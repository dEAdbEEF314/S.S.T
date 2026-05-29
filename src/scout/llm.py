import re
import json
import logging
import requests
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from .rate_limit import DistributedRateLimiter

logger = logging.getLogger("scout.llm")

class LLMOrganizer:
    def __init__(self, api_key: str, base_url: str, 
                 model: str = "gemini-1.5-pro", 
                 rpm: int = 15, tpm: int = 10000000, rpd: int = 1500,
                 user_language: str = "ja",
                 llm_backend: str = "GEMINI",
                 draft_model: Optional[str] = None,
                 metadata_source_priority: str = "MBZ,STEAM_PICS,STEAM_STORE,STEAM_TAGS,EMBEDDED",
                 priority_tit2: str = "FILE,EMBED,VDF,MBZ,PICS_API",
                 priority_tpe1: str = "EMBED,MBZ,PICS_API",
                 priority_trck: str = "EMBED,MBZ,PICS_API",
                 priority_tpos: str = "PICS_API,EMBED,MBZ",
                 priority_tyer: str = "EMBED,MBZ,WEB_API",
                 priority_tpub: str = "MBZ,PICS_API",
                 priority_apic: str = "EMBED,MBZ,PICS_API,WEB_API"):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.draft_model = draft_model
        self.user_language = user_language
        self.llm_backend = llm_backend.upper()
        self.metadata_source_priority = metadata_source_priority
        self.priority_tit2 = priority_tit2
        self.priority_tpe1 = priority_tpe1
        self.priority_trck = priority_trck
        self.priority_tpos = priority_tpos
        self.priority_tyer = priority_tyer
        self.priority_tpub = priority_tpub
        self.priority_apic = priority_apic
        self.limiter = DistributedRateLimiter(rpm, tpm, rpd)

    def _simplify_v_album(self, v: Optional[Dict], sampled: bool = False) -> Optional[Dict]:
        if not v: return None
        v_copy = v.copy()
        tracks = v_copy.get("tracks", [])
        
        # Remove heavy/redundant fields for LLM context, but KEEP credits for FINGERPRINT
        simplified_tracks = []
        for t in tracks:
            if not isinstance(t, dict): 
                simplified_tracks.append(t)
                continue
            st = {
                "d": t.get("disc"),
                "n": t.get("track_num"),
                "t": t.get("title")
            }
            # Keep credits if they exist (FINGERPRINT source)
            if t.get("credits"):
                st["c"] = t["credits"]
            simplified_tracks.append(st)
        
        if sampled and len(simplified_tracks) > 20:
            v_copy["tracks"] = simplified_tracks[:15] + [{"note": f"... skipping {len(simplified_tracks)-20} tracks ..."}] + simplified_tracks[-5:]
        else:
            v_copy["tracks"] = simplified_tracks
            
        return v_copy

    def consolidate_virtual_albums(self, app_id: int, v_steam: Dict, v_fingerprint: Optional[Dict], v_local: Dict, num_ctx: Optional[int] = None) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Consolidates the three virtual albums into a final tag set using LLM.
        """
        full_logs = []
        
        # Simplify albums to save context
        s_steam = self._simplify_v_album(v_steam, sampled=True)
        s_fingerprint = self._simplify_v_album(v_fingerprint, sampled=True)
        s_local = self._simplify_v_album(v_local, sampled=True)

        # Phase 1: Identity & Global Tags
        identity_prompt = f"""
Generate an audit JSON object based on these three "Virtual Albums".
(Note: Tracklists are sampled/simplified)

### 1. STEAM VIRTUAL ALBUM (Official Store Info)
{json.dumps(s_steam, ensure_ascii=False)}

### 2. FINGERPRINT VIRTUAL ALBUM (Physical Waveform Match / Ground Truth)
{json.dumps(s_fingerprint, ensure_ascii=False) if v_fingerprint else "NOT AVAILABLE"}

### 3. LOCAL VIRTUAL ALBUM (Current File Tags/Filenames)
{json.dumps(s_local, ensure_ascii=False)}

### [MASTER AUDIT GUIDELINE]
1. GROUND TRUTH: FINGERPRINT matches are based on physical waveforms. 
   If physical_match_ratio > 80%, set Identity Confidence to 95-100% even if names vary.
2. IDENTITY ALIASES: Game Developer (Steam) == Artist (MBZ), Publisher (Steam) == Label (MBZ). 
   These are NOT contradictions.
3. YEAR FLEXIBILITY: Difference between Store and Physical release year is NORMAL.
4. JUDGEMENT: Choose ARCHIVE if Confidence >= 95 and Quality >= 90.

### OUTPUT FORMAT (JSON ONLY, NO PREAMBLE, NO THINKING):
```json
{{
  "identity_confidence": number (0-100 integer),
  "integrity_quality": number (0-100 integer),
  "archive_vs_review_ratio": {{"archive": number, "review": number}},
  "confidence_reason": "English reasoning",
  "strategy": "FINGERPRINT_BASED" | "STEAM_BASED" | "LOCAL_BASED" | "HYBRID",
  "semantic_label": "Label in {self.user_language}",
  "global_tags": {{
    "canonical_album_artist": "...",
    "canonical_genre": "...",
    "canonical_year": "YYYY",
    "canonical_label": "...",
    "chosen_mbz_id": "..."
  }}
}}
```
"""
        global_res, global_log = self._call_llm(app_id, identity_prompt, num_ctx=num_ctx)
        full_logs.append(global_log)

        if not global_res:
             return None, {"phase1_res": None, "phase1_log": global_log}

        # Normalize confidence if in 0-1 range
        conf = global_res.get("identity_confidence", 0)
        if 0 < conf <= 1:
            conf *= 100
            global_res["identity_confidence"] = conf
        
        if conf < 90:
             return None, {"phase1_res": global_res, "phase1_log": global_log}

        # Phase 2: Track-by-Track Mapping with Chunking
        final_instructions = {}
        local_tracks = v_local.get("tracks", [])
        
        # Prepare full simplified reference tracks for Phase 2 (not sampled)
        ref_steam = self._simplify_v_album(v_steam, sampled=False).get("tracks", [])
        ref_fingerprint = self._simplify_v_album(v_fingerprint, sampled=False).get("tracks", []) if v_fingerprint else []
        
        chunk_size = 20
        for i in range(0, len(local_tracks), chunk_size):
            chunk = local_tracks[i:i + chunk_size]
            s_chunk = []
            for t in chunk:
                s_chunk.append({
                    "id": t.get("title"), 
                    "d": t.get("disc"),
                    "dur": (t.get("duration_ms", 0) // 1000) if t.get("duration_ms") else None
                })
            
            mapping_prompt = f"""
Generate track mapping instructions for tracks {i+1} to {i+len(chunk)}.
Identity: {json.dumps(global_res.get("global_tags"), ensure_ascii=False)}

### REFERENCE VIRTUAL ALBUMS (TRACKS ONLY):
STEAM: {json.dumps(ref_steam, ensure_ascii=False)}
FINGERPRINT (Ground Truth): {json.dumps(ref_fingerprint, ensure_ascii=False)}

### LOCAL_CHUNK TO PROCESS:
{json.dumps(s_chunk, ensure_ascii=False)}

### RULES:
1. Match LOCAL_CHUNK to FINGERPRINT (Ground Truth) first.
2. If FINGERPRINT has "c" (credits: composer, lyricist, etc.), ensure they are integrated.
3. Output JSON ONLY. No preamble, no thinking.

### MANDATORY OUTPUT FORMAT (JSON ONLY):
```json
{{
  "track_instructions": {{
     "LOCAL_TRACK_ID": {{
        "action": "use_fingerprint" | "use_steam" | "use_local",
        "override_title": string | null,
        "override_track": number | null,
        "override_disc": number | null,
        "composer": string | null,
        "lyricist": string | null,
        "arranger": string | null,
        "reason": "English reasoning"
     }}
  }}
}}
```
"""
            track_res, track_log = self._call_llm(app_id, mapping_prompt, num_ctx=num_ctx)
            full_logs.append(track_log)
            
            if track_res and "track_instructions" in track_res:
                for t_id, data in track_res["track_instructions"].items():
                    # Match by the "id" we provided (which was the title)
                    matching_track = next((t for t in chunk if t["title"] == t_id), None)
                    if matching_track:
                        tid = f"{matching_track['local_key'][0]}_{matching_track['local_key'][1]}"
                        data.update({
                            "TPE2": global_res["global_tags"].get("canonical_album_artist"),
                            "TCON": global_res["global_tags"].get("canonical_genre"),
                            "TDRC": global_res["global_tags"].get("canonical_year"),
                            "TPUB": global_res["global_tags"].get("canonical_label"),
                            "TEXT": data.get("lyricist"),
                            "TCOM": data.get("composer"),
                            "TPE4": data.get("arranger"),
                            "identity_confidence": global_res["identity_confidence"],
                            "confidence_score": global_res["identity_confidence"],
                            "strategy": global_res["strategy"],
                            "semantic_label": global_res["semantic_label"]
                        })
                        final_instructions[tid] = data

        return final_instructions, {"phase1_res": global_res, "logs": full_logs}

    def consolidate_metadata(self, app_id: int, steam_info: Dict[str, Any], track_sources: Dict[str, List[Dict[str, Any]]], mbz_candidates: List[Dict[str, Any]], num_ctx: Optional[int] = None) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        full_logs = []
        
        # --- Phase 1: Determine Global Identity (The "Soul") ---
        # Formatting helpers for Markdown readability
        def format_store_tracks(tracks):
            if not tracks: return "なし"
            md = "\n| Disc | No | Title | Duration (s) |\n|---|---|---|---|\n"
            for t in tracks: md += f"| {t.get('disc','')} | {t.get('number','')} | {t.get('title','')} | {t.get('duration_s','')} |\n"
            return md

        def format_mbz_candidates(cands):
            if not cands: return "なし"
            md = "\n"
            for i, c in enumerate(cands):
                md += f"#### Candidate [{i}]: {c.get('album')} (Score: {c.get('score')})\n"
                md += f"- **Artist**: {c.get('artist')}\n- **Year**: {c.get('year')}\n- **Label**: {c.get('label')}\n- **Tracks**: {c.get('track_count')} (Digital: {c.get('is_digital')})\n- **Evidence**: {', '.join(c.get('evidence', []))}\n"
                md += "- **Tracklist Sample**:\n"
                for t in c.get('tracks', [])[:5]:
                    md += f"  - {t.get('position')}: {t.get('title')}\n"
                if len(c.get('tracks', [])) > 5: md += "  - ...\n"
                md += "\n"
            return md

        def format_local_summary(sources):
            if not sources: return "なし"
            md = "\n| Logical ID | Duration (s) |\n|---|---|\n"
            for tid, s in sources.items():
                dur = s[0].get('duration') if s else 'Unknown'
                md += f"| {tid} | {dur} |\n"
            return md

        steam_tracks_json = json.dumps(steam_info.get('store_tracklist', []), ensure_ascii=False)
        mbz_cands_json = json.dumps(mbz_candidates, indent=2, ensure_ascii=False)
        local_tracks_json = json.dumps([{"id": tid, "duration": s[0].get("duration")} for tid, s in track_sources.items()], indent=2)

        # Dynamic System Hint for Fallback
        system_hint = ""
        local_count = len(track_sources)
        store_count = len(steam_info.get('store_tracklist', []))
        if local_count > 0 and local_count == store_count:
            if local_count == 1:
                system_hint = "\n### [SYSTEM HINT]\nSTRUCTURAL PERFECT MATCH DETECTED (SINGLE TRACK). Apply 'シングル盤の法則'.\n"
            else:
                system_hint = f"\n### [SYSTEM HINT]\nSTRUCTURAL PERFECT MATCH DETECTED ({local_count} tracks). Highly likely the same work.\n"

        global_id_prompt = f"""
You are the authoritative [Master Archive Auditor] for music metadata management.
Analyze the provided information sources to independently evaluate the "Identity" (origin) and "Integrity" (quality) of this work.

### [CRITICAL: Metadata Constitution (Priority)]
The user has specified the following order of trust for information sources:
Global Priority: {self.metadata_source_priority}

When conflicts or contradictions arise in specific fields, decide according to these individual priorities:
- Track Title (TIT2): {self.priority_tit2}
- Artist (TPE1): {self.priority_tpe1}
- Track Number (TRCK): {self.priority_trck}
- Disc Number (TPOS): {self.priority_tpos}
- Year (TYER): {self.priority_tyer}
- Label/Publisher (TPUB): {self.priority_tpub}
- Cover Art (APIC): {self.priority_apic}

These priorities are absolute guidelines for determining the "correct" answer in case of discrepancies.
However, if a top-tier source contains track numbers like "01 - Title", you are expected to perform intellectual cleaning to extract only the pure title, possibly by comparing it with lower-tier clean sources.

### [CRITICAL: Dirty Tags & Forced Cleaning]
- **Supreme Command**: This system prioritizes "Visibility on DJ Equipment". If a title begins with a track number like "01 - " or "01. ", **you MUST remove it (cleaning), even if it is the official name in MusicBrainz or Steam Store.**
- Titles that trigger the system's validation logic (Regex: `^(\\d+)([\\s.-]+)`) will be detected as "Dirty Tags" and the archive will be rejected.
- Your task is to compare multiple sources and derive the "Purest Title (no numbers)". If top-tier sources are "dirty", adopt a cleaner lower-tier source or perform the cleaning yourself.
- If a title is "01 - Title", you MUST output it as "Title". Failure to do so will result in your inference being rejected as "Low Quality".

### [Advanced Identification: AcoustID Bottom-Up Analysis]
Pay attention to the "Evidence" in each MusicBrainz candidate:
- **ACOUSTID_RELEASE_MATCH**: This release ID is a "physical match" directly pointed to by the fingerprints generated from the local audio files.
- **DIRECT_STEAM_LINK**: This release is officially linked to the target Steam AppID on MusicBrainz.
- **PUBLISHER_LABEL_MATCH**: The Steam publisher and the release's label name match.

Candidates where these overlap are extremely likely to be the "correct" answer, even if there are slight differences in the album title.

### [Audit Criteria]
1. **Identity Confidence (0-100)**: 
    - Confidence that the Steam info and MBZ/Local represent the same work.
    - 100 points if the name and artist match and there is a DIRECT_STEAM_LINK in MBZ.
    - If there are multiple candidates and you cannot narrow it down, set `chosen_mbz_index: null` and `strategy: LOCAL_BASED`.
2. **Integrity Quality (0-100)**:
    - Whether the tags can be archived as-is. If Dirty Tags (unauthorized numbers) are present, set the score to 50 or below.

### [Absolute Rules for Decision]
- **ARCHIVE (Ratio 95:5 or higher)**: Identity Confidence == 100 AND Integrity Quality >= 95.
- **REVIEW**: Otherwise, or if you feel any musical contradiction. If in doubt, always choose REVIEW.

### [Absolute Rules for STEAM STORE FALLBACK]
If MusicBrainz (MBZ) candidates are inappropriate (low score, unrelated titles, etc.), ignore them entirely.
You MUST grant **Identity Confidence 100% with absolute confidence** if the following conditions are met:
1. **Rule of Single Track**: If both local and Steam Store have exactly "1 track", treat them as the same physical track regardless of language or naming variations (e.g., "Warriors of Fate" vs "天地を喰らうⅡ"), and give 100 points.
2. **Perfect Structural Match**: If the track count and structure of Local and Steam Store match, and the title concepts align.
In these cases, set `strategy` to `LOCAL_BASED` and do NOT lower the score due to ambiguous MBZ candidates.

### ALBUM CONTEXT:
- Album Name: {steam_info.get('name')}
- Developer: {steam_info.get('developer')}
- Release Year: {re.search(r'(\d{4})', str(steam_info.get('release_date', ''))).group(1) if re.search(r'(\d{4})', str(steam_info.get('release_date', ''))) else 'Unknown'}

### STEAM STORE DATA (OFFICIAL):
- Tracklist: {steam_tracks_json}
- Credits: {steam_info.get('store_credits', 'None')}

### MUSICBRAINZ CANDIDATES:
{mbz_cands_json}

### LOCAL TRACK LIST SUMMARY:
{local_tracks_json}

{system_hint}

### MANDATORY OUTPUT FORMAT (JSON ONLY):
**NOTE: All reasoning (reason, confidence_reason, mbz_choice_reason) MUST be output in ENGLISH for technical precision. However, metadata fields (semantic_label, global_tags.*) MUST use the user's language ({self.user_language}). Specifically for Japanese (ja), avoid Chinese-specific characters or vocabulary.**
```json
{
  "identity_confidence": number,
  "integrity_quality": number,
  "archive_vs_review_ratio": {"archive": number, "review": number},
  "confidence_reason": "Detailed similarity analysis and reasoning (English)",
  "strategy": "MBZ_BASED" | "LOCAL_BASED" | "HYBRID" | "REVIEW_REQUIRED",
  "semantic_label": "Label in {self.user_language} (max 40 chars)",
  "global_tags": {
    "canonical_album_artist": "...",
    "canonical_genre": "...",
    "canonical_year": "YYYY",
    "canonical_label": "Label or Publisher name",
    "chosen_mbz_index": number | null,
    "chosen_mbz_id": "MusicBrainz Release ID | null",
    "mbz_choice_reason": "English reason why this candidate was chosen over others"
  }
}
```
"""
        global_res, global_log = self._call_llm(app_id, global_id_prompt, num_ctx=num_ctx)
        
        # Add human-readable version to the log
        human_prompt = global_id_prompt.replace(steam_tracks_json, format_store_tracks(steam_info.get('store_tracklist', [])))
        human_prompt = human_prompt.replace(mbz_cands_json, format_mbz_candidates(mbz_candidates))
        human_prompt = human_prompt.replace(local_tracks_json, format_local_summary(track_sources))
        global_log["human_prompt"] = human_prompt
        full_logs.append(global_log)
        
        if not global_res:
            return None, {"phase1_log": global_log}
            
        id_conf = int(global_res.get("identity_confidence", 0))
        archive_ratio = int(global_res.get("archive_vs_review_ratio", {}).get("archive", 0))
        
        if id_conf < 95 or archive_ratio < 90 or global_res.get("strategy") == "REVIEW_REQUIRED":
            return {}, {"phase1_res": global_res, "phase1_log": global_log}

        # --- Phase 2: Sequential Track Mapping ---
        global_identity = global_res.get("global_tags", {})
        strategy = global_res.get("strategy")
        all_instructions = {}
        full_logs = []
        # Key: (disc, track) -> sid
        seen_numbers_global = {}
        
        track_ids = list(track_sources.keys())
        # Create a mapping of stable IDs (idx_N) to original logical IDs
        stable_to_logical = {f"idx_{i}": tid for i, tid in enumerate(track_ids)}
        logical_to_stable = {tid: sid for sid, tid in stable_to_logical.items()}
        
        chunk_size = 10 if self.llm_backend == "OLLAMA" else 30

        for i in range(0, len(track_ids), chunk_size):
            chunk = track_ids[i:i + chunk_size]
            
            # Create context with explicit local disc/track info
            chunk_context = {}
            for k in chunk:
                sid = logical_to_stable[k]
                try:
                    local_disc = int(k.split('_')[0])
                except:
                    local_disc = 1
                
                chunk_context[sid] = {
                    "local_context": {
                        "disc": local_disc
                    },
                    "sources": track_sources[k]
                }

            chunk_json = json.dumps(chunk_context, indent=None, ensure_ascii=False)
            mapping_prompt = f"""
            Perform precise track mapping.
            Identity: {json.dumps(global_identity, ensure_ascii=False)}

            ### STEAM STORE DATA (OFFICIAL):
            - Tracklist: {steam_tracks_json}
            - Credits: {steam_info.get('store_credits', 'None')}

            ### INSTRUCTIONS:
            1. Parse the credits text (e.g., "Track 1 by X") and link it to the composer or artist of the corresponding track.
            2. Match the Steam official tracklist titles with the local tracks, and use the most reliable source.
            3. **Title Cleaning (Absolute Command)**: Regardless of the source adopted, if a title begins with a track number like "01. " or "1- ", you MUST remove it.
            4. **Track Number Completion & Invalidation**:
               - If the local track number is unknown (0 or null) and the title matches the Steam official tracklist, output that number as `override_track`.
            5. **Disc Number Maintenance & Completion (Critical)**:
               - If the provided `local_context.disc` is 2 or higher, ALWAYS output it in `override_disc`.
            6. **No Duplicate Track Numbers (Absolute Command)**:
               - It is **systemically forbidden** to assign the same `override_track` to multiple tracks within the same disc.

            ### TRACKS TO MAP (Keys are Stable IDs):
            {chunk_json}

            ### MANDATORY OUTPUT FORMAT (JSON ONLY):
            ```json
            {{
              "track_instructions": {{
                 "STABLE_ID": {{
                    "action": "use_mbz" | "use_local_tag" | "use_filename" | "needs_review",
                    "mbz_track_index": number,
                    "override_title": string | null,
                    "override_track": number | null,
                    "override_disc": number | null,
                    "reason": "Reasoning for the decision (English)"
                 }}
              }}
            }}
            ```
            """
            res, log_data = self._call_llm(app_id, mapping_prompt, num_ctx=num_ctx)

            human_chunk_context = {stable_to_logical[sid]: ctx for sid, ctx in chunk_context.items()}
            human_mapping_prompt = mapping_prompt.replace(chunk_json, json.dumps(human_chunk_context, indent=2, ensure_ascii=False))
            log_data["human_prompt"] = human_mapping_prompt
            full_logs.append(log_data)
            
            if res and "track_instructions" in res:
                for sid, data in res["track_instructions"].items():
                    tid = stable_to_logical.get(sid)
                    if not tid: continue
                    
                    try:
                        local_disc = int(tid.split('_')[0])
                    except:
                        local_disc = 1

                    target_disc = data.get("override_disc") or local_disc
                    target_track = data.get("override_track")
                    
                    if target_track is None:
                        for src in track_sources[tid]:
                            if src["type"] == "filename":
                                target_track = src.get("inferred_track_num")
                                break
                    
                    if target_track is not None:
                        key = (str(target_disc), str(target_track))
                        if key in seen_numbers_global:
                            if data.get("override_track") is not None:
                                data["override_track"] = None
                        else:
                            seen_numbers_global[key] = sid

                    data.update({
                        "TPE2": global_identity.get("canonical_album_artist"),
                        "TCON": global_identity.get("canonical_genre"),
                        "TDRC": global_identity.get("canonical_year"),
                        "identity_confidence": id_conf,
                        "confidence_score": id_conf,
                        "strategy": strategy,
                        "semantic_label": global_res.get("semantic_label"),
                        "chosen_mbz_index": global_identity.get("chosen_mbz_index", 0),
                        "override_track": data.get("override_track"),
                        "override_disc": data.get("override_disc")
                    })
                    all_instructions[tid] = data

        return all_instructions, {"phase1_res": global_res, "phase1_log": global_log, "chunks": full_logs}

    def _call_llm(self, app_id: int, prompt: str, num_ctx: Optional[int] = None) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        messages = [{"role": "user", "content": prompt}]
        log_entry = {"timestamp": datetime.utcnow().isoformat(), "prompt": prompt, "response": None, "error": None}

        logger.debug(f"[{app_id}] --- [LLM PROMPT START] ---\n{prompt}\n--- [LLM PROMPT END] ---")

        if self.llm_backend not in ["OLLAMA"] and not self.limiter.acquire(messages):
            log_entry["error"] = "Rate limit reached"
            return None, log_entry

        max_retries = 3
        retry_delay = 5

        if self.llm_backend == "OLLAMA":
            url = f"{self.base_url}/api/chat"
            options = {"temperature": 0.0, "num_predict": 4096}
            if num_ctx:
                options["num_ctx"] = num_ctx
            payload = {
                "model": self.model, "messages": messages, "stream": False, "format": "json",
                "options": options
            }
            if self.draft_model:
                payload["draft_model"] = self.draft_model
            headers = {"Content-Type": "application/json"}
        else:
            url = f"{self.base_url}/v1beta/openai/chat/completions" if self.llm_backend == "GEMINI" else f"{self.base_url}/v1/chat/completions"
            payload = {"model": self.model, "messages": messages, "temperature": 0.0, "response_format": {"type": "json_object"}}
            if num_ctx:
                payload["num_ctx"] = num_ctx
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=300)
                if response.status_code == 200:
                    res_json = response.json()
                    message = res_json.get("message", {})
                    content = message.get("content", "")
                    thinking = message.get("thinking", "")
                    
                    if self.llm_backend != "OLLAMA":
                        content = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")

                    logger.debug(f"[{app_id}] --- [LLM RESPONSE START] ---\n{content}\n--- [LLM RESPONSE END] ---")
                    if thinking:
                        logger.debug(f"[{app_id}] --- [LLM THINKING START] ---\n{thinking}\n--- [LLM THINKING END] ---")
                    
                    if not content or not content.strip():
                        if thinking and '{' in thinking:
                            # Attempt to salvage JSON from thinking if content is empty
                            content = thinking
                        else:
                            raise ValueError("Empty response")
                    
                    log_entry["response"] = content
                    
                    try:
                        clean_content = re.sub(r'```json\s*(.*?)\s*```', r'\1', content, flags=re.DOTALL)
                        clean_content = re.sub(r'<(thought|reasoning)>.*?</\1>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
                        start_idx = clean_content.find('{')
                        end_idx = clean_content.rfind('}')
                        if start_idx != -1 and end_idx != -1:
                            json_str = clean_content[start_idx:end_idx + 1]
                            json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
                            return json.loads(json_str), log_entry
                        else:
                            raise ValueError("No valid JSON object found in response")
                    except Exception as e:
                        logger.warning(f"[{app_id}] JSON strict parsing failed: {e}")
                        raise
                
                log_entry["error"] = f"HTTP {response.status_code}"
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                    continue
                return None, log_entry

            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"[{app_id}] LLM {self.llm_backend} attempt {attempt+1} failed: {e}")
                    time.sleep(retry_delay)
                    continue
                log_entry["error"] = str(e)
                return None, log_entry
        return None, log_entry

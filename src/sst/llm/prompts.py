import json
from typing import List, Dict, Any, Optional

def build_mapping_prompt(
    global_res: Dict[str, Any],
    s_mbz_search: Dict[str, Any],
    v_mbz_search: Optional[Dict[str, Any]],
    ref_steam: List[Dict[str, Any]],
    ref_fingerprint: List[Dict[str, Any]],
    s_chunk: List[Dict[str, Any]],
    start_idx: int,
    user_language: str,
) -> str:
    ref_fingerprint_str = json.dumps(ref_fingerprint, ensure_ascii=False) if ref_fingerprint else "NOT AVAILABLE"
    end_idx = start_idx + len(s_chunk)
    return f"""
        Generate track mapping instructions for tracks {start_idx+1} to {end_idx}.
        Identity: {json.dumps(global_res.get("global_tags"), ensure_ascii=False)}

        ### REFERENCE VIRTUAL ALBUMS (TRACKS ONLY):
        STEAM: {json.dumps(ref_steam, ensure_ascii=False)}
        FINGERPRINT: {ref_fingerprint_str}
        MBZ_SEARCH: {json.dumps(s_mbz_search.get("tracks", []) if s_mbz_search else [], ensure_ascii=False) if v_mbz_search else "NOT AVAILABLE"}

        ### LOCAL_CHUNK TO PROCESS:
        {json.dumps(s_chunk, ensure_ascii=False)}

        ### RULES:
        1. Match LOCAL_CHUNK to FINGERPRINT (if available) first, then MBZ_SEARCH, then STEAM. NEVER select a "use_*" action for a source that is NOT AVAILABLE.
        2. **Unique Mapping**: Each track in the LOCAL_CHUNK MUST map to a **UNIQUE** reference track (v_idx). Do NOT map multiple local tracks to the same "matched_v_idx".
        3. **Fingerprint Direct Mapping**: FINGERPRINT indices (`v_idx`) are strictly aligned 1:1 with LOCAL_CHUNK indices (`chunk_idx`). If you use "use_fingerprint" for a local track, you MUST set `matched_v_idx` EXACTLY equal to its `chunk_idx`. If the corresponding FINGERPRINT track is null or missing, you MUST fallback to MBZ_SEARCH or STEAM instead.
        4. **Automatic Numbering**: If action is "use_steam", "use_fingerprint", or "use_mbz_search", LEAVE "override_track" and "override_disc" as **null**. The system will automatically adopt the numbers from the reference album.

        5. **Override Only When Necessary**: Use "override_track" or "override_disc" ONLY if the reference album has WRONG or MISSING numbers (e.g., track number is 0 or null).
        6. **Disc Alignment**: If the matched reference track belongs to a different disc than the local "d", you MUST ensure the final output reflects the correct disc.
        7. If action is "use_fingerprint", "use_steam", or "use_mbz_search", you MUST provide the exact "v_idx" value from the respective reference album as "matched_v_idx". Note that "v_idx" is 0-indexed, so "matched_v_idx": 0 is valid and expected for the first track. Do NOT shift indices.
        8. No Duplicate Tracks: Ensure that the final mapping does not result in duplicate track numbers within the same disc.
        9. Output JSON ONLY. No preamble, no thinking.

**NOTE: All reasoning (reason) MUST be output in the language code: {user_language}. If {user_language} is "ja" (Japanese), you MUST write in native Japanese and strictly avoid Chinese characters or vocabulary.**

### MANDATORY OUTPUT FORMAT (JSON ONLY):
```json
{{
  "track_instructions": {{
     "CHUNK_INDEX": {{
        "action": "use_fingerprint" | "use_mbz_search" | "use_steam" | "use_local",
        "matched_v_idx": number | null,
        "override_title": string | null,
        "override_track": number | null,
        "override_disc": number | null,
        "composer": string | null,
        "lyricist": string | null,
        "arranger": string | null,
        "reason": "Reasoning in {user_language}"
     }}
  }}
}}
```
"""

def build_coherence_prompt(coherences: dict, steam_skel: list, fp_skel: list) -> str:
    return f"""
Generate a Coherence Routing Map for a massive album.
We have split the LOCAL album into logical 'Coherences' (blocks of ~30 tracks).
For lift Coherence, identify the corresponding track range (start_v_idx to end_v_idx) in the REFERENCE albums.

### LOCAL COHERENCES (Skeleton):
{json.dumps(coherences, ensure_ascii=False, indent=2)}

### STEAM REFERENCE SKELETON:
{json.dumps(steam_skel, ensure_ascii=False, indent=2)}

### FINGERPRINT REFERENCE SKELETON:
{json.dumps(fp_skel, ensure_ascii=False, indent=2) if fp_skel else "NOT AVAILABLE"}

### OUTPUT FORMAT (JSON ONLY, NO PREAMBLE):
```json
{{
  "coherence_mappings": {{
    "Coherence_1": {{
      "steam_start_v_idx": 0,
      "steam_end_v_idx": 29,
      "fingerprint_start_v_idx": 0,
      "fingerprint_end_v_idx": 29
    }}
  }}
}}
```
"""

def build_identity_prompt(s_steam: dict, s_fingerprint: Optional[dict], s_mbz_search: Optional[dict], s_local: dict, user_language: str) -> str:
    return f"""
Generate an audit JSON object based on these three "Virtual Albums".
(Note: Tracklists are sampled/simplified)

### 1. STEAM VIRTUAL ALBUM (Official Store Info)
{json.dumps(s_steam, ensure_ascii=False)}

### 2. FINGERPRINT VIRTUAL ALBUM (Physical Waveform Match / Ground Truth)
{json.dumps(s_fingerprint, ensure_ascii=False) if s_fingerprint else "NOT AVAILABLE"}

### 3. MBZ_SEARCH VIRTUAL ALBUM (Semantic Truth / Text Match)
{json.dumps(s_mbz_search, ensure_ascii=False) if s_mbz_search else "NOT AVAILABLE"}

### 4. LOCAL VIRTUAL ALBUM (Current File Tags/Filenames)
{json.dumps(s_local, ensure_ascii=False)}

### [MASTER AUDIT GUIDELINE]
1. GROUND TRUTH: FINGERPRINT matches are based on physical waveforms. 
   If physical_match_ratio > 80%, set Identity Confidence to 95-100% even if names vary.
   If source is "VERIFIED_MBZ" (FINGERPRINT and MBZ_SEARCH match perfectly), use 100% confidence.
2. STEAM-TRUST PATH: If STEAM tracklist structurally matches LOCAL (same count/order) and titles align, TRUST STEAM as Ground Truth and set Identity Confidence to 100%, EVEN IF FINGERPRINT is missing or has a low match ratio. FINGERPRINT incompleteness must NEVER lower the score when STEAM is a perfect structural match.
3. DISC NUMBER FLEXIBILITY: LOCAL disc numbers (d) are often incorrect or defaulted to 1. 
   If STEAM or FINGERPRINT define multiple discs, you MUST re-assign tracks to the correct discs in Phase 2.
4. IDENTITY ALIASES: Game Developer (Steam) == Artist (MBZ), Publisher (Steam) == Label (MBZ). 
   These are NOT contradictions.
5. JUDGEMENT: Choose ARCHIVE if Confidence >= 100 and Quality >= 95. 
   When ARCHIVE is chosen, you MUST set "archive_vs_review_ratio" to {{"archive": 100, "review": 0}}.

**NOTE: All reasoning and text values (confidence_reason, semantic_label, global_tags) MUST be output in the language code: {user_language}. If {user_language} is "ja" (Japanese), you MUST write in native Japanese and strictly avoid Chinese characters or vocabulary. Keep confidence_reason EXTREMELY short and concise (under 50 characters) to save tokens.**

### OUTPUT FORMAT (JSON ONLY, NO PREAMBLE, NO THINKING):
```json
{{
  "identity_confidence": number (0-100 integer),
  "integrity_quality": number (0-100 integer),
  "archive_vs_review_ratio": {{"archive": number, "review": number}},
  "confidence_reason": "Very brief reasoning in {user_language} (Max 50 chars)",
  "strategy": "FINGERPRINT_BASED" | "STEAM_BASED" | "LOCAL_BASED" | "MBZ_SEARCH_BASED" | "HYBRID",
  "semantic_label": "Label in {user_language}",
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

def get_system_prompt() -> str:
    return """You are a [Metadata Audit JSON Generator].
Your ONLY output is a raw JSON object. 

RULES:
1. Start your response with "{" immediately.
2. DO NOT use reasoning blocks, "Thinking Process", or any preamble.
3. Output MUST be valid JSON.
4. If uncertain, default to judgment "REVIEW" and confidence 0."""

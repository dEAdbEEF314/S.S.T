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
      Generate STEAM slot alignment instructions for the physical local files in this batch.
      Album identity summary: {json.dumps(global_res.get("global_tags"), ensure_ascii=False)}

      ### STEAM SLOTS (GROUND TRUTH STRUCTURE):
      {json.dumps(ref_steam, ensure_ascii=False)}

      ### ACOUSTID / MBZ_RELEASE SIGNALS:
      {ref_fingerprint_str}

      ### MBZ_SEARCH AUXILIARY SIGNALS:
      {json.dumps(s_mbz_search.get("tracks", []) if s_mbz_search else [], ensure_ascii=False) if v_mbz_search else "NOT AVAILABLE"}

      ### LOCAL FILE SIGNALS TO PROCESS:
        {json.dumps(s_chunk, ensure_ascii=False)}

        ### RULES:
      1. STEAM defines the canonical slot structure. Prefer ACOUSTID / MBZ_RELEASE as evidence, but assign files to STEAM slots.
      2. Each local file must belong to at most one STEAM slot.
      3. Each STEAM slot in this chunk should list the exact file_id values that belong to it.
      4. Use ACOUSTID / MBZ_RELEASE when available, then MBZ_SEARCH, then filename / embedded numbering, then title similarity.
      5. If action is "use_steam", "use_fingerprint", or "use_mbz_search", provide the exact `matched_v_idx` of the referenced STEAM or auxiliary track.
      6. Use `override_track` or `override_disc` only when the source numbering is missing or broken.
      7. Do not create titles or metadata that are not supported by the provided signals.
      8. Keep `reason` concise.
      9. Output JSON ONLY. No preamble, no thinking.

**NOTE: All reasoning (reason) MUST be output in the language code: {user_language}. If {user_language} is "ja" (Japanese), you MUST write in native Japanese and strictly avoid Chinese characters or vocabulary.**

### MANDATORY OUTPUT FORMAT (JSON ONLY):
```json
{{
  "slots": {{
    "STEAM_SLOT_NUMBER": {{
      "files": ["FILE_ID"],
      "confidence": 0.0,
      "reason": "Reasoning in {user_language}"
    }}
  }},
  "unassigned_files": ["FILE_ID"],
  "unassigned_reason": "Reasoning in {user_language}",
  "track_instructions": {{
    "FILE_ID": {{
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

def build_identity_prompt(s_steam: dict, s_fingerprint: Optional[dict], s_mbz_search: Optional[dict], s_local: dict, user_language: str) -> str:
    return f"""
Generate an audit JSON object for aligning local files to STEAM slots.
(Note: Tracklists are sampled/simplified)

### 1. STEAM ALBUM (Ground Truth Structure)
{json.dumps(s_steam, ensure_ascii=False)}

### 2. ACOUSTID / MBZ_RELEASE SIGNALS (Physical Match)
{json.dumps(s_fingerprint, ensure_ascii=False) if s_fingerprint else "NOT AVAILABLE"}

### 3. MBZ_SEARCH SIGNALS (Text Match)
{json.dumps(s_mbz_search, ensure_ascii=False) if s_mbz_search else "NOT AVAILABLE"}

### 4. LOCAL FILE SIGNALS (Current Files)
{json.dumps(s_local, ensure_ascii=False)}

### [MASTER AUDIT GUIDELINE]
1. STEAM is the structural source of truth.
2. ACOUSTID matches are the strongest physical evidence for album identity and artist resolution.
3. STEAM-TRUST PATH: If STEAM tracklist structurally matches LOCAL (same count/order) and numbering aligns, you may trust STEAM even when ACOUSTID is incomplete.
4. DISC NUMBER FLEXIBILITY: LOCAL disc numbers (d) are often incorrect or defaulted to 1.
  If STEAM or ACOUSTID define multiple discs, you MUST re-assign tracks to the correct discs in alignment.
5. IDENTITY ALIASES: Game Developer (Steam) == Artist (MBZ), Publisher (Steam) == Label (MBZ).
   These are NOT contradictions.
6. JUDGEMENT: prefer review when evidence is incomplete or contradictory.

**NOTE: All reasoning and text values (confidence_reason, semantic_label, global_tags) MUST be output in the language code: {user_language}. If {user_language} is "ja" (Japanese), you MUST write in native Japanese and strictly avoid Chinese characters or vocabulary. Keep confidence_reason EXTREMELY short and concise (under 50 characters) to save tokens.**

### OUTPUT FORMAT (JSON ONLY, NO PREAMBLE, NO THINKING):
```json
{{
  "album_confidence": number (0-100 integer),
  "mapping_confidence": number (0-100 integer),
  "data_quality": number (0-100 integer),
  "concerns": ["Concern in {user_language}"],
  "identity_confidence": number (0-100 integer),
  "integrity_quality": number (0-100 integer),
  "archive_vs_review_ratio": {{"archive": number, "review": number}},
  "confidence_reason": "Very brief reasoning in {user_language} (Max 50 chars)",
  "strategy": "ACOUSTID_BASED" | "STEAM_BASED" | "LOCAL_BASED" | "MBZ_SEARCH_BASED" | "HYBRID",
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

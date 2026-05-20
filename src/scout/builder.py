import logging
import re
from typing import Dict, Any, List, Optional
from .models import SteamMetadata

logger = logging.getLogger("scout.builder")

class MetadataBuilder:
    @staticmethod
    def _clean_title_logic(title: str, track_number: Optional[str] = None) -> str:
        if not title: return ""
        
        # Check for leading track numbers like "01. ", "1 - ", etc.
        match = re.match(r'^(\d+)([\s.-]+)', title)
        if match:
            # SAFETY: Check for decimals (e.g. "14.3 Billion Years")
            # If it's a dot followed by a digit, it's likely a decimal, not a separator.
            if match.group(2) == '.' and match.end() < len(title) and title[match.end()].isdigit():
                return title.strip()

            if track_number:
                prefixed_num = match.group(1).lstrip('0') or '0'
                clean_track_num = str(track_number).lstrip('0') or '0'
                
                # Only remove if it matches the actual track number (likely redundant)
                if prefixed_num == clean_track_num:
                    cleaned = title[match.end():].strip()
                    logger.debug(f"Cleaned redundant track number prefix: '{title}' -> '{cleaned}'")
                    return cleaned
        
        return title.strip()

    @staticmethod
    def build_tag_map(
        app_id: int, 
        disc: int, 
        clean_title: str, 
        adopted_info: Dict, 
        steam_meta: SteamMetadata, 
        instr: Dict, 
        mbz_candidates: List[Dict], 
        track_sources: Dict,
        user_language_639_2: str,
        global_identity: Dict[str, Any] = {}
    ) -> Dict[str, Any]:
        """
        Constructs the ID3v2.3 tag map based on merged sources and SST.md definitions.
        Ensures 'Locked Truth' from Steam is preserved.
        """
        res_title = clean_title
        res_artist = steam_meta.developer or "Unknown Artist"
        res_track = str(adopted_info.get("filename_track") or 0)
        res_disc = f"{disc}/1"
        
        action = instr.get("action", "use_local_tag")
        
        # 1. Resolve Identity
        if action == "use_mbz" and mbz_candidates:
            try:
                mbz_idx = instr.get("chosen_mbz_index")
                if mbz_idx is None or mbz_idx == -1: mbz_idx = 0

                mbz_album = mbz_candidates[mbz_idx]
                t_idx = instr.get("mbz_track_index")
                if t_idx is None: t_idx = 0

                if t_idx < len(mbz_album.get("tracks", [])):

                    mbz_track = mbz_album["tracks"][t_idx]
                    if isinstance(mbz_track, dict):
                        res_title = mbz_track.get("title", res_title)
                        res_track = str(mbz_track.get("position", res_track))
                    else:
                        res_title = str(mbz_track)
                
                res_artist = mbz_album.get("artist", res_artist)
                res_disc = f"{mbz_album.get('disc_number', disc)}/{mbz_album.get('total_discs', 1)}"
            except Exception as e:
                logger.debug(f"[{app_id}] MBZ resolution failed for {clean_title}: {e}")
        
        elif action == "use_local_tag":
            local_tags = {}
            tid = f"{disc}_{clean_title}"
            for s in track_sources.get(tid, []):
                if s["type"] == "embedded_merged":
                    local_tags = s.get("tags", {})
                    break
            res_title = local_tags.get("title", res_title)
            res_artist = local_tags.get("artist", res_artist)
            res_track = local_tags.get("track_number", res_track)
            res_disc = local_tags.get("disc_number", res_disc)

        # 2. Apply Overrides (LLM Correction)
        if instr.get("override_title"): res_title = instr["override_title"]
        if instr.get("override_track"): res_track = str(instr["override_track"])

        # 3. Final System-level Cleaning (The "Safety Net")
        # Even if LLM fails or sources are dirty, we enforce the 'No leading numbers' rule ONLY if it matches the track.
        res_title = MetadataBuilder._clean_title_logic(res_title, res_track)

        # 3. Genre logic
        all_genres = steam_meta.genres if steam_meta.genres else []
        if not all_genres and steam_meta.parent_genres:
            all_genres = steam_meta.parent_genres
        
        if all_genres:
            joined_genres = ", ".join(all_genres)
        else:
            joined_genres = steam_meta.genre or steam_meta.parent_genre or 'Soundtrack'
            
        final_genre = f"STEAM VGM, {joined_genres}"

        # 4. Comment/Grouping logic (Parent Game Reference)
        target_name = steam_meta.parent_name or steam_meta.name
        target_appid = steam_meta.parent_app_id or app_id
        
        # Use parent_tags as they are usually richer community tags (Topic 10)
        target_tags = steam_meta.parent_tags if steam_meta.parent_tags else steam_meta.tags
        joined_tags = "; ".join(target_tags) if target_tags else ""
        
        target_url = f"https://store.steampowered.com/app/{target_appid}"
        new_info = f"{target_name}, {joined_tags}, {target_appid}, {target_url}"

        # Merge with existing comment (Topic: Separator Change)
        tid = f"{disc}_{clean_title}"
        existing_comment = ""
        for s in track_sources.get(tid, []):
            if s["type"] == "embedded_merged":
                existing_comment = s.get("tags", {}).get("comment", "")
                break
        
        if existing_comment and str(existing_comment).strip():
            res_comment = f"{existing_comment}, {new_info}"
        else:
            res_comment = new_info
        
        # 5. Label Fallback (Topic 6)
        res_label = global_identity.get("canonical_label")
        if not res_label and mbz_candidates:
            res_label = mbz_candidates[0].get("label")
        if not res_label:
            res_label = f"{steam_meta.developer or steam_meta.publisher}"

        # 6. Year extraction (Topic 4/5)
        raw_date = instr.get("TDRC") or steam_meta.release_date or ""
        year_match = re.search(r'(\d{4})', str(raw_date))
        res_year = year_match.group(1) if year_match else "0000"

        # 7. Final Map Construction
        return {
            "title": (res_title or clean_title).strip(),
            "artist": res_artist.strip(),
            "album": steam_meta.name, # LOCKED
            "album_artist": f"{steam_meta.developer}, {steam_meta.publisher}", # SST.md 5
            "genre": final_genre,
            "label": res_label,
            "grouping": f"{target_name}, Steam",
            "comment": res_comment,
            "composer": instr.get("TCOM", steam_meta.developer or "Unknown"),
            "year": res_year,
            "track_number": str(res_track).split('/')[0].strip(),
            "disc_number": str(res_disc) if "/" in str(res_disc) else f"{res_disc}/1",
            "language": user_language_639_2,
            "mbid": mbz_candidates[0].get("mbid") if mbz_candidates else None,
            "steam_appid": app_id
        }

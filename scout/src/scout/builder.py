import logging
from typing import Dict, Any, List, Optional
from .models import SteamMetadata

logger = logging.getLogger("scout.builder")

class MetadataBuilder:
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
        user_language_639_2: str
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
                # Top pre-filtered candidate is the primary source
                mbz_album = mbz_candidates[0]
                t_idx = instr.get("mbz_track_index", 0)
                mbz_track = mbz_album["tracks"][t_idx]
                res_title = mbz_track.get("title", res_title)
                res_artist = mbz_track.get("artist", res_artist)
                res_track = str(mbz_track.get("position", res_track))
                res_disc = f"{mbz_album.get('disc_number', disc)}/{mbz_album.get('total_discs', 1)}"
            except Exception as e:
                logger.debug(f"MBZ resolution failed for {clean_title}: {e}")
        
        elif action == "use_local_tag":
            local_tags = {}
            tid = f"{disc}_{clean_title}"
            for s in track_sources.get(tid, []):
                if s["type"] == "embedded_merged":
                    local_tags = s.get("tags", {})
                    break
            res_title = local_tags.get("title", res_title)
            res_artist = local_tags.get("artist", res_artist)
            res_track = str(local_tags.get("track_number", res_track))
            res_disc = str(local_tags.get("disc_number", res_disc))

        # 2. Apply Overrides (LLM Correction)
        if instr.get("override_title"): res_title = instr["override_title"]
        if instr.get("override_track"): res_track = str(instr["override_track"])

        # 3. Genre logic
        raw_genre = instr.get("TCON", steam_meta.genre or steam_meta.parent_genre or 'Soundtrack')
        final_genre = raw_genre if raw_genre.startswith("STEAM VGM") else f"STEAM VGM, {raw_genre}"

        # 4. Comment/Grouping logic (Parent Game Reference)
        # Use soundtrack info as fallback if no parent exists
        target_name = steam_meta.parent_name or steam_meta.name
        target_appid = steam_meta.parent_app_id or app_id
        target_url = f"https://store.steampowered.com/app/{target_appid}"
        
        # 5. Final Map Construction
        return {
            "title": res_title.strip(),
            "artist": res_artist.strip(),
            "album": steam_meta.name, # LOCKED
            "album_artist": f"{steam_meta.developer}; {steam_meta.publisher}", # SST.md 5
            "genre": final_genre,
            "grouping": f"{target_name}; Steam",
            "comment": f"{target_name}; {', '.join(steam_meta.tags[:10])}; {target_appid}; {target_url}",
            "composer": instr.get("TCOM", steam_meta.developer or "Unknown"),
            "year": instr.get("TDRC", steam_meta.release_date[:4] if steam_meta.release_date else "0000"),
            "track_number": res_track.split('/')[0].strip(),
            "disc_number": res_disc if "/" in str(res_disc) else f"{res_disc}/1",
            "language": user_language_639_2,
            # Pass-through for audit
            "mbid": mbz_candidates[0].get("mbid") if mbz_candidates else None,
            "steam_appid": app_id
        }

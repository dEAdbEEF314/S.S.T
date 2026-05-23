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
        global_identity: Dict[str, Any] = {},
        priorities: Optional[Dict[str, str]] = None,
        total_discs: int = 1,
        vgmdb_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Constructs the ID3v2.3 tag map based on merged sources, SST.md definitions,
        and user-defined metadata priorities.
        Ensures 'Locked Truth' from Steam is preserved.
        """
        # Set default priorities if not passed
        if priorities is None:
            priorities = {
                "TIT2": "FILE,EMBED,VDF,VGMDB,MBZ,PICS_API",
                "TPE1": "EMBED,VGMDB,MBZ,PICS_API",
                "TRCK": "VGMDB,PICS_API,MBZ,FILE,EMBED",
                "TPOS": "VGMDB,PICS_API,EMBED,MBZ",
                "TYER": "EMBED,VGMDB,MBZ,WEB_API",
                "TPUB": "VGMDB,MBZ,PICS_API",
            }

        # --- 1. Prepare Data Extractors ---

        # EMBED (Media Embedded Data)
        local_tags = {}
        tid = f"{disc}_{clean_title}"
        for s in track_sources.get(tid, []):
            if s["type"] == "embedded_merged":
                local_tags = s.get("tags", {})
                break

        # MBZ (MusicBrainz Data)
        mbz_album = None
        mbz_track = None
        mbz_idx = instr.get("chosen_mbz_index")
        if mbz_idx is None or mbz_idx == -1: mbz_idx = 0
        if mbz_candidates and mbz_idx < len(mbz_candidates):
            mbz_album = mbz_candidates[mbz_idx]
            t_idx = instr.get("mbz_track_index")
            if t_idx is None: t_idx = 0
            if t_idx < len(mbz_album.get("tracks", [])):
                mbz_track = mbz_album["tracks"][t_idx]

        # PICS_API (Steam PICS Tracks Data)
        pics_track = None
        # Remove leading numbers and separators from clean_title for fuzzy matching (same as track_grouper)
        fuzzy_clean_title = re.sub(r'^(\d+[\s._-]+)+', '', clean_title)
        fuzzy_clean_title = re.sub(r'\.[a-zA-Z0-9]+$', '', fuzzy_clean_title) # Remove extension if any
        fuzzy_clean_title = re.sub(r'[^a-zA-Z0-9]', ' ', fuzzy_clean_title)
        fuzzy_clean_title = " ".join(fuzzy_clean_title.split()).lower()

        for t in steam_meta.store_tracklist:
            t_title = t.get("title", "")
            # Normalize store title in the same way TrackManager does for filenames
            norm_t_title = re.sub(r'[^a-zA-Z0-9]', ' ', t_title)
            norm_t_title = " ".join(norm_t_title.split()).lower()
            
            if norm_t_title == fuzzy_clean_title or fuzzy_clean_title.startswith(norm_t_title + " "):
                pics_track = t
                break
        with open("/tmp/builder_debug.log", "a") as dbgf:
            dbgf.write(f"\n--- {clean_title} ---\n")
            dbgf.write(f"fuzzy_clean_title: {fuzzy_clean_title}\n")
            if pics_track:
                dbgf.write(f"Matched PICS: {pics_track.get('title')} (Disc {pics_track.get('disc')})\n")
            else:
                dbgf.write("Matched PICS: NONE\n")

        # --- 2. Dynamic Priority Resolution with Fallback ---

        # 2.1 TIT2 (曲名)
        res_title = None
        tit2_priority = priorities.get("TIT2", "FILE,EMBED,VDF,VGMDB,MBZ,PICS_API")
        for src in tit2_priority.split(","):
            src = src.strip().upper()
            val = None
            if src == "FILE" and adopted_info.get("path"):
                val = adopted_info["path"].stem
            elif src == "EMBED":
                val = local_tags.get("title")
            elif src == "VDF":
                val = clean_title
            elif src == "VGMDB" and vgmdb_data:
                t_idx = instr.get("vgmdb_track_index")
                if t_idx: val = vgmdb_data["tracks"].get(t_idx)
            elif src == "MBZ" and mbz_track:
                val = mbz_track.get("title") if isinstance(mbz_track, dict) else str(mbz_track)
            elif src == "PICS_API" and pics_track:
                val = pics_track.get("title")
            
            if val and str(val).strip():
                res_title = str(val).strip()
                # Apply Plan B Truncation Logic (60 chars)
                if " / " in res_title and len(res_title) > 60:
                    # Preserving only the local (Japanese) part if combined is too long
                    parts = res_title.split(" / ", 1)
                    res_title = parts[0].strip()
                    logger.debug(f"Bilingual title truncated to local only (length > 60): {res_title}")
                break
        if not res_title:
            res_title = clean_title

        # 2.2 TPE1 (アーティスト)
        res_artist = None
        tpe1_priority = priorities.get("TPE1", "EMBED,VGMDB,MBZ,PICS_API")
        for src in tpe1_priority.split(","):
            src = src.strip().upper()
            val = None
            if src == "EMBED":
                val = local_tags.get("artist")
            elif src == "VGMDB" and vgmdb_data:
                val = vgmdb_data.get("artist_ja") or vgmdb_data.get("artist_en")
            elif src == "MBZ" and mbz_album:
                val = mbz_album.get("artist")
            elif src == "PICS_API":
                # Extract artist from store_credits if available
                if steam_meta.store_credits:
                    match = re.search(r'Artist:\s*(.*)', steam_meta.store_credits, re.IGNORECASE)
                    if match:
                        val = match.group(1).strip()
                if not val:
                    val = steam_meta.developer
            
            if val and str(val).strip():
                res_artist = str(val).strip()
                break
        if not res_artist:
            res_artist = steam_meta.developer or "Various Artists"

        # 2.3 TRCK (トラック番号)
        res_track = None
        trck_priority = priorities.get("TRCK", "VGMDB,PICS_API,MBZ,FILE,EMBED")
        for src in trck_priority.split(","):
            src = src.strip().upper()
            val = None
            if src == "VGMDB" and vgmdb_data:
                val = instr.get("vgmdb_track_index")
            elif src == "FILE":
                val = adopted_info.get("filename_track")
            elif src == "EMBED":
                val = local_tags.get("track_number")
            elif src == "MBZ" and mbz_track:
                val = mbz_track.get("position") if isinstance(mbz_track, dict) else None
            elif src == "PICS_API" and pics_track:
                val = pics_track.get("number")
            
            if val and str(val).strip() and str(val).strip() != "0":
                res_track = str(val).strip()
                break
        if not res_track:
            res_track = str(adopted_info.get("filename_track") or 0)

        # 2.4 TPOS (ディスク番号)
        res_disc = None
        tpos_priority = priorities.get("TPOS", "VGMDB,PICS_API,EMBED,MBZ")
        for src in tpos_priority.split(","):
            src = src.strip().upper()
            val = None
            if src == "VGMDB" and vgmdb_data:
                val = str(disc)
            elif src == "PICS_API" and pics_track:
                val = pics_track.get("disc")
            elif src == "EMBED":
                val = local_tags.get("disc_number")
            elif src == "MBZ" and mbz_album:
                # MBZ already provides disc/total format usually
                val = f"{mbz_album.get('disc_number', disc)}/{mbz_album.get('total_discs', 1)}"
            
            if val and str(val).strip() and str(val).strip() != "0":
                res_disc = str(val).strip()
                break
        
        # Determine logical total discs for the denominator
        actual_total_discs = total_discs
        if "/" in str(res_disc):
            parts = str(res_disc).split("/")
            res_disc = parts[0].strip()
            if len(parts) > 1:
                try:
                    explicit_total = int(parts[1].strip())
                    if explicit_total >= disc:
                        actual_total_discs = explicit_total
                except ValueError: pass

        if not res_disc:
            res_disc = str(disc)

        # 2.5 TYER (発売年)
        res_year = None
        tyer_priority = priorities.get("TYER", "EMBED,VGMDB,MBZ,WEB_API")
        for src in tyer_priority.split(","):
            src = src.strip().upper()
            val = None
            if src == "VGMDB" and vgmdb_data:
                val = vgmdb_data.get("year")
            elif src == "WEB_API":
                val = steam_meta.release_date
            elif src == "MBZ" and mbz_album:
                val = mbz_album.get("year")
            elif src == "EMBED":
                val = local_tags.get("year")
            
            if val:
                match = re.search(r'(\d{4})', str(val))
                if match:
                    res_year = match.group(1)
                    break
        if not res_year:
            raw_date = instr.get("TDRC") or steam_meta.release_date or ""
            match = re.search(r'(\d{4})', str(raw_date))
            res_year = match.group(1) if match else "0000"

        # 2.6 TPUB (レーベル)
        res_label = None
        tpub_priority = priorities.get("TPUB", "VGMDB,MBZ,PICS_API")
        for src in tpub_priority.split(","):
            src = src.strip().upper()
            val = None
            if src == "VGMDB" and vgmdb_data:
                dtitle = vgmdb_data.get("album_ja") or ""
                cat_match = re.search(r'\[([^\]]+)\]', dtitle)
                if cat_match: val = cat_match.group(1)
            elif src == "MBZ" and mbz_album:
                val = mbz_album.get("label")
            elif src == "PICS_API":
                val = steam_meta.label or global_identity.get("canonical_label") or steam_meta.publisher
            
            if val and str(val).strip() and str(val).strip() not in ["無", "none", "Unknown", "N/A"]:
                res_label = str(val).strip()
                break
        if not res_label:
            res_label = f"{steam_meta.developer or steam_meta.publisher}"

        # --- 3. Apply Overrides (LLM Correction) ---
        if instr.get("override_title"): res_title = instr["override_title"]
        if instr.get("override_track"): res_track = str(instr["override_track"])
        if instr.get("override_disc"): res_disc = str(instr["override_disc"])

        # --- 4. Final System-level Cleaning ---
        res_title = MetadataBuilder._clean_title_logic(res_title, res_track)

        # --- 5. Genre Logic ---
        all_genres = steam_meta.genres if steam_meta.genres else []
        if not all_genres and steam_meta.parent_genres:
            all_genres = steam_meta.parent_genres
        
        if all_genres:
            joined_genres = ", ".join(all_genres)
        else:
            joined_genres = steam_meta.genre or steam_meta.parent_genre or 'Soundtrack'
            
        final_genre = f"STEAM VGM, {joined_genres}"

        # --- 6. Comment/Grouping Logic (Parent Game Reference) ---
        target_name = steam_meta.parent_name or steam_meta.name
        target_appid = steam_meta.parent_app_id or app_id
        
        target_tags = steam_meta.parent_tags if steam_meta.parent_tags else steam_meta.tags
        joined_tags = f"[{'/ '.join(target_tags)}]" if target_tags else ""
        
        target_url = f"https://store.steampowered.com/app/{target_appid}"
        new_info = f"{target_name}, {joined_tags}, {target_appid}, {target_url}"

        # Merge with existing comment
        existing_comment = ""
        for s in track_sources.get(tid, []):
            if s["type"] == "embedded_merged":
                existing_comment = s.get("tags", {}).get("comment", "")
                break
        
        if existing_comment and str(existing_comment).strip():
            res_comment = f"{existing_comment}, {new_info}"
        else:
            res_comment = new_info

        # --- 7. Construct Final Map ---
        res_album = steam_meta.name
        if vgmdb_data:
            ja_alb = vgmdb_data.get("album_ja")
            en_alb = vgmdb_data.get("album_en")
            if ja_alb and en_alb and ja_alb != en_alb:
                # Use bilingual format for album as well
                res_album = f"{ja_alb} / {en_alb}"
            else:
                res_album = ja_alb or en_alb or steam_meta.name

        return {
            "title": (res_title or clean_title).strip(),
            "artist": res_artist.strip(),
            "album": res_album.strip(),
            "album_artist": f"{steam_meta.developer}, {steam_meta.publisher}", # SST.md 5
            "genre": final_genre,
            "label": res_label,
            "grouping": f"{target_name}, Steam",
            "comment": res_comment,
            "composer": instr.get("TCOM", steam_meta.developer or "Unknown"),
            "year": res_year,
            "track_number": str(res_track).split('/')[0].strip(),
            "disc_number": f"{res_disc}/{actual_total_discs}",
            "language": user_language_639_2,
            "mbid": mbz_candidates[0].get("mbid") if mbz_candidates else None,
            "steam_appid": app_id
        }


import logging
import re
from typing import Dict, Any, List, Optional, Union
from .config import DEFAULT_TITLE_CLEANING_TRUSTED_SOURCES
from .models import SteamMetadata

logger = logging.getLogger("sst.builder")

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
                    logger.debug(f"冗長なトラック番号のプレフィックスをクリーンアップしました: '{title}' -> '{cleaned}'")
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
        total_discs: int = 1
    ) -> Dict[str, Any]:
        """
        Constructs the ID3v2.3 tag map based on merged sources and simplified priority logic.
        Structure (Track Number, Title) is strictly trusted from Steam if available.
        Fallback to FINGERPRINT/MBZ for structure only when Steam is completely missing.
        Additional details (Artist, Composer, Year) are heavily augmented by MBZ.
        """
        # --- 1. Prepare Data Extractors ---
        local_tags = {}
        tid = f"{disc}_{clean_title}"
        for s in track_sources.get(tid, []):
            if s["type"] == "embedded_merged":
                local_tags = s.get("tags", {})
                break

        mbz_album = None
        mbz_track = None
        mbz_idx = instr.get("chosen_mbz_index")
        if mbz_idx is None or mbz_idx == -1: mbz_idx = 0
        if mbz_candidates and mbz_idx < len(mbz_candidates):
            mbz_album = mbz_candidates[mbz_idx]
            t_idx = instr.get("mbz_track_index")
            if t_idx is not None and t_idx < len(mbz_album.get("tracks", [])):
                mbz_track = mbz_album["tracks"][t_idx]
            else:
                mbz_track = None

        pics_track = None
        s_idx = instr.get("matched_v_idx")

        # 1. 常にSTEAM情報をGround Truthとするため、アクションに関わらず matched_v_idx があれば最優先で取得
        if s_idx is not None and s_idx >= 0 and s_idx < len(steam_meta.store_tracklist):
            pics_track = steam_meta.store_tracklist[s_idx]
        
        # 2. matched_v_idxが無くても、use_local以外ならSTEAMトラックリストからのファジーマッチを試みて補完する
        if not pics_track and instr.get("action") != "use_local":
            fuzzy_clean_title = re.sub(r'^(\d+[\s._-]+)+', '', clean_title)
            fuzzy_clean_title = re.sub(r'\.[a-zA-Z0-9]+$', '', fuzzy_clean_title)
            fuzzy_clean_title = re.sub(r'[^a-zA-Z0-9]', ' ', fuzzy_clean_title)
            fuzzy_clean_title = " ".join(fuzzy_clean_title.split()).lower()

            exact_match = None
            prefix_match = None
            for t in steam_meta.store_tracklist:
                t_title = t.get("title") or t.get("name", "")
                norm_t_title = re.sub(r'[^a-zA-Z0-9]', ' ', t_title)
                norm_t_title = " ".join(norm_t_title.split()).lower()
                
                if norm_t_title == fuzzy_clean_title:
                    exact_match = t
                    break
                if not prefix_match and fuzzy_clean_title.startswith(norm_t_title + " "):
                    prefix_match = t
            
            pics_track = exact_match or prefix_match

        # --- 2. Dynamic Priority Resolution ---

        # 2.1 TIT2 (Title)
        res_title = None
        chosen_src = "VDF"
        
        # Absolute priority: Steam (Ground Truth) -> LLM Override -> MBZ/Fingerprint -> Local
        if pics_track:
            res_title = pics_track.get("title") or pics_track.get("name")
            chosen_src = "PICS_API"
        elif instr.get("override_title"):
            res_title = instr.get("override_title")
            chosen_src = "LLM_OVERRIDE"
        elif mbz_track:
            res_title = mbz_track.get("title") if isinstance(mbz_track, dict) else str(mbz_track)
            chosen_src = "MBZ"
        elif local_tags.get("title"):
            res_title = local_tags.get("title")
            chosen_src = "EMBED"
        else:
            res_title = clean_title

        res_title = res_title or clean_title
        if " / " in res_title and len(res_title) > 60:
            res_title = res_title.split(" / ", 1)[0].strip()

        res_title = MetadataBuilder._clean_title_logic(res_title, instr.get("override_track"))

        # 2.2 TPE1 (Artist)
        res_artist = None
        # MBZ details take priority if available, otherwise Steam Credits, then Local, then Steam Developer
        if mbz_album and mbz_album.get("artist"):
            res_artist = mbz_album.get("artist")
        elif steam_meta.store_credits:
            match = re.search(r'Artist:\s*(.*)', steam_meta.store_credits, re.IGNORECASE)
            if match: res_artist = match.group(1).strip()
        
        if not res_artist:
            res_artist = local_tags.get("artist") or steam_meta.developer or "Various Artists"

        # 2.3 TRCK (Track Number)
        res_track = ""
        if pics_track and pics_track.get("number"):
            res_track = str(pics_track.get("number"))
        elif instr.get("override_track") and str(instr.get("override_track")) != "0":
            res_track = str(instr.get("override_track"))
        elif mbz_track:
            val = mbz_track.get("position") or mbz_track.get("track_num")
            if val: res_track = str(val)
        
        if not res_track or res_track == "0":
            res_track = str(adopted_info.get("filename_track") or 0)

        # 2.4 TPOS (Disc Number)
        res_disc = ""
        if pics_track and pics_track.get("disc"):
            res_disc = str(pics_track.get("disc"))
        elif instr.get("override_disc") and str(instr.get("override_disc")) != "0":
            res_disc = str(instr.get("override_disc"))
        elif mbz_track:
            res_disc = str(mbz_track.get("disc", disc))
        else:
            res_disc = str(disc)
                
        actual_total_discs = total_discs
        if "/" in str(res_disc):
            parts = str(res_disc).split("/")
            res_disc = parts[0].strip()
            if len(parts) > 1:
                try: actual_total_discs = max(actual_total_discs, int(parts[1].strip()))
                except ValueError: pass

        if not res_disc: res_disc = str(disc)
        try: actual_total_discs = max(actual_total_discs, int(res_disc))
        except ValueError: pass

        # 2.5 TYER (Year)
        res_year = None
        if mbz_album and mbz_album.get("year"):
            match = re.search(r'(\d{4})', str(mbz_album.get("year")))
            if match: res_year = match.group(1)
            
        if not res_year:
            raw_date = steam_meta.release_date or local_tags.get("year") or ""
            match = re.search(r'(\d{4})', str(raw_date))
            res_year = match.group(1) if match else "0000"

        # 2.6 TPUB (Label)
        res_label = None
        if mbz_album and mbz_album.get("label") and mbz_album.get("label") not in ["無", "none", "Unknown", "N/A"]:
            res_label = mbz_album.get("label")
        else:
            val = steam_meta.label or global_identity.get("canonical_label") or steam_meta.publisher
            if val and val not in ["無", "none", "Unknown", "N/A"]:
                res_label = val
                
        if not res_label:
            res_label = f"{steam_meta.developer or steam_meta.publisher}"

        # 2.7 TCOM (Composer)
        res_composer = instr.get("composer") or instr.get("TCOM")
        if not res_composer or res_composer == "Unknown":
            if steam_meta.store_credits:
                patterns = [r'Composer:\s*(.*)', r'Music by\s*(.*)', r'Music:\s*(.*)', r'Sound by\s*(.*)', r'Soundtrack by\s*(.*)']
                for p in patterns:
                    match = re.search(p, steam_meta.store_credits, re.IGNORECASE)
                    if match:
                        res_composer = match.group(1).split('\n')[0].strip()
                        break
        
        if not res_composer:
            res_composer = steam_meta.developer or "Unknown"

        # --- 3. Final System-level Cleaning (Trust Tier Logic) ---
        trusted_sources = [s.strip().upper() for s in DEFAULT_TITLE_CLEANING_TRUSTED_SOURCES.split(",")]
        
        if chosen_src not in trusted_sources:
            res_title = MetadataBuilder._clean_title_logic(res_title, res_track)
        else:
            logger.debug(f"信頼できるソースのタイトルクリーンアップをスキップします: {chosen_src} ('{res_title}')")

        # --- 4. Genre Logic ---
        all_genres = steam_meta.genres if steam_meta.genres else []
        if not all_genres and steam_meta.parent_genres:
            all_genres = steam_meta.parent_genres
        
        if all_genres:
            joined_genres = ", ".join(all_genres)
        else:
            joined_genres = steam_meta.genre or steam_meta.parent_genre or 'Soundtrack'
            
        final_genre = f"STEAM VGM, {joined_genres}"

        # --- 5. Comment/Grouping Logic ---
        target_name = steam_meta.parent_name or steam_meta.name
        target_appid = steam_meta.parent_app_id or app_id
        
        target_tags = steam_meta.parent_tags if steam_meta.parent_tags else steam_meta.tags
        joined_tags = f"[{'/ '.join(target_tags)}]" if target_tags else ""
        
        target_url = f"https://store.steampowered.com/app/{target_appid}"
        new_info = f"{target_name}, {joined_tags}, {target_appid}, {target_url}"

        existing_comment = local_tags.get("comment", "")
        if existing_comment and str(existing_comment).strip():
            res_comment = f"{existing_comment}, {new_info}"
        else:
            res_comment = new_info

        # --- 6. Construct Final Map ---
        return {
            "title": (res_title or clean_title).strip(),
            "artist": res_artist.strip(),
            "album": steam_meta.name.strip(),
            "album_artist": f"{steam_meta.developer}, {steam_meta.publisher}",
            "genre": final_genre,
            "label": res_label.strip() if res_label else "",
            "grouping": f"{target_name}, Steam",
            "comment": res_comment,
            "composer": res_composer,
            "year": res_year,
            "track_number": str(res_track).split('/')[0].strip(),
            "disc_number": f"{res_disc}/{actual_total_discs}",
            "language": user_language_639_2,
            "mbid": mbz_candidates[0].get("mbid") if mbz_candidates else None,
            "steam_appid": app_id,
            "title_source": chosen_src
        }


import logging
import re
from typing import Dict, Any, List, Optional
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
        priorities: Optional[Dict[str, str]] = None,
        total_discs: int = 1
    ) -> Dict[str, Any]:
        """
        Constructs the ID3v2.3 tag map based on merged sources, SST.md definitions,
        and user-defined metadata priorities.
        Ensures 'Locked Truth' from Steam is preserved.
        """
        # Set default priorities if not passed
        if priorities is None:
            priorities = {
                "TIT2": "FILE,EMBED,VDF,MBZ,PICS_API",
                "TPE1": "EMBED,MBZ,PICS_API",
                "TRCK": "PICS_API,MBZ,FILE,EMBED",
                "TPOS": "PICS_API,EMBED,MBZ",
                "TYER": "EMBED,MBZ,WEB_API",
                "TPUB": "MBZ,PICS_API",
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
            
            # Use matched_v_idx from LLM if action is use_fingerprint
            t_idx = None
            if instr.get("action") == "use_fingerprint":
                t_idx = instr.get("matched_v_idx")
            else:
                t_idx = instr.get("mbz_track_index")

            if t_idx is not None and t_idx < len(mbz_album.get("tracks", [])):
                mbz_track = mbz_album["tracks"][t_idx]
            else:
                if t_idx is not None:
                    logger.warning(f"[{app_id}] MBZトラックインデックス {t_idx} が範囲外です (最大: {len(mbz_album.get('tracks', []))-1})")
                mbz_track = None

        # PICS_API (Steam PICS Tracks Data)
        pics_track = None
        
        # Use matched_v_idx from LLM if action is use_steam
        # RELAXED HEURISTIC: If LLM suggested use_fingerprint but there's no MBZ track found
        # (common hallucination when fingerprint is missing), try using it as a Steam index.
        s_idx = instr.get("matched_v_idx")
        is_steam_action = (instr.get("action") == "use_steam")
        is_misidentified_fingerprint = (instr.get("action") == "use_fingerprint" and not mbz_track)

        if (is_steam_action or is_misidentified_fingerprint) and s_idx is not None:
            if s_idx < len(steam_meta.store_tracklist):
                pics_track = steam_meta.store_tracklist[s_idx]
                if is_misidentified_fingerprint:
                    logger.debug(f"[{app_id}] トラック '{clean_title}' の誤認識されたフィンガープリントアクションをSteamインデックス {s_idx} に修正しました")
        
        if not pics_track:
            # Fallback to fuzzy matching
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

        with open("/tmp/builder_debug.log", "a") as dbgf:
            dbgf.write(f"\n--- {clean_title} ---\n")
            if pics_track:
                dbgf.write(f"Matched PICS: {pics_track.get('title')} (Disc {pics_track.get('disc')})\n")
            else:
                dbgf.write("Matched PICS: NONE\n")

        # --- 2. Dynamic Priority Resolution with Fallback ---

        # 2.1 TIT2 (曲名)
        res_title = instr.get("override_title")
        chosen_src = "LLM_OVERRIDE" if res_title else "VDF"
        
        if not res_title:
            tit2_priority = priorities.get("TIT2", "FILE,EMBED,VDF,MBZ,PICS_API")
            for src in tit2_priority.split(","):
                src = src.strip().upper()
                val = None
                if src == "FILE" and adopted_info.get("path"):
                    val = adopted_info["path"].stem
                elif src == "EMBED":
                    val = local_tags.get("title")
                elif src == "VDF":
                    val = clean_title
                elif src == "MBZ" and mbz_track:
                    val = mbz_track.get("title") if isinstance(mbz_track, dict) else str(mbz_track)
                elif src == "PICS_API" and pics_track:
                    val = pics_track.get("title") or pics_track.get("name")
                
                if val and str(val).strip():
                    res_title = str(val).strip()
                    chosen_src = src
                    # Apply Plan B Truncation Logic (60 chars)
                    if " / " in res_title and len(res_title) > 60:
                        parts = res_title.split(" / ", 1)
                        res_title = parts[0].strip()
                        logger.debug(f"バイリンガルタイトルがローカルのみに切り詰められました (長さ > 60): {res_title}")
                    break
        
        if not res_title:
            res_title = clean_title
            chosen_src = "VDF"
            
        res_title = MetadataBuilder._clean_title_logic(res_title, instr.get("override_track"))

        # 2.2 TPE1 (アーティスト)
        res_artist = None
        tpe1_priority = priorities.get("TPE1", "EMBED,MBZ,PICS_API")
        for src in tpe1_priority.split(","):
            src = src.strip().upper()
            val = None
            if src == "EMBED":
                val = local_tags.get("artist")
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
        res_track = str(instr.get("override_track") or "")
        if not res_track or res_track == "0":
            trck_priority = priorities.get("TRCK", "PICS_API,MBZ,FILE,EMBED")
            for src in trck_priority.split(","):
                src = src.strip().upper()
                val = None
                if src == "FILE":
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
        if not res_track or res_track == "0":
            res_track = str(adopted_info.get("filename_track") or 0)

        # 2.4 TPOS (ディスク番号)
        res_disc = str(instr.get("override_disc") or "")
        if not res_disc or res_disc == "0":
            tpos_priority = priorities.get("TPOS", "PICS_API,EMBED,MBZ")
            for src in tpos_priority.split(","):
                src = src.strip().upper()
                val = None
                if src == "PICS_API" and pics_track:
                    val = pics_track.get("disc")
                elif src == "EMBED":
                    val = local_tags.get("disc_number")
                elif src == "MBZ" and mbz_track:
                    val = str(mbz_track.get("disc", disc))
                
                if val and str(val).strip() and str(val).strip() != "0":
                    res_disc = str(val).strip()
                    break
        
        if not res_disc or res_disc == "0":
            res_disc = str(disc)
        
        # Determine logical total discs for the denominator
        actual_total_discs = total_discs
        if "/" in str(res_disc):
            parts = str(res_disc).split("/")
            res_disc = parts[0].strip()
            if len(parts) > 1:
                try:
                    explicit_total = int(parts[1].strip())
                    actual_total_discs = max(actual_total_discs, explicit_total)
                except ValueError: pass

        if not res_disc:
            res_disc = str(disc)
        
        # FINAL SAFETY: If res_disc is a number, ensure denominator is at least that number
        try:
            d_num = int(res_disc)
            actual_total_discs = max(actual_total_discs, d_num)
        except ValueError: pass

        # 2.5 TYER (発売年)
        res_year = None
        tyer_priority = priorities.get("TYER", "EMBED,MBZ,WEB_API")
        for src in tyer_priority.split(","):
            src = src.strip().upper()
            val = None
            if src == "WEB_API":
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
        tpub_priority = priorities.get("TPUB", "MBZ,PICS_API")
        for src in tpub_priority.split(","):
            src = src.strip().upper()
            val = None
            if src == "MBZ" and mbz_album:
                val = mbz_album.get("label")
            elif src == "PICS_API":
                val = steam_meta.label or global_identity.get("canonical_label") or steam_meta.publisher
            
            if val and str(val).strip() and str(val).strip() not in ["無", "none", "Unknown", "N/A"]:
                res_label = str(val).strip()
                break
        if not res_label:
            res_label = f"{steam_meta.developer or steam_meta.publisher}"

        # 2.7 TCOM (作曲者)
        res_composer = instr.get("composer") or instr.get("TCOM")
        if not res_composer or res_composer == "Unknown":
            # Fallback to regex extraction from Steam credits
            if steam_meta.store_credits:
                # Common patterns in Steam credits: "Composer: XXX", "Music by XXX", etc.
                patterns = [
                    r'Composer:\s*(.*)',
                    r'Music by\s*(.*)',
                    r'Music:\s*(.*)',
                    r'Sound by\s*(.*)',
                    r'Soundtrack by\s*(.*)'
                ]
                for p in patterns:
                    match = re.search(p, steam_meta.store_credits, re.IGNORECASE)
                    if match:
                        res_composer = match.group(1).split('\n')[0].strip()
                        break
        
        if not res_composer:
            res_composer = steam_meta.developer or "Unknown"

        # --- 3. Apply Overrides (LLM Correction) ---
        if instr.get("override_title"):
            res_title = instr["override_title"]
            chosen_src = "LLM_OVERRIDE" # LLM is untrusted by system logic for final cleaning
            
        if instr.get("override_track"): res_track = str(instr["override_track"])
        if instr.get("override_disc"): res_disc = str(instr["override_disc"])

        # --- 4. Final System-level Cleaning (Trust Tier Logic) ---
        trusted_sources = [s.strip().upper() for s in (priorities.get("TRUSTED_TITLE_SOURCES") or "MBZ,PICS_API").split(",")]
        
        if chosen_src not in trusted_sources:
            res_title = MetadataBuilder._clean_title_logic(res_title, res_track)
        else:
            logger.debug(f"信頼できるソースのタイトルクリーンアップをスキップします: {chosen_src} ('{res_title}')")

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

        return {
            "title": (res_title or clean_title).strip(),
            "artist": res_artist.strip(),
            "album": res_album.strip(),
            "album_artist": f"{steam_meta.developer}, {steam_meta.publisher}", # SST.md 5
            "genre": final_genre,
            "label": res_label,
            "grouping": f"{target_name}, Steam",
            "comment": res_comment,
            "composer": res_composer,
            "year": res_year,
            "track_number": str(res_track).split('/')[0].strip(),
            "disc_number": f"{res_disc}/{actual_total_discs}",
            "language": user_language_639_2,
            "mbid": mbz_candidates[0].get("mbid") if mbz_candidates else None,
            "steam_appid": app_id
        }


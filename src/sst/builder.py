import logging
import re
import html
from typing import Dict, Any, List, Optional, Union
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
        slot_embedded_tags: Optional[Dict[str, Any]] = None,
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
        local_tags = dict(slot_embedded_tags or {})
        tid = f"{disc}_{clean_title}"
        for s in track_sources.get(tid, []):
            if s["type"] == "embedded_merged":
                for key, value in s.get("tags", {}).items():
                    if key not in local_tags and value:
                        local_tags[key] = value

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
            
        # Check if Steam track numbering is broken (massive duplicates or zeros)
        is_steam_numbering_broken = False
        if steam_meta and steam_meta.store_tracklist:
            numbers = [str(t.get("number", "0")) for t in steam_meta.store_tracklist]
            zeros = numbers.count("0")
            if len(numbers) > 1:
                from collections import Counter
                most_common_num, count = Counter(numbers).most_common(1)[0]
                if count >= len(numbers) * 0.5 or zeros >= len(numbers) * 0.5:
                    is_steam_numbering_broken = True
            elif len(numbers) == 1 and zeros == 1:
                is_steam_numbering_broken = True
        
        # 2. matched_v_idxが無くても、STEAMトラックリストからのファジーマッチを試みて補完する
        if not pics_track and instr.get("matched_v_idx") is None:
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
        
        # Absolute priority: Steam (Ground Truth) -> MBZ/AcoustID evidence -> EMBED -> LOCAL
        if pics_track:
            res_title = pics_track.get("title") or pics_track.get("name")
            chosen_src = "STEAM"
        elif mbz_track:
            res_title = mbz_track.get("title") if isinstance(mbz_track, dict) else str(mbz_track)
            chosen_src = "MBZ_RELEASE"
        elif local_tags.get("title"):
            res_title = local_tags.get("title")
            chosen_src = "EMBED"
        else:
            res_title = clean_title.split("::")[0] if "::" in clean_title else clean_title
            chosen_src = "LOCAL"

        clean_fallback = clean_title.split("::")[0] if "::" in clean_title else clean_title
        res_title = res_title or clean_fallback
        if " / " in res_title and len(res_title) > 60:
            res_title = res_title.split(" / ", 1)[0].strip()

        # 2.2 TPE1 (Artist)
        # Priority: ACOUSTID recording artist -> MBZ release artist -> Steam Credits -> Developer
        res_artist = None
        if mbz_track and isinstance(mbz_track, dict) and (mbz_track.get("recording_artist") or mbz_track.get("artist_credit")):
            res_artist = mbz_track.get("recording_artist") or mbz_track.get("artist_credit")
        if mbz_album and mbz_album.get("artist"):
            res_artist = res_artist or mbz_album.get("artist")
        if not res_artist and steam_meta.store_credits:
            match = re.search(r'Artist:\s*(.*)', steam_meta.store_credits, re.IGNORECASE)
            if match: res_artist = match.group(1).strip()
        
        # Fallback: Developer (when missing or generic placeholder)
        if not res_artist or res_artist.lower() in ["various artists", "va", "various"]:
            res_artist = steam_meta.developer or "Unknown Artist"

        # 2.3 TRCK (Track Number)
        res_track = ""
        if pics_track and pics_track.get("number") and not is_steam_numbering_broken:
            res_track = str(pics_track.get("number"))
        elif instr.get("override_track") and str(instr.get("override_track")) != "0" and not is_steam_numbering_broken:
            res_track = str(instr.get("override_track"))
        elif instr.get("matched_v_idx") is not None:
            res_track = str(int(instr.get("matched_v_idx")) + 1)
        elif mbz_track:
            val = mbz_track.get("position") or mbz_track.get("track_num")
            if val: res_track = str(val)
            
        if not res_track or res_track == "0":
            local_track = str(local_tags.get("track_number") or "0").split('/')[0].strip()
            if local_track != "0":
                res_track = local_track
        
        if not res_track or res_track == "0":
            res_track = str(adopted_info.get("filename_track") or 0)

        if not res_track or res_track == "0":
            if s_idx is not None and s_idx >= 0:
                res_track = str(s_idx + 1)

        if not res_track or res_track == "0":
            res_track = "1"

        # 2.4 TPOS (Disc Number)
        res_disc = ""
        if pics_track and pics_track.get("disc"):
            res_disc = str(pics_track.get("disc"))
        elif instr.get("override_disc") and str(instr.get("override_disc")) != "0":
            res_disc = str(instr.get("override_disc"))
        elif local_tags.get("disc_number"):
            res_disc = str(local_tags.get("disc_number"))
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
        raw_date = steam_meta.release_date or ""
        if raw_date:
            match = re.search(r'(\d{4})', str(raw_date))
            res_year = match.group(1) if match else "0000"

        if not res_year and mbz_album and mbz_album.get("year"):
            match = re.search(r'(\d{4})', str(mbz_album.get("year")))
            if match:
                res_year = match.group(1)

        if not res_year:
            raw_date = local_tags.get("year") or ""
            match = re.search(r'(\d{4})', str(raw_date))
            res_year = match.group(1) if match else "0000"

        # 2.6 TPUB (Retired field)
        res_label = None
        if mbz_album and mbz_album.get("label") and mbz_album.get("label") not in ["無", "none", "Unknown", "N/A"]:
            res_label = mbz_album.get("label")
        elif global_identity.get("canonical_label") and global_identity.get("canonical_label") not in ["無", "none", "Unknown", "N/A"]:
            res_label = global_identity.get("canonical_label")

        # 2.7 TCOM (Composer): STEAM credits are authoritative; LLM output is not.
        res_composer = None
        if steam_meta.store_credits:
            patterns = [r'Composer:\s*(.*)', r'Music by\s*(.*)', r'Music:\s*(.*)', r'Sound by\s*(.*)', r'Soundtrack by\s*(.*)']
            for p in patterns:
                match = re.search(p, steam_meta.store_credits, re.IGNORECASE)
                if match:
                    res_composer = match.group(1).split('\n')[0].strip()
                    break
        if not res_composer and mbz_track and isinstance(mbz_track, dict) and mbz_track.get("recording_artist"):
            res_composer = mbz_track.get("recording_artist")
        if not res_composer and local_tags.get("composer"):
            res_composer = str(local_tags.get("composer"))
        if not res_composer and local_tags.get("artist"):
            res_composer = str(local_tags.get("artist"))
        
        if not res_composer:
            res_composer = steam_meta.developer or "Unknown"

        # --- 3. Genre Logic ---
        all_genres = steam_meta.genres if steam_meta.genres else []
        if not all_genres and steam_meta.parent_genres:
            all_genres = steam_meta.parent_genres
        
        if all_genres:
            joined_genres = ", ".join(all_genres)
        else:
            joined_genres = steam_meta.genre or steam_meta.parent_genre or 'Soundtrack'
            
        final_genre = f"STEAM VGM, {joined_genres}"

        # --- 4. Comment/Grouping Logic ---
        # TAGGING_RULE.md COMM spec: 既存の埋め込みコメント(先頭保持) + "親ゲーム名, 親ゲームストアURL, [タグ1/ タグ2/ ...]"
        target_name = steam_meta.parent_name or steam_meta.name
        target_appid = steam_meta.parent_app_id or app_id
        
        target_tags = steam_meta.parent_tags if steam_meta.parent_tags else steam_meta.tags
        target_url = f"https://store.steampowered.com/app/{target_appid}"
        new_info_parts = [target_name, target_url]
        new_info_parts.append(f"[{'/ '.join(target_tags)}]")
        new_info = ", ".join(new_info_parts)

        existing_comment = local_tags.get("comment", "")
        if existing_comment and str(existing_comment).strip():
            res_comment = f"{existing_comment}, {new_info}"
        else:
            res_comment = new_info

        # --- 5. Construct Final Map ---
        def _u(val):
            return html.unescape(str(val)) if val is not None else ""

        album_artist_parts = [_u(part).strip() for part in [steam_meta.developer, steam_meta.publisher] if part]
        clean_fallback_title = clean_title.split("::")[0] if "::" in clean_title else clean_title

        return {
            "title": _u(res_title or clean_fallback_title).strip(),
            "artist": _u(res_artist).strip(),
            "album": _u(steam_meta.name).strip(),
            "album_artist": ", ".join(album_artist_parts),
            "genre": final_genre,
            "label": "",
            "grouping": _u(f"{target_name}, Steam"),
            "comment": _u(res_comment),
            "composer": _u(res_composer),
            "year": res_year,
            "track_number": str(res_track).split('/')[0].strip(),
            "disc_number": f"{res_disc}/{actual_total_discs}",
            "language": user_language_639_2,
            "mbid": mbz_candidates[0].get("mbid") if mbz_candidates else None,
            "steam_appid": app_id,
            "title_source": chosen_src
        }


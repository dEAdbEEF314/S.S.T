import logging
import re
import html
from typing import Dict, Any, List, Optional
from .models import SteamMetadata

logger = logging.getLogger("sst.builder")

class MetadataBuilder:
    @staticmethod
    def _clean_title_logic(title: str, track_number: Optional[str] = None) -> str:
        if not title:
            return ""
        
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
        Structure (Track Number, Title) is strictly trusted from Steam if available,
        except for a fully verified MBZ release linked to this exact Steam AppID.
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
        if mbz_idx is None or mbz_idx == -1:
            mbz_idx = 0
        if mbz_candidates and mbz_idx < len(mbz_candidates):
            mbz_album = mbz_candidates[mbz_idx]
            t_idx = instr.get("mbz_track_index")
            if t_idx is not None and t_idx < len(mbz_album.get("tracks", [])):
                mbz_track = mbz_album["tracks"][t_idx]
            else:
                mbz_track = None
        verified_mbz_authority = bool(
            mbz_album and mbz_album.get("steam_link_verified")
        )

        pics_track = None
        s_idx = instr.get("matched_v_idx")

        # The effective tracklist is Steam's, except in the verified-MBZ route where
        # the processor supplies the MBZ release tracklist as the canonical structure.
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
        
        # A fully fingerprint-verified direct Steam link overrides Steam's incomplete
        # tracklist; otherwise Steam remains the structural ground truth.
        if verified_mbz_authority and mbz_track:
            res_title = mbz_track.get("title")
            chosen_src = "MBZ_STEAM_VERIFIED"
        elif pics_track:
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
        if chosen_src not in {"STEAM", "MBZ_STEAM_VERIFIED"} and " / " in res_title and len(res_title) > 60:
            res_title = res_title.split(" / ", 1)[0].strip()

        # 2.2 TPE1 (Artist)
        # Priority: ACOUSTID recording artist -> MBZ release artist -> Steam Credits -> Developer
        res_artist = None
        artist_source = "UNKNOWN"
        if instr.get("mbz_track_artist"):
            res_artist = instr["mbz_track_artist"]
            artist_source = "MBZ_STEAM_VERIFIED" if verified_mbz_authority else "MBZ_RECORDING_CREDIT"
        if not res_artist and mbz_track and isinstance(mbz_track, dict) and (mbz_track.get("recording_artist") or mbz_track.get("artist_credit")):
            res_artist = mbz_track.get("recording_artist") or mbz_track.get("artist_credit")
            artist_source = "MBZ_STEAM_VERIFIED" if verified_mbz_authority else "MBZ_RELEASE"
        if mbz_album and mbz_album.get("artist"):
            if not res_artist:
                res_artist = mbz_album.get("artist")
                artist_source = "MBZ_STEAM_VERIFIED" if verified_mbz_authority else "MBZ_RELEASE"
        if not res_artist and steam_meta.store_credits:
            match = re.search(r'Artist:\s*(.*)', steam_meta.store_credits, re.IGNORECASE)
            if match:
                res_artist = match.group(1).strip()
                artist_source = "STEAM_STORE_CREDITS"
        
        # Fallback: Developer (when missing or generic placeholder)
        if not res_artist or res_artist.lower() in ["various artists", "va", "various"]:
            res_artist = steam_meta.developer or "Unknown Artist"
            artist_source = "STEAM_DEVELOPER" if steam_meta.developer else "UNKNOWN_PLACEHOLDER"

        # 2.3 TRCK (Track Number)
        res_track = ""
        track_number_source = "UNKNOWN"
        matched_v_idx = instr.get("matched_v_idx")
        if verified_mbz_authority and mbz_track:
            res_track = str(mbz_track.get("position") or mbz_track.get("track_num") or "")
            track_number_source = "MBZ_STEAM_VERIFIED"
        elif pics_track and pics_track.get("number") and not is_steam_numbering_broken:
            res_track = str(pics_track.get("number"))
            track_number_source = "STEAM"
        elif instr.get("override_track") and str(instr.get("override_track")) != "0" and not is_steam_numbering_broken:
            res_track = str(instr.get("override_track"))
            track_number_source = "STEAM_ALIGNMENT"
        elif matched_v_idx is not None:
            res_track = str(int(matched_v_idx) + 1)
            track_number_source = "STEAM_SLOT_INDEX"
        elif mbz_track:
            val = mbz_track.get("position") or mbz_track.get("track_num")
            if val:
                res_track = str(val)
                track_number_source = "MBZ_RELEASE"
            
        if not res_track or res_track == "0":
            local_track = str(local_tags.get("track_number") or "0").split('/')[0].strip()
            if local_track != "0":
                res_track = local_track
                track_number_source = "EMBED"
        
        if not res_track or res_track == "0":
            res_track = str(adopted_info.get("filename_track") or 0)
            if res_track != "0":
                track_number_source = "LOCAL"

        if not res_track or res_track == "0":
            if s_idx is not None and s_idx >= 0:
                res_track = str(s_idx + 1)
                track_number_source = "STEAM_SLOT_INDEX"

        if not res_track or res_track == "0":
            res_track = "1"
            track_number_source = "DEFAULT_PLACEHOLDER"

        # 2.4 TPOS (Disc Number)
        res_disc = ""
        disc_number_source = "UNKNOWN"
        if verified_mbz_authority and mbz_track:
            res_disc = str(mbz_track.get("disc", disc))
            disc_number_source = "MBZ_STEAM_VERIFIED"
        elif pics_track and pics_track.get("disc"):
            res_disc = str(pics_track.get("disc"))
            disc_number_source = "STEAM"
        elif instr.get("override_disc") and str(instr.get("override_disc")) != "0":
            res_disc = str(instr.get("override_disc"))
            disc_number_source = "STEAM_ALIGNMENT"
        elif local_tags.get("disc_number"):
            res_disc = str(local_tags.get("disc_number"))
            disc_number_source = "EMBED"
        elif mbz_track:
            res_disc = str(mbz_track.get("disc", disc))
            disc_number_source = "MBZ_RELEASE"
        else:
            res_disc = str(disc)
            disc_number_source = "LOCAL_STRUCTURE"
                
        actual_total_discs = total_discs
        if "/" in str(res_disc):
            parts = str(res_disc).split("/")
            res_disc = parts[0].strip()
            if len(parts) > 1:
                try:
                    actual_total_discs = max(actual_total_discs, int(parts[1].strip()))
                except ValueError:
                    pass

        if not res_disc:
            res_disc = str(disc)
        try:
            actual_total_discs = max(actual_total_discs, int(res_disc))
        except ValueError:
            pass

        # 2.5 TYER (Year)
        res_year = None
        year_source = "UNKNOWN"
        raw_date = steam_meta.release_date or ""
        if verified_mbz_authority and mbz_album and mbz_album.get("year"):
            raw_date = str(mbz_album["year"])
            year_source = "MBZ_STEAM_VERIFIED"
        if raw_date:
            match = re.search(r'(\d{4})', str(raw_date))
            res_year = match.group(1) if match else "0000"
            if year_source == "UNKNOWN":
                year_source = "STEAM"

        if not res_year and mbz_album and mbz_album.get("year"):
            match = re.search(r'(\d{4})', str(mbz_album.get("year")))
            if match:
                res_year = match.group(1)
                year_source = "MBZ_RELEASE"

        if not res_year:
            raw_date = local_tags.get("year") or ""
            match = re.search(r'(\d{4})', str(raw_date))
            res_year = match.group(1) if match else "0000"
            year_source = "EMBED" if match else "UNKNOWN_PLACEHOLDER"
        if res_year == "0000":
            year_source = "UNKNOWN_PLACEHOLDER"

        # 2.6 TPUB (Retired field per METADATA_SOURCE_SPEC.md - not exported to final tags)

        # 2.7 TCOM (Composer): STEAM credits are authoritative; LLM output is not.
        res_composer = None
        composer_source = "UNKNOWN"
        if steam_meta.store_credits:
            patterns = [r'Composer:\s*(.*)', r'Music by\s*(.*)', r'Music:\s*(.*)', r'Sound by\s*(.*)', r'Soundtrack by\s*(.*)']
            for p in patterns:
                match = re.search(p, steam_meta.store_credits, re.IGNORECASE)
                if match:
                    res_composer = match.group(1).split('\n')[0].strip()
                    composer_source = "STEAM_STORE_CREDITS"
                    break
        if not res_composer and mbz_track and isinstance(mbz_track, dict) and mbz_track.get("recording_artist"):
            res_composer = mbz_track.get("recording_artist")
            composer_source = "MBZ_STEAM_VERIFIED" if verified_mbz_authority else "MBZ_RELEASE"
        if not res_composer and local_tags.get("composer"):
            res_composer = str(local_tags.get("composer"))
            composer_source = "EMBED_COMPOSER"
        if not res_composer and local_tags.get("artist"):
            res_composer = str(local_tags.get("artist"))
            composer_source = "EMBED_ARTIST_FALLBACK"
        
        if not res_composer:
            res_composer = steam_meta.developer or "Unknown"
            composer_source = "STEAM_DEVELOPER" if steam_meta.developer else "UNKNOWN_PLACEHOLDER"

        # --- 3. Genre Logic ---
        all_genres = steam_meta.genres if steam_meta.genres else []
        if not all_genres and steam_meta.parent_genres:
            all_genres = steam_meta.parent_genres
        
        if all_genres:
            joined_genres = ", ".join(all_genres)
            genre_source = "STEAM_GENRES" if steam_meta.genres else "STEAM_PARENT_GENRES"
        else:
            joined_genres = steam_meta.genre or steam_meta.parent_genre or 'Soundtrack'
            genre_source = "STEAM_GENRE_FALLBACK" if steam_meta.genre or steam_meta.parent_genre else "DEFAULT_PLACEHOLDER"
            
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

        if verified_mbz_authority and mbz_album and mbz_album.get("artist"):
            album_artist = _u(mbz_album["artist"]).strip()
            album_artist_source = "MBZ_STEAM_VERIFIED"
        else:
            album_artist_parts = [_u(part).strip() for part in [steam_meta.developer, steam_meta.publisher] if part]
            album_artist = ", ".join(album_artist_parts)
            album_artist_source = "STEAM_DEVELOPER_PUBLISHER"
        clean_fallback_title = clean_title.split("::")[0] if "::" in clean_title else clean_title
        album_source = "MBZ_STEAM_VERIFIED" if verified_mbz_authority and mbz_album else "STEAM"
        field_provenance = {
            "title": chosen_src,
            "artist": artist_source,
            "album": album_source,
            "album_artist": album_artist_source,
            "year": year_source,
            "track_number": track_number_source,
            "disc_number": disc_number_source,
            "genre": genre_source,
            "grouping": "STEAM",
            "comment": ["EMBED", "STEAM"] if existing_comment else ["STEAM"],
            "composer": composer_source,
            "language": "CONFIG_USER_LANGUAGE",
            "steam_appid": "STEAM_APP_IDENTITY",
            "mbid": "MUSICBRAINZ_RELEASE" if mbz_candidates else "UNKNOWN",
        }

        return {
            "title": _u(res_title or clean_fallback_title).strip(),
            "artist": _u(res_artist).strip(),
            "album": _u(
                mbz_album.get("album") if verified_mbz_authority and mbz_album else steam_meta.name
            ).strip(),
            "album_artist": album_artist,
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
            "title_source": chosen_src,
            "_field_provenance": field_provenance,
        }

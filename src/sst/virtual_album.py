import logging
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter

from .ident.acoustid import AcoustIDIdentifier
from .ident.mbz import MusicBrainzIdentifier
from .models import SteamMetadata

logger = logging.getLogger("sst.virtual_album")

class VirtualAlbumBuilder:
    def __init__(self, acoustid_client: AcoustIDIdentifier, mbz_client: MusicBrainzIdentifier, fingerprint_all: bool = False):
        self.acoustid = acoustid_client
        self.mbz = mbz_client
        self.fingerprint_all = fingerprint_all

    def build_fingerprint_album(self, track_groups: Dict[Tuple[int, str], List[Dict[str, Any]]], on_track_complete: Optional[callable] = None) -> Optional[Dict[str, Any]]:
        """
        Builds a virtual album using AcoustID cross-validation (majority vote) with advanced tie-break.
        """
        logger.info("Building FINGERPRINT virtual album using advanced cross-validation...")
        
        all_release_ids = []
        track_results = {}
        
        # Step 1: Scan tracks (Full or Sampled)
        target_keys = list(track_groups.keys())
        sampled_keys = target_keys
        
        # Apply sampling if not fingerprint_all and album is large
        if not self.fingerprint_all and len(target_keys) > 3:
            mid = len(target_keys) // 2
            sampled_keys = [target_keys[0], target_keys[mid], target_keys[-1]]
            logger.info(f"Sampling mode: Scanning {len(sampled_keys)}/{len(target_keys)} tracks.")
        else:
            logger.info(f"Full scan mode: Scanning all {len(target_keys)} tracks.")

        for i, key in enumerate(target_keys):
            if key not in sampled_keys:
                if on_track_complete:
                    on_track_complete()
                continue

            variants = track_groups[key]
            if not variants:
                if on_track_complete:
                    on_track_complete()
                continue
            
            # Use the best quality file for fingerprinting
            best_file = variants[0]["path"]
            candidates = self.acoustid.identify_track(best_file)
            
            track_results[key] = candidates
            for cand in candidates:
                if cand.get("release_ids"):
                    all_release_ids.extend(cand["release_ids"])
            
            if on_track_complete:
                on_track_complete()
        
        if not all_release_ids:
            logger.warning("No Release IDs found via AcoustID.")
            return None

        # Step 2: Advanced Scoring (Tie-break)
        # Instead of just counting, we calculate a score for each unique Release ID
        unique_rids = set(all_release_ids)
        rid_scores = {}
        
        counts = Counter(all_release_ids)
        local_track_count = len(track_groups)
        local_names_flat = " ".join([k[1].lower() for k in track_groups.keys()])
        
        for rid in unique_rids:
            # Base score: votes from tracks
            score = counts[rid] * 10
            
            # Fetch summary info for tie-break (fast fetch)
            details = self.mbz.get_release_details(rid)
            if not details: continue
            
            # 1. Structural Match (+50pt)
            mb_track_count = 0
            for medium in details.get("medium-list", []):
                mb_track_count += len(medium.get("track-list", []))
            
            if mb_track_count == local_track_count:
                score += 50
                logger.debug(f"RID {rid}: Track count match (+50)")
            
            # 2. Keyword Alignment (+30pt)
            keywords = ["instrumental", "off vocal", "karaoke", "remix", "arrange"]
            for kw in keywords:
                if kw in local_names_flat and kw in (details.get("title") or "").lower():
                    score += 30
                    logger.debug(f"RID {rid}: Keyword match '{kw}' (+30)")
            
            rid_scores[rid] = (score, details)

        # Pick the winner
        if not rid_scores:
            logger.warning("No Release ID scores could be calculated.")
            return None

        sorted_rids = sorted(rid_scores.items(), key=lambda x: x[1][0], reverse=True)
        chosen_rid, (best_score, release_details) = sorted_rids[0]
        logger.info(f"Advanced winner: {chosen_rid} (Score: {best_score})")

        # Step 3: Construct Virtual Album with Detailed Credits
        virtual_album = {
            "source": "FINGERPRINT",
            "mbid": chosen_rid,
            "album_name": release_details.get("title"),
            "artist": release_details.get("artist-credit-phrase"),
            "year": release_details.get("date", "")[:4] if release_details.get("date") else None,
            "label": release_details.get("label-info-list", [{}])[0].get("label", {}).get("name") if release_details.get("label-info-list") else None,
            "tracks": []
        }

        # Step 4: Parse Detailed Credits (Relationships)
        mb_mediums = release_details.get("medium-list", [])
        mb_all_tracks = []
        for medium in mb_mediums:
            m_pos = int(medium.get("position", 1))
            for track in medium.get("track-list", []):
                recording = track.get("recording", {})
                
                # Parse relationships (Composer, Lyricist, etc.)
                credits = {"composer": [], "lyricist": [], "arranger": [], "remixer": []}
                rels = recording.get("recording-relation-list", []) + recording.get("work-relation-list", [])
                for rel in rels:
                    rtype = rel.get("type")
                    target = rel.get("artist", {}).get("name")
                    if rtype == "composer": credits["composer"].append(target)
                    elif rtype == "lyricist": credits["lyricist"].append(target)
                    elif rtype == "arranger": credits["arranger"].append(target)
                    elif rtype == "remixer": credits["remixer"].append(target)

                mb_all_tracks.append({
                    "disc": m_pos,
                    "position": int(track.get("position", 0)),
                    "title": recording.get("title") or track.get("title"),
                    "duration_ms": int(track.get("length") or recording.get("length") or 0),
                    "mbid": recording.get("id"),
                    "credits": {k: ", ".join(v) if v else None for k, v in credits.items()}
                })

        # Step 5: Duration-based Track Binding
        matched_count = 0
        for key, variants in track_groups.items():
            local_dur = variants[0]["duration"] * 1000 # ms
            
            best_match = None
            min_diff = 3000 # 3 seconds threshold
            
            for mb_t in mb_all_tracks:
                diff = abs(mb_t["duration_ms"] - local_dur)
                if diff < min_diff:
                    min_diff = diff
                    best_match = mb_t
            
            if best_match:
                matched_count += 1
                virtual_album["tracks"].append({
                    "local_key": key,
                    "disc": best_match["disc"],
                    "track_num": best_match["position"],
                    "title": best_match["title"],
                    "duration_ms": best_match["duration_ms"],
                    "mbid": best_match["mbid"],
                    "credits": best_match["credits"],
                    "mbz_track_index": mb_all_tracks.index(best_match)
                })
            else:
                virtual_album["tracks"].append({
                    "local_key": key,
                    "disc": None,
                    "track_num": None,
                    "title": None,
                    "duration_ms": None,
                    "mbid": None,
                    "credits": None,
                    "mbz_track_index": None
                })
        
        # Physical confidence hint
        match_ratio = (matched_count / local_track_count * 100) if local_track_count > 0 else 0
        virtual_album["physical_match_ratio"] = round(match_ratio, 1)
        virtual_album["match_hint"] = f"HIGH ({matched_count}/{local_track_count} tracks matched by duration)" if match_ratio > 80 else "LOW"

        return virtual_album

    def build_steam_album(self, steam_meta: SteamMetadata) -> Dict[str, Any]:
        """
        Builds a virtual album using Steam Store info.
        """
        virtual_album = {
            "source": "STEAM",
            "album_name": steam_meta.name,
            "artist": steam_meta.developer,
            "year": steam_meta.release_date[:4] if steam_meta.release_date else None,
            "label": steam_meta.publisher,
            "tracks": []
        }
        
        for track in steam_meta.store_tracklist:
            virtual_album["tracks"].append({
                "disc": int(track.get("disc", 1)),
                "track_num": int(track.get("number") or track.get("track_number") or 0),
                "title": track.get("title") or track.get("name"),
                "duration_ms": (int(track.get("duration_s", 0)) * 1000) if track.get("duration_s") else None
            })
            
        return virtual_album

    def build_local_album(self, track_groups: Dict[Tuple[int, str], List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Builds a virtual album using Local file tags.
        """
        virtual_album = {
            "source": "LOCAL",
            "album_name": None,
            "artist": None,
            "year": None,
            "label": None,
            "tracks": []
        }
        
        for key, variants in track_groups.items():
            best = variants[0]
            virtual_album["tracks"].append({
                "local_key": key,
                "disc": key[0],
                "track_num": None, 
                "title": key[1],
                "duration_ms": int(best["duration"] * 1000)
            })
            
        return virtual_album

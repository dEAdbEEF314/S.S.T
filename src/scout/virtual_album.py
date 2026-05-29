import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from collections import Counter
import re

from .ident.acoustid import AcoustIDIdentifier
from .ident.mbz import MusicBrainzIdentifier
from .models import SteamMetadata

logger = logging.getLogger("scout.virtual_album")

class VirtualAlbumBuilder:
    def __init__(self, acoustid_client: AcoustIDIdentifier, mbz_client: MusicBrainzIdentifier):
        self.acoustid = acoustid_client
        self.mbz = mbz_client

    def build_fingerprint_album(self, track_groups: Dict[Tuple[int, str], List[Dict[str, Any]]], on_track_complete: Optional[callable] = None) -> Optional[Dict[str, Any]]:
        """
        Builds a virtual album using AcoustID cross-validation (majority vote).
        """
        logger.info("Building FINGERPRINT virtual album using cross-validation...")
        
        all_release_ids = []
        track_results = {}
        
        # Step 1: Scan all tracks
        target_keys = list(track_groups.keys())
        for i, key in enumerate(target_keys):
            variants = track_groups[key]
            if not variants:
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
            
            # API Rate Limit mitigation for large albums
            if i < len(target_keys) - 1:
                import time
                import random
                time.sleep(1.0 + random.uniform(0, 0.5))
        
        if not all_release_ids:
            logger.warning("No Release IDs found via AcoustID.")
            return None

        # Step 2: Majority Vote
        counts = Counter(all_release_ids)
        most_common = counts.most_common()
        
        # Tie-break logic (simplified for now: pick the one with most tracks in MBZ matching local count)
        chosen_rid = most_common[0][0]
        logger.info(f"Majority vote winner: {chosen_rid} ({counts[chosen_rid]} votes)")

        # Step 3: Fetch full details for the winner
        release_details = self.mbz.get_release_details(chosen_rid)
        if not release_details:
            return None

        # Step 4: Construct Virtual Album
        virtual_album = {
            "source": "FINGERPRINT",
            "mbid": chosen_rid,
            "album_name": release_details.get("title"),
            "artist": release_details.get("artist-credit-phrase"),
            "year": release_details.get("date", "")[:4] if release_details.get("date") else None,
            "label": release_details.get("label-info-list", [{}])[0].get("label", {}).get("name") if release_details.get("label-info-list") else None,
            "tracks": []
        }

        # Step 5: Duration-based Track Binding
        mb_mediums = release_details.get("medium-list", [])
        mb_all_tracks = []
        for medium in mb_mediums:
            m_pos = int(medium.get("position", 1))
            for track in medium.get("track-list", []):
                mb_all_tracks.append({
                    "disc": m_pos,
                    "position": int(track.get("position", 0)),
                    "title": track.get("recording", {}).get("title") or track.get("title"),
                    "duration_ms": int(track.get("length") or track.get("recording", {}).get("length") or 0),
                    "mbid": track.get("recording", {}).get("id")
                })

        matched_count = 0
        total_local_tracks = len(track_groups)
        for key, variants in track_groups.items():
            local_dur = variants[0]["duration"] * 1000 # ms
            
            # Find best duration match in the chosen MBZ release
            best_match = None
            min_diff = 2000 # 2 seconds threshold
            
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
                    "mbid": best_match["mbid"]
                })
            else:
                virtual_album["tracks"].append({
                    "local_key": key,
                    "disc": None,
                    "track_num": None,
                    "title": None,
                    "duration_ms": None,
                    "mbid": None
                })
        
        # Physical confidence hint
        match_ratio = (matched_count / total_local_tracks * 100) if total_local_tracks > 0 else 0
        virtual_album["physical_match_ratio"] = round(match_ratio, 1)
        virtual_album["match_hint"] = f"HIGH ({matched_count}/{total_local_tracks} tracks matched by duration)" if match_ratio > 80 else "LOW"

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
                "track_num": int(track.get("track_number", 0)),
                "title": track.get("name"),
                "duration_ms": None # Steam doesn't usually provide duration via Web API easily
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
                "track_num": None, # Usually parsed from filename or existing tag
                "title": key[1],
                "duration_ms": int(best["duration"] * 1000)
            })
            
        return virtual_album

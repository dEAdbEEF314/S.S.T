import musicbrainzngs
import logging
import re
import time
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

class MusicBrainzIdentifier:
    def __init__(self, app_name: str, version: str, contact: str):
        musicbrainzngs.set_useragent(app_name, version, contact)

    def search_release(
        self, 
        album_name: str, 
        expected_track_count: int, 
        app_id: Optional[int] = None, 
        parent_app_id: Optional[int] = None,
        year: Optional[str] = None,
        local_baseline: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Searches MusicBrainz and returns ranked candidates using the NWO Hybrid Scoring System.
        """
        log_data = {
            "query": {"album_name": album_name, "app_id": app_id, "expected_track_count": expected_track_count},
            "timestamp": datetime.utcnow().isoformat(),
            "attempts": []
        }
        
        # 1. Broad Search by Title
        # We don't filter by Artist anymore to avoid missing high-quality entries
        try:
            time.sleep(1.1) # Rate limit
            # Use 'release' instead of Lucene for broadness, then refine in Python
            result = musicbrainzngs.search_releases(release=album_name, limit=20)
            all_raw_releases = result.get('release-list', [])
            log_data["attempts"].append({"query": album_name, "count": len(all_raw_releases)})
        except Exception as e:
            logger.error(f"MBZ search error: {e}")
            return [], log_data

        if not all_raw_releases:
            return [], log_data

        # 2. Detailed Scoring (The Python Sieve)
        scored_candidates = []
        
        for r in all_raw_releases:
            mbid = r['id']
            # Fetch full details including URL relations and recordings for fingerprinting
            try:
                time.sleep(1.1)
                full_r = musicbrainzngs.get_release_by_id(mbid, includes=["url-rels", "recordings", "artist-credits"])
                release_data = full_r.get('release', {})
            except Exception as e:
                logger.warning(f"Failed to fetch details for {mbid}: {e}")
                continue

            score = 0
            evidence_notes = []

            # --- Tier 1: Deterministic Evidence ---
            relations = release_data.get('url-relation-list', [])
            for rel in relations:
                url = rel.get('target', '')
                # Steam AppID Check
                if app_id and f"store.steampowered.com/app/{app_id}" in url:
                    score += 500
                    evidence_notes.append("DIRECT_STEAM_LINK")
                elif parent_app_id and f"store.steampowered.com/app/{parent_app_id}" in url:
                    score += 300
                    evidence_notes.append("PARENT_STEAM_LINK")
                # Bandcamp Bonus
                if "bandcamp.com" in url:
                    score += 100
                    evidence_notes.append("BANDCAMP_LINK")

            # --- Tier 2: Strong Semantic & Structural ---
            # Title Similarity
            steam_sim = SequenceMatcher(None, album_name.lower(), release_data.get('title', '').lower()).ratio()
            local_sim = 0
            if local_baseline and local_baseline.get("album"):
                local_sim = SequenceMatcher(None, local_baseline["album"].lower(), release_data.get('title', '').lower()).ratio()
            
            title_score = int(max(steam_sim, local_sim) * 100)
            score += title_score
            evidence_notes.append(f"TITLE_SIM({title_score})")

            # Track Count
            try:
                mb_tracks = sum(int(m.get('track-count', 0)) for m in release_data.get('medium-list', []))
            except: mb_tracks = 0
            
            if mb_tracks == expected_track_count:
                score += 50
                evidence_notes.append("TRACK_COUNT_MATCH")
            else:
                diff = abs(mb_tracks - expected_track_count)
                penalty = min(50, diff * 10)
                score -= penalty
                evidence_notes.append(f"TRACK_COUNT_DIFF(-{penalty})")

            # --- Tier 3: Corroborative ---
            # Format
            is_digital = any(m.get('format') == 'Digital Media' for m in release_data.get('medium-list', []))
            if is_digital:
                score += 30
                evidence_notes.append("DIGITAL_FORMAT")

            # Date
            mb_year = release_data.get('date', '')[:4]
            compare_year = year or (local_baseline.get("year") if local_baseline else None)
            if compare_year and mb_year:
                if mb_year == compare_year:
                    score += 20
                    evidence_notes.append("DATE_MATCH")
                else:
                    date_diff = abs(int(mb_year) - int(compare_year))
                    score -= min(20, date_diff * 5)

            # --- NEW: Tracklist Fingerprint (+200 Bonus) ---
            if local_baseline and local_baseline.get("tracks"):
                local_track_names = [t.lower() for t in local_baseline["tracks"]]
                mb_track_names = []
                for m in release_data.get('medium-list', []):
                    for t in m.get('track-list', []):
                        if t.get('recording', {}).get('title'):
                            mb_track_names.append(t['recording']['title'].lower())
                
                if local_track_names and mb_track_names:
                    # Naive match: how many local tracks exist in MBZ list?
                    matches = 0
                    for lt in local_track_names:
                        if any(SequenceMatcher(None, lt, mt).ratio() > 0.85 for mt in mb_track_names):
                            matches += 1
                    
                    match_ratio = matches / len(local_track_names)
                    if match_ratio >= 0.8:
                        score += 200
                        evidence_notes.append(f"FINGERPRINT_MATCH({int(match_ratio*100)}%)")

            scored_candidates.append({
                "mbid": mbid,
                "score": score,
                "evidence": evidence_notes,
                "album": release_data.get('title'),
                "artist": release_data.get('artist-credit-phrase'),
                "year": mb_year,
                "track_count": mb_tracks,
                "is_digital": is_digital,
                "tracks": mb_track_names if 'mb_track_names' in locals() else []
            })

        # 3. Final Ranking
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        top_candidates = scored_candidates[:5]
        
        log_data["ranked_candidates"] = top_candidates
        return top_candidates, log_data

    def get_release_artwork_url(self, mbid: str) -> Optional[str]:
        try:
            images = musicbrainzngs.get_image_list(mbid)
            for img in images.get('images', []):
                if img.get('front') and img.get('image'): return img.get('image')
        except: pass
        return None

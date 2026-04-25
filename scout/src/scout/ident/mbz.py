import musicbrainzngs
import logging
import re
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class MusicBrainzIdentifier:
    def __init__(self, app_name: str, version: str, contact: str):
        musicbrainzngs.set_useragent(app_name, version, contact)

    def search_release(self, album_name: str, expected_track_count: int, app_id: Optional[int] = None, artists: List[str] = [], year: Optional[str] = None, parent_year: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Searches MusicBrainz and returns a list of ranked candidates based on scoring rules a-f.
        Returns (ranked_candidates, log_data).
        """
        log_data = {
            "query": {"album_name": album_name, "artists": artists, "year": year, "parent_year": parent_year, "expected_track_count": expected_track_count, "app_id": app_id},
            "attempts": [],
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        # 1. Multi-stage search
        clean_name = re.sub(r'\s+((original\s+)?soundtrack|ost)(\s+.*)?$', '', album_name, flags=re.IGNORECASE).strip()
        search_names = [album_name]
        if clean_name != album_name: search_names.append(clean_name)

        all_raw_releases = []
        import time
        for name in search_names:
            # Strict MBZ rate limiting (1req/s)
            time.sleep(1.1)
            query = f'release:"{name}"'
            if artists: query += f" AND (artist:\"{'\" OR artist:\"'.join(artists)}\")"
            years = [y for y in [year, parent_year] if y]
            if years: query += f" AND (date:{' OR date:'.join(years)})"
            query += ' AND format:"Digital Media"'
            
            try:
                result = musicbrainzngs.search_releases(query=query, limit=50)
                releases = result.get('release-list', [])
                if releases:
                    all_raw_releases.extend(releases)
                    log_data["attempts"].append({"query": query, "count": len(releases)})
            except Exception as e:
                logger.error(f"MBZ search error: {e}")

        # Fallback if no digital/year matches
        if not all_raw_releases:
            try:
                result = musicbrainzngs.search_releases(release=album_name, limit=20)
                all_raw_releases = result.get('release-list', [])
            except: pass

        # 2. Scoring (Rules a-f)
        scored_candidates = []
        seen_ids = set()
        
        for r in all_raw_releases:
            if r['id'] in seen_ids: continue
            seen_ids.add(r['id'])
            
            # Base engine score (0-100)
            score = int(r.get('ext:score', 0))
            
            # a. Album Title Match (+40)
            if r.get('title', '').lower() == album_name.lower():
                score += 40
            
            # b. Format = DigitalMedia (+50)
            if any(m.get('format') == 'Digital Media' for m in r.get('medium-list', [])):
                score += 50
                
            # c. No "Bandcamp" (+20)
            if "bandcamp" not in r.get('title', '').lower():
                score += 20
                
            # d. Track Count Match (+40 or +20)
            try:
                mb_tracks = int(r.get('medium-track-count', 0))
                if mb_tracks == 0:
                    mb_tracks = sum(int(m.get('track-count', 0)) for m in r.get('medium-list', []))
            except: mb_tracks = 0
            
            if mb_tracks == expected_track_count:
                score += 40
            elif abs(mb_tracks - expected_track_count) <= 2:
                score += 20
                
            # e. Soundtrack Release Date Match (+40 or +20)
            mb_year = r.get('date', '')[:4]
            if year and mb_year:
                if mb_year == year: score += 40
                elif abs(int(mb_year) - int(year)) <= 1: score += 20
            
            # f. Parent Game Release Date Match (+30 or +10)
            if parent_year and mb_year:
                if mb_year == parent_year: score += 30
                elif abs(int(mb_year) - int(parent_year)) <= 1: score += 10

            # Status Bonus
            if r.get('status', '').lower() == 'official': score += 20
            elif r.get('status', '').lower() == 'bootleg': score -= 100

            scored_candidates.append((score, r))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        
        # 3. Format Top Candidates for LLM
        ranked_results = []
        for score, r in scored_candidates[:5]: # Take top 5 for LLM to choose from
            ranked_results.append({
                "mbid": r['id'],
                "score": score,
                "status": r.get('status', 'Unknown'),
                "album": r.get('title'),
                "artist": r.get('artist-credit-phrase'),
                "year": r.get('date', '')[:4],
                "track_count": int(r.get('medium-track-count', 0)) or sum(int(m.get('track-count', 0)) for m in r.get('medium-list', [])),
                "is_digital": any(m.get('format') == 'Digital Media' for m in r.get('medium-list', []))
            })

        log_data["ranked_candidates"] = ranked_results
        return ranked_results, log_data

    def get_full_release_details(self, mbid: str) -> Optional[Dict[str, Any]]:
        """Fetches full tracklist and metadata for a chosen MBID."""
        try:
            return musicbrainzngs.get_release_by_id(mbid, includes=["recordings", "url-rels", "artist-credits"])
        except Exception as e:
            logger.error(f"Failed to fetch MBZ details for {mbid}: {e}")
            return None

    def get_release_artwork_url(self, mbid: str) -> Optional[str]:
        try:
            images = musicbrainzngs.get_image_list(mbid)
            for img in images.get('images', []):
                if img.get('front') and img.get('image'): return img.get('image')
        except: pass
        return None

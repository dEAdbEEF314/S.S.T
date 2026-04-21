import musicbrainzngs
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class MusicBrainzIdentifier:
    def __init__(self, app_name: str, version: str, contact: str):
        musicbrainzngs.set_useragent(app_name, version, contact)

    def search_release(self, album_name: str, expected_track_count: int, steam_release_date: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Searches MusicBrainz for a release and applies tie-breaking rules.
        Returns (formatted_result, log_data).
        """
        log_data = {
            "query": {"album_name": album_name, "expected_track_count": expected_track_count},
            "raw_response": None,
            "timestamp": datetime.utcnow().isoformat()
        }
        try:
            # Search for releases matching the album name
            result = musicbrainzngs.search_releases(release=album_name, limit=10)
            log_data["raw_response"] = result
            releases = result.get('release-list', [])
            
            if not releases:
                logger.info(f"No MusicBrainz results for: {album_name}")
                return None, log_data

            # Filter and sort by score (MB provides a score attribute)
            # We take all with the highest score first, then apply our rules
            max_score = int(releases[0].get('ext:score', 0))
            candidates = [r for r in releases if int(r.get('ext:score', 0)) == max_score]
            
            if len(candidates) > 1:
                logger.info(f"Multiple MB candidates with score {max_score}. Applying tie-breakers.")
                candidates = self._apply_tie_breakers(candidates, expected_track_count, steam_release_date)
            
            best_match = candidates[0]
            
            # Fetch full details for the best match (including track list and relationships)
            release_id = best_match['id']
            full_release = musicbrainzngs.get_release_by_id(release_id, includes=["recordings", "url-rels", "artist-credits"])
            log_data["full_release"] = full_release
            
            return self._format_result(full_release.get('release', {})), log_data

        except Exception as e:
            logger.error(f"MusicBrainz search error: {e}")
            log_data["error"] = str(e)
            return None, log_data

    def _apply_tie_breakers(self, candidates: List[dict], expected_track_count: int, steam_date: Optional[str]) -> List[dict]:
        """
        Applies rules from about_TAG.txt:
        a. Format = Digital Media
        b. No "Bandcamp"
        c. Track count closest
        d. Date closest
        """
        # 1. Format: Digital Media preferred
        digital = [c for c in candidates if any(m.get('format') == 'Digital Media' for m in c.get('medium-list', []))]
        if digital:
            candidates = digital

        # 2. Exclude "Bandcamp"
        no_bandcamp = [c for c in candidates if "bandcamp" not in c.get('title', '').lower()]
        if no_bandcamp and len(no_bandcamp) < len(candidates):
            candidates = no_bandcamp

        # 3. Track Count
        candidates.sort(key=lambda c: abs(int(c.get('medium-track-count', 0)) - expected_track_count))
        
        # 4. Release Date (Optional but good)
        if steam_date:
            try:
                s_date = datetime.strptime(steam_date[:4], "%Y")
                candidates.sort(key=lambda c: self._date_diff(c.get('date'), s_date))
            except:
                pass

        return candidates

    def _date_diff(self, mb_date: Optional[str], target_date: datetime) -> int:
        if not mb_date:
            return 9999
        try:
            m_date = datetime.strptime(mb_date[:4], "%Y")
            return abs((m_date - target_date).days)
        except:
            return 9999

    def _format_result(self, release: dict) -> Dict[str, Any]:
        """Extracts and normalizes metadata from the MB release dict."""
        # Extract VGMdb URL from relationships
        vgmdb_url = None
        for rel in release.get('url-relation-list', []):
            if 'vgmdb.net/album/' in rel.get('target', ''):
                vgmdb_url = rel.get('target')
                break

        # Get tracks
        tracks = []
        for medium in release.get('medium-list', []):
            disc_num = int(medium.get('position', 1))
            for track in medium.get('track-list', []):
                tracks.append({
                    "title": track.get('recording', {}).get('title'),
                    "artist": track.get('artist-credit-phrase'),
                    "track_num": int(track.get('position', 1)),
                    "disc_num": disc_num
                })

        return {
            "mbid": release.get('id'),
            "album": release.get('title'),
            "artist": release.get('artist-credit-phrase'),
            "year": release.get('date', '')[:4] if release.get('date') else None,
            "vgmdb_url": vgmdb_url,
            "tracks": tracks
        }

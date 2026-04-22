import musicbrainzngs
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class MusicBrainzIdentifier:
    def __init__(self, app_name: str, version: str, contact: str):
        musicbrainzngs.set_useragent(app_name, version, contact)

    def search_release(self, album_name: str, expected_track_count: int, app_id: Optional[int] = None, steam_release_date: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        Searches MusicBrainz for a release and applies tie-breaking rules.
        Returns (formatted_result, log_data).
        """
        log_data = {
            "query": {"album_name": album_name, "expected_track_count": expected_track_count, "app_id": app_id},
            "raw_search_response": None, # Will store the initial search results
            "raw_full_release": None,    # Will store the detailed release data
            "timestamp": datetime.utcnow().isoformat(),
            "confidence": "none"
        }
        try:
            # Search for releases matching the album name
            result = musicbrainzngs.search_releases(release=album_name, limit=10)
            log_data["raw_search_response"] = result
            releases = result.get('release-list', [])
            
            if not releases:
                logger.info(f"No MusicBrainz results for: {album_name}")
                return None, log_data

            # Filter and sort by score
            max_score = int(releases[0].get('ext:score', 0))
            candidates = [r for r in releases if int(r.get('ext:score', 0)) == max_score]
            
            is_confirmed = False
            is_ultra = False

            if len(candidates) > 1:
                logger.info(f"Multiple MB candidates with score {max_score}. Applying tie-breakers.")
                candidates, is_confirmed = self._apply_tie_breakers(candidates, expected_track_count, steam_release_date)
            else:
                candidates, is_confirmed = self._apply_tie_breakers(candidates, expected_track_count, steam_release_date)
            
            best_match = candidates[0]
            
            # Fetch full details for the best match
            release_id = best_match['id']
            full_release = musicbrainzngs.get_release_by_id(release_id, includes=["recordings", "url-rels", "artist-credits"])
            log_data["raw_full_release"] = full_release
            
            # Direct AppID Matching (Ultra Confirmation)
            if app_id:
                steam_url_pattern = f"store.steampowered.com/app/{app_id}"
                for rel in full_release.get('release', {}).get('url-relation-list', []):
                    if steam_url_pattern in rel.get('target', ''):
                        logger.info(f"Ultra Confirmation: Direct Steam AppID match found for {app_id}!")
                        is_ultra = True
                        break

            log_data["confidence"] = "ultra_confirmed" if is_ultra else ("confirmed" if is_confirmed else "weak")
            
            formatted = self._format_result(full_release.get('release', {}))
            formatted["confidence"] = log_data["confidence"]
            return formatted, log_data

        except Exception as e:
            logger.error(f"MusicBrainz search error: {e}")
            log_data["error"] = str(e)
            return None, log_data

    def _apply_tie_breakers(self, candidates: List[dict], expected_track_count: int, steam_date: Optional[str]) -> Tuple[List[dict], bool]:
        """
        Applies rules in order:
        0. disambiguation == "Steam" (Highest Priority)
        a. Format == Digital Media
        b. No "Bandcamp"
        c. Track count proximity
        d. Date proximity
        """
        is_steam_discriminated = False
        is_digital = False
        is_not_bandcamp = False

        # 0. Disambiguation: Steam
        steam_releases = [c for c in candidates if c.get('disambiguation', '').lower() == 'steam']
        if steam_releases:
            candidates = steam_releases
            is_steam_discriminated = True

        # a. Format: Digital Media preferred
        digital = [c for c in candidates if any(m.get('format') == 'Digital Media' for m in c.get('medium-list', []))]
        if digital:
            candidates = digital
            is_digital = True

        # b. Exclude "Bandcamp"
        no_bandcamp = [c for c in candidates if "bandcamp" not in c.get('title', '').lower()]
        if no_bandcamp:
            candidates = no_bandcamp
            is_not_bandcamp = True

        # c. Track Count Proximity
        candidates.sort(key=lambda c: abs(int(c.get('medium-track-count', 0)) - expected_track_count))
        
        # d. Date Proximity
        if steam_date:
            try:
                s_date = datetime.strptime(steam_date[:4], "%Y")
                candidates.sort(key=lambda c: self._date_diff(c.get('date'), s_date))
            except:
                pass

        # "Confirmed" if disambiguation is Steam OR (Digital Media AND No Bandcamp)
        confirmed = is_steam_discriminated or (is_digital and is_not_bandcamp)
        return candidates, confirmed

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

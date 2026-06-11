import acoustid
import logging
import os
import time
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger("sst.ident.acoustid")

class AcoustIDIdentifier:
    _api_lock = threading.Lock()
    _last_call_time = 0.0

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ACOUSTID_API_KEY")
        if not self.api_key:
            logger.warning("ACOUSTID_API_KEY not found. AcoustID matching will be disabled.")

    def _wait_for_rate_limit(self):
        """Ensures at least 1.0s between global API calls."""
        with self._api_lock:
            now = time.time()
            elapsed = now - AcoustIDIdentifier._last_call_time
            wait_time = 1.1 - elapsed # Use 1.1s for safety
            if wait_time > 0:
                time.sleep(wait_time)
            AcoustIDIdentifier._last_call_time = time.time()

    def identify_track(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Generates a fingerprint for the given file and looks it up on AcoustID.
        Returns a list of MusicBrainz Recording IDs and associated metadata.
        """
        if not self.api_key:
            return []

        try:
            logger.debug(f"Generating fingerprint for {file_path.name}...")
            # Generate fingerprint using fpcalc via the acoustid library
            duration, fingerprint = acoustid.fingerprint_file(str(file_path))
            
            # Global Rate Limit Enforcement
            self._wait_for_rate_limit()
            
            logger.debug(f"Fingerprint generated ({duration:.2f}s). Looking up AcoustID...")
            
            # Lookup AcoustID
            # meta="recordings releases" gives us MB Recording IDs and associated Release IDs
            results = acoustid.lookup(self.api_key, fingerprint, duration, meta="recordings releases", timeout=10.0)
            logger.debug(f"AcoustID lookup completed for {file_path.name}.")

            candidates = []
            if results.get("status") == "ok":
                for result in results.get("results", []):
                    score = result.get("score", 0.0)
                    for recording in result.get("recordings", []):
                        # Extract all associated Release IDs for this recording
                        release_ids = [rel.get("id") for rel in recording.get("releases", []) if rel.get("id")]
                        candidates.append({
                            "mbid": recording.get("id"),
                            "release_ids": release_ids,
                            "title": recording.get("title"),
                            "artist": recording.get("artists", [{}])[0].get("name") if recording.get("artists") else None,
                            "acoustid_score": score,
                            "source": "AcoustID"
                        })

            return candidates
        except acoustid.AcoustidError as e:
            logger.error(f"AcoustID API Error for {file_path.name}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error identifying {file_path.name} with AcoustID: {e}")
        
        return []

    def get_best_mbid(self, file_path: Path) -> Optional[str]:
        """Convenience method to get the single most likely MBID."""
        candidates = self.identify_track(file_path)
        if not candidates:
            return None
        # Sort by acoustid_score descending
        candidates.sort(key=lambda x: x.get("acoustid_score", 0), reverse=True)
        return candidates[0]["mbid"]

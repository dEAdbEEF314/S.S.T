import acoustid
import logging
import os
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger("scout.ident.acoustid")

class AcoustIDIdentifier:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ACOUSTID_API_KEY")
        if not self.api_key:
            logger.warning("ACOUSTID_API_KEY not found. AcoustID matching will be disabled.")

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
            logger.debug(f"Fingerprint generated ({duration:.2f}s). Looking up AcoustID...")
            
            # Lookup AcoustID
            # meta="recordings" gives us the MusicBrainz Recording IDs
            results = acoustid.lookup(self.api_key, fingerprint, duration, meta="recordings")
            logger.debug(f"AcoustID lookup completed for {file_path.name}.")

            candidates = []
            if results.get("status") == "ok":
                for result in results.get("results", []):
                    score = result.get("score", 0.0)
                    for recording in result.get("recordings", []):
                        candidates.append({
                            "mbid": recording.get("id"),
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

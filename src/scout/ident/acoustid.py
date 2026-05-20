import acoustid
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class AcoustIDIdentifier:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def identify(self, file_path: str) -> Optional[dict]:
        """
        Identifies a track using AcoustID fingerprinting.
        Returns the best match or None.
        """
        try:
            # results is a list of (score, recording_id, title, artist)
            results = acoustid.match(self.api_key, file_path, parse=True)
            
            # Find highest score
            best_match = None
            max_score = 0
            
            for score, recording_id, title, artist in results:
                if score > max_score:
                    max_score = score
                    best_match = {
                        "recording_id": recording_id,
                        "title": title,
                        "artist": artist,
                        "score": score
                    }
            
            if best_match:
                logger.info(f"AcoustID match: {best_match['title']} by {best_match['artist']} (Score: {max_score})")
            return best_match

        except acoustid.FingerprintError as e:
            logger.error(f"Fingerprint error: {e}")
        except acoustid.WebServiceError as e:
            logger.error(f"AcoustID Web Service error: {e}")
        except Exception as e:
            logger.error(f"AcoustID generic error: {e}")
            
        return None

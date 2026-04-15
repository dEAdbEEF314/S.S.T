import logging
from typing import List, Dict, Any
from collections import Counter

logger = logging.getLogger(__name__)

class CrossFormatValidator:
    """Validates metadata consistency across different audio formats."""

    @staticmethod
    def validate_album(format_metadata: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Compares metadata summaries across different formats (e.g., 'flac' vs 'mp3').
        :param format_metadata: Mapping of extension -> List of track metadata dicts
        :return: High-confidence metadata if consistent, else empty.
        """
        if len(format_metadata) < 2:
            logger.debug("Only one format available, skipping cross-validation.")
            return {}

        summaries = {}
        for ext, tracks in format_metadata.items():
            # Create an album-level summary for this format
            summaries[ext] = CrossFormatValidator._summarize(tracks)

        # Compare summaries
        formats = list(summaries.keys())
        base_format = formats[0]
        is_consistent = True
        
        for other_format in formats[1:]:
            if summaries[base_format] != summaries[other_format]:
                logger.info(f"Metadata mismatch between {base_format} and {other_format}")
                is_consistent = False
                break
        
        if is_consistent and summaries[base_format].get("album"):
            logger.info(f"Cross-format validation SUCCESS for album: {summaries[base_format]['album']}")
            return summaries[base_format]
        
        return {}

    @staticmethod
    def _summarize(tracks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Creates a summary of common album-level tags from a list of tracks."""
        if not tracks:
            return {}
            
        album_names = [t.get("album") for t in tracks if t.get("album")]
        artists = [t.get("artist") for t in tracks if t.get("artist")]
        years = [t.get("year") for t in tracks if t.get("year")]
        artwork_presence = [t.get("has_artwork", False) for t in tracks]

        # Use most common values (simple consensus)
        return {
            "album": Counter(album_names).most_common(1)[0][0] if album_names else None,
            "artist": Counter(artists).most_common(1)[0][0] if artists else None,
            "year": Counter(years).most_common(1)[0][0] if years else None,
            "track_count": len(tracks),
            "consistent_artwork": all(artwork_presence) if artwork_presence else False
        }

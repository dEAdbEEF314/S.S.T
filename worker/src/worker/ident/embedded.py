import logging
from pathlib import Path
from typing import Optional, Dict, Any
from mutagen import File
from mutagen.id3 import ID3, APIC

logger = logging.getLogger(__name__)

class EmbeddedMetadataExtractor:
    """Extracts existing metadata and artwork from audio files."""
    
    @staticmethod
    def extract(file_path: Path) -> Dict[str, Any]:
        """
        Extracts tags and cover art presence from a file.
        Returns a normalized dictionary of tags.
        """
        try:
            audio = File(file_path, easy=True)
            if audio is None:
                logger.warning(f"Could not parse metadata for: {file_path}")
                return {}

            # Basic tags
            metadata = {
                "title": audio.get("title", [None])[0],
                "artist": audio.get("artist", [None])[0],
                "album": audio.get("album", [None])[0],
                "track_number": audio.get("tracknumber", [None])[0],
                "year": audio.get("date", [None])[0],
                "has_artwork": False
            }

            # Check for artwork (APIC in ID3 or other formats)
            try:
                full_audio = File(file_path)
                if hasattr(full_audio, 'pictures') and full_audio.pictures:
                    metadata["has_artwork"] = True
                elif isinstance(full_audio, ID3):
                    if full_audio.getall("APIC"):
                        metadata["has_artwork"] = True
                elif hasattr(full_audio, 'tags'):
                    # Check for common artwork tags in different formats
                    for key in full_audio.tags.keys():
                        if "covr" in key or "METADATA_BLOCK_PICTURE" in key:
                            metadata["has_artwork"] = True
                            break
            except Exception as e:
                logger.debug(f"Artwork check failed for {file_path}: {e}")

            return {k: v for k, v in metadata.items() if v is not None}

        except Exception as e:
            logger.error(f"Error extracting metadata from {file_path}: {e}")
            return {}

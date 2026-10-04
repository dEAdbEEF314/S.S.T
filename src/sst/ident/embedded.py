import logging
from pathlib import Path
from typing import Dict, Any
from mutagen import File
from mutagen.id3 import ID3

logger = logging.getLogger(__name__)

class EmbeddedMetadataExtractor:
    """Extracts existing metadata and artwork from audio files."""
    
    @staticmethod
    def extract(file_path: Path) -> Dict[str, Any]:
        """
        Extracts tags, duration, and cover art presence from a file.
        Returns a normalized dictionary of tags.
        """
        try:
            audio = File(file_path, easy=True)
            if audio is None:
                logger.warning(f"Could not parse metadata for: {file_path}")
                return {}

            duration = 0.0
            if getattr(audio, "info", None) is not None:
                length = getattr(audio.info, "length", None)
                if length is not None and isinstance(length, (int, float)) and length > 0:
                    duration = float(length)

            # Basic tags
            metadata = {
                "title": audio.get("title", [None])[0],
                "artist": audio.get("artist", [None])[0],
                "album": audio.get("album", [None])[0],
                "composer": audio.get("composer", [None])[0],
                "track_number": audio.get("tracknumber", [None])[0],
                "disc_number": audio.get("discnumber", [None])[0],
                "year": audio.get("date", [None])[0],
                "comment": audio.get("comment", [None])[0],
                "has_artwork": False,
                "duration": duration,
            }

            # Check for artwork and additional tags (APIC/COMM in ID3 or other formats)
            try:
                # Single-pass: inspect underlying raw tags / picture blocks without re-opening file
                raw_tags = getattr(audio.tags, "_EasyID3__id3", audio.tags)
                if raw_tags is not None and hasattr(raw_tags, "keys"):
                    if not metadata.get("comment"):
                        # Search for COMM frames if easy mode missed it (common in ID3)
                        for key in raw_tags.keys():
                            if key.startswith("COMM"):
                                comm_frame = raw_tags[key]
                                if hasattr(comm_frame, "text") and comm_frame.text:
                                    metadata["comment"] = str(comm_frame.text[0])
                                    break

                    if not metadata.get("composer"):
                        for key in raw_tags.keys():
                            if key.startswith("TCOM"):
                                composer_frame = raw_tags[key]
                                if hasattr(composer_frame, "text") and composer_frame.text:
                                    metadata["composer"] = str(composer_frame.text[0])
                                    break

                if hasattr(audio, 'pictures') and audio.pictures:
                    metadata["has_artwork"] = True
                elif isinstance(raw_tags, ID3) or hasattr(raw_tags, "getall"):
                    if hasattr(raw_tags, "getall") and raw_tags.getall("APIC"):
                        metadata["has_artwork"] = True
                elif raw_tags is not None and hasattr(raw_tags, "keys"):
                    # Check for common artwork tags in different formats
                    for key in raw_tags.keys():
                        if "covr" in key or "METADATA_BLOCK_PICTURE" in key:
                            metadata["has_artwork"] = True
                            break
            except Exception as e:
                logger.debug(f"Artwork check failed for {file_path}: {e}")

            return {k: v for k, v in metadata.items() if v is not None}
        except Exception as e:
            logger.error(f"Error extracting metadata from {file_path}: {e}")
            return {}

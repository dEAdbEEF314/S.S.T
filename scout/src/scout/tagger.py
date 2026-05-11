import os
import subprocess
import logging
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("scout.tagger")

class AudioTagger:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def process_artwork(self, raw_data: bytes) -> Optional[Path]:
        if not raw_data: return None
        try:
            art_path = self.output_dir / "cover_temp.jpg"
            with open(art_path, "wb") as f:
                f.write(raw_data)
            return art_path
        except: return None

    def convert_and_limit(self, source_path: Path, tier: str, subdir: str = "") -> Tuple[Path, bool]:
        """
        Converts to AIFF (lossless) or MP3 (lossy) using FFmpeg.
        Returns (output_path, has_warnings).
        """
        target_ext = ".aif" if tier == "lossless" else ".mp3"
        out_rel_dir = self.output_dir / subdir
        out_rel_dir.mkdir(parents=True, exist_ok=True)
        target_path = out_rel_dir / (source_path.stem + target_ext)

        # Basic command
        cmd = ["ffmpeg", "-y", "-i", str(source_path)]
        
        # Enforce ID3v2.3 for both AIFF and MP3
        if tier == "lossless":
            cmd += ["-write_id3v2", "1", "-id3v2_version", "3"]
        else:
            cmd += ["-codec:a", "libmp3lame", "-qscale:a", "2", "-id3v2_version", "3"]

        cmd.append(str(target_path))
        
        process = subprocess.run(cmd, capture_output=True, text=True)
        has_warnings = False
        if process.stderr:
            # Check for critical decoding errors
            if "Decoding error" in process.stderr or "invalid rice order" in process.stderr:
                logger.warning(f"FFmpeg warnings for {source_path.name}: {process.stderr}")
                has_warnings = True
        
        return target_path, has_warnings

    def write_tags(self, file_path: Path, tag_map: Dict[str, Any], artwork_path: Optional[Path] = None):
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, TCON, TDRC, TRCK, TPOS, COMM, TPE2, TCOM, APIC, TIT1, TYER, TPUB
        from mutagen.aiff import AIFF
        from mutagen.mp3 import MP3

        try:
            audio = AIFF(file_path) if file_path.suffix == ".aif" else MP3(file_path)
            if audio.tags is None: audio.add_tags()
            tags = audio.tags

            # Standard Tags
            tags.add(TIT2(encoding=3, text=tag_map["title"]))
            tags.add(TPE1(encoding=3, text=tag_map["artist"]))
            tags.add(TALB(encoding=3, text=tag_map["album"]))
            tags.add(TPE2(encoding=3, text=tag_map["album_artist"]))
            tags.add(TCON(encoding=3, text=tag_map["genre"]))

            # Label/Publisher (TPUB)
            if tag_map.get("label"):
                tags.add(TPUB(encoding=3, text=tag_map["label"]))

            # Handle Year (Strictly TYER for ID3v2.3)
            # We delete TDRC first to prevent mutagen from auto-syncing/modernizing it.
            tags.delall("TDRC")
            year_val = tag_map["year"][:4] if tag_map.get("year") else "0000"
            tags.add(TYER(encoding=3, text=year_val))

            tags.add(TRCK(encoding=3, text=tag_map["track_number"]))
            tags.add(TPOS(encoding=3, text=tag_map["disc_number"]))
            tags.add(TCOM(encoding=3, text=tag_map["composer"]))
            tags.add(TIT1(encoding=3, text=tag_map["grouping"]))

            # Comment length adjustment (Prune tags unit by unit if too long)
            comment_text = tag_map["comment"]
            if len(comment_text.encode('utf-16')) > 2000:
                parts = comment_text.split(" | ")
                if len(parts) >= 4:
                    name, tags_str, app_id, url = parts[0], parts[1], parts[2], parts[3]
                    tags_list = tags_str.split(", ")
                    while tags_list and len(f"{name} | {', '.join(tags_list)} | {app_id} | {url}".encode('utf-16')) > 2000:
                        tags_list.pop()
                    comment_text = f"{name} | {', '.join(tags_list)} | {app_id} | {url}"

            tags.add(COMM(encoding=3, lang=tag_map["language"], desc="", text=comment_text))

            # Artwork
            if artwork_path and artwork_path.exists():
                with open(artwork_path, "rb") as f:
                    tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Front Cover', data=f.read()))

            # Force save as ID3v2.3
            audio.save(v2_version=3)

        except Exception as e:
            logger.error(f"Failed to write tags to {file_path.name}: {e}")

        except Exception as e:
            logger.error(f"Failed to write tags to {file_path.name}: {e}")

    @staticmethod
    def read_tags(file_path: Path) -> Dict[str, Any]:
        """Reads tags from an audio file and returns a standard tag map."""
        from mutagen.id3 import ID3
        from mutagen.aiff import AIFF
        from mutagen.mp3 import MP3
        
        try:
            audio = AIFF(file_path) if file_path.suffix == ".aif" else MP3(file_path)
            tags = audio.tags
            if tags is None: return {}
            
            def get_text(frame_id):
                frame = tags.get(frame_id)
                return str(frame.text[0]) if frame and frame.text else None

            return {
                "title": get_text("TIT2"),
                "artist": get_text("TPE1"),
                "album": get_text("TALB"),
                "album_artist": get_text("TPE2"),
                "genre": get_text("TCON"),
                "year": get_text("TYER") or get_text("TDRC"),
                "track_number": get_text("TRCK"),
                "disc_number": get_text("TPOS"),
                "composer": get_text("TCOM"),
                "grouping": get_text("TIT1"),
                "comment": get_text("COMM::'Steam Metadata'") or get_text("COMM")
            }
        except Exception as e:
            logger.error(f"Failed to read tags from {file_path.name}: {e}")
            return {}

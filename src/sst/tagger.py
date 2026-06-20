import subprocess
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("sst.tagger")

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
        except Exception: return None

    def _get_audio_properties(self, path: Path) -> Tuple[int, int]:
        """
        Gets (sample_rate, bit_depth) using ffprobe.
        Returns (0, 0) on failure.
        """
        import json
        try:
            cmd = [
                "ffprobe", "-v", "error", 
                "-select_streams", "a:0", 
                "-show_entries", "stream=sample_rate,bits_per_sample,sample_fmt", 
                "-of", "json", 
                str(path)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            data = json.loads(res.stdout)
            streams = data.get("streams", [])
            if not streams:
                return 0, 0
            
            stream = streams[0]
            sample_rate = int(stream.get("sample_rate", 0))
            
            bit_depth = 0
            bits = stream.get("bits_per_sample")
            if bits:
                bit_depth = int(bits)
            else:
                fmt = stream.get("sample_fmt", "")
                if "16" in fmt:
                    bit_depth = 16
                elif "24" in fmt:
                    bit_depth = 24
                elif "32" in fmt or "flt" in fmt:
                    bit_depth = 32
                elif "dbl" in fmt or "64" in fmt:
                    bit_depth = 64
            
            return sample_rate, bit_depth
        except Exception:
            return 0, 0

    def convert_and_limit(self, source_path: Path, tier: str, subdir: str = "") -> Tuple[Path, bool]:
        """
        Converts to AIFF (lossless) or MP3 (lossy) using FFmpeg.
        Enforces 24-bit / 48 kHz maximum limits for lossless files.
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
            
            # Check source properties for conditional downsampling
            rate, depth = self._get_audio_properties(source_path)
            if rate > 0:
                # 1. Limit sampling rate to 48 kHz
                if rate > 48000:
                    cmd += ["-ar", "48000"]
                    logger.info(f"Downsampling {source_path.name} from {rate}Hz to 48000Hz.")
                
                # 2. Limit bit depth to 24-bit
                if depth > 24:
                    cmd += ["-acodec", "pcm_s24be"]
                    logger.info(f"Reducing bit depth of {source_path.name} from {depth}-bit to 24-bit.")
        else:
            cmd += ["-codec:a", "libmp3lame", "-b:a", "320k", "-id3v2_version", "3"]

        cmd.append(str(target_path))
        
        # Capture output as binary to avoid UnicodeDecodeError when paths contain non-UTF-8 characters
        process = subprocess.run(cmd, capture_output=True)
        has_warnings = False
        if process.stderr:
            # Decode safely by ignoring characters that cannot be decoded as UTF-8
            stderr_str = process.stderr.decode('utf-8', errors='ignore')
            # Check for critical decoding errors
            if "Decoding error" in stderr_str or "invalid rice order" in stderr_str:
                logger.warning(f"FFmpeg warnings for {source_path.name}: {stderr_str}")
                has_warnings = True

        return target_path, has_warnings

    def write_tags(self, file_path: Path, tag_map: Dict[str, Any], artwork_path: Optional[Path] = None):
        from mutagen.id3 import TIT2, TPE1, TALB, TCON, TRCK, TPOS, COMM, TPE2, TCOM, APIC, TIT1, TYER, TPUB
        from mutagen.aiff import AIFF
        from mutagen.mp3 import MP3

        try:
            audio = AIFF(file_path) if file_path.suffix == ".aif" else MP3(file_path)
            
            # Ensure we have an ID3 tag object to work with
            if audio.tags is None:
                audio.add_tags()
            else:
                # Clear all existing frames to ensure a clean slate
                audio.tags.clear()
            
            tags = audio.tags

            # Standard Tags (Encoding 1 = UTF-16 with BOM for ID3v2.3 compliance)
            tags.add(TIT2(encoding=1, text=tag_map["title"]))
            tags.add(TPE1(encoding=1, text=tag_map["artist"]))
            tags.add(TALB(encoding=1, text=tag_map["album"]))
            tags.add(TPE2(encoding=1, text=tag_map["album_artist"]))
            tags.add(TCON(encoding=1, text=tag_map["genre"]))

            # Label/Publisher (TPUB)
            if tag_map.get("label"):
                tags.add(TPUB(encoding=1, text=tag_map["label"]))

            # Handle Year (Strictly TYER for ID3v2.3)
            year_val = tag_map["year"][:4] if tag_map.get("year") else "0000"
            tags.add(TYER(encoding=1, text=year_val))

            tags.add(TRCK(encoding=1, text=tag_map["track_number"] or "0"))
            tags.add(TPOS(encoding=1, text=tag_map["disc_number"] or "1/1"))
            if tag_map.get("composer"):
                tags.add(TCOM(encoding=1, text=tag_map["composer"]))
            tags.add(TIT1(encoding=1, text=tag_map["grouping"] or ""))

            # Comment logic
            comment_text = tag_map["comment"]
            if len(comment_text.encode('utf-16')) > 2000:
                match = re.search(r', \[(.*)\], \d+, https', comment_text)
                if match:
                    prefix = comment_text[:match.start(1)]
                    tags_str = match.group(1)
                    suffix = comment_text[match.end(1):]
                    tags_list = tags_str.split("/ ")
                    while tags_list and len(f"{prefix}{'/ '.join(tags_list)}{suffix}".encode('utf-16')) > 2000:
                        tags_list.pop()
                    comment_text = f"{prefix}{'/ '.join(tags_list)}{suffix}"

            # Add the single consolidated comment in the specified user language (encoding=1 for UTF-16)
            tags.add(COMM(encoding=1, lang=tag_map["language"], desc="", text=comment_text))

            # Artwork (APIC frame uses encoding=1 for description if present, though Front Cover desc is standard ASCII)
            if artwork_path and artwork_path.exists():
                with open(artwork_path, "rb") as f:
                    tags.add(APIC(encoding=1, mime='image/jpeg', type=3, desc='Front Cover', data=f.read()))

            # Force save as ID3v2.3 for maximum compatibility (including Windows Explorer)
            audio.save(v2_version=3)

        except Exception as e:
            logger.error(f"Failed to write tags to {file_path.name}: {e}")

    @staticmethod
    def read_tags(file_path: Path) -> Dict[str, Any]:
        """Reads tags from an audio file and returns a standard tag map."""
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

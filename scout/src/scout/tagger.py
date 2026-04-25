import os
import subprocess
import logging
from pathlib import Path
from PIL import Image
from typing import Optional
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TCON, TIT1, COMM, TCOM, TDRC, TRCK, TPOS, TXXX, APIC

logger = logging.getLogger(__name__)

# Constants for quality limits
MAX_SAMPLE_RATE = "48000"
MP3_BITRATE = "320k"
TARGET_IMAGE_SIZE = (500, 500)

class AudioTagger:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def process_artwork(self, source_img_data: bytes) -> bytes:
        """Resizes to 500x500. If square, stretches to fill. If not, pads with black."""
        import io
        try:
            with Image.open(io.BytesIO(source_img_data)) as img:
                # Convert to RGB to ensure black background consistency
                img = img.convert("RGB")

                width, height = img.size
                aspect_ratio = width / height

                # If nearly square (within 1% tolerance), force resize to fill 500x500
                if 0.99 <= aspect_ratio <= 1.01:
                    img = img.resize(TARGET_IMAGE_SIZE, Image.Resampling.LANCZOS)
                    new_img = img
                else:
                    # Maintain aspect ratio, scaling longest side to 500
                    img.thumbnail(TARGET_IMAGE_SIZE, Image.Resampling.LANCZOS)
                    # Create black background
                    new_img = Image.new("RGB", TARGET_IMAGE_SIZE, (0, 0, 0))
                    # Center the image
                    x = (TARGET_IMAGE_SIZE[0] - img.width) // 2
                    y = (TARGET_IMAGE_SIZE[1] - img.height) // 2
                    new_img.paste(img, (x, y))

                output = io.BytesIO()
                new_img.save(output, format="PNG")
                return output.getvalue()
        except Exception as e:
            logger.error(f"Artwork processing failed: {e}")
            return source_img_data


    def convert_and_limit(self, source_path: Path, quality_tier: str, subdir: str = "") -> Path:
        """
        Converts audio based on quality tier and strict constraints.
        :param quality_tier: 'lossless' -> AIFF (24-bit/48kHz), 'lossy' -> 320k MP3
        :param subdir: Optional subdirectory (e.g. disc number)
        """
        target_ext = ".aiff" if quality_tier == "lossless" else ".mp3"
        
        dest_dir = self.output_dir / subdir if subdir else self.output_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        target_path = dest_dir / source_path.with_suffix(target_ext).name
        
        # Avoid upscanning/re-encoding if source is already MP3 and tier is lossy/mp3
        if source_path.suffix.lower() == ".mp3" and target_ext == ".mp3":
            import shutil
            try:
                shutil.copy2(source_path, target_path)
                return target_path
            except Exception as e:
                logger.error(f"Failed to copy MP3: {e}")
                # Fallback to ffmpeg if copy fails
        
        # FFmpeg command for strict limits
        cmd = ["ffmpeg", "-i", str(source_path), "-y", "-loglevel", "error"]

        if quality_tier == "lossless":
            # AIFF: 24-bit PCM Big Endian, 48kHz (Highest Compatibility)
            # Using 'soxr' resampler for professional-grade sample rate conversion
            cmd += [
                "-ar", "48000",
                "-resampler", "soxr",
                "-c:a", "pcm_s24be", 
                "-write_id3v2", "1",
                str(target_path)
            ]
        else:
            # MP3: Convert to 320kbps CBR, max 48kHz with high-quality resampling
            cmd += [
                "-ar", "48000",
                "-resampler", "soxr",
                "-codec:a", "libmp3lame", 
                "-b:a", "320k", 
                str(target_path)
            ]

        try:
            subprocess.run(cmd, check=True)
            return target_path
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed for {source_path}: {e}")
            raise

    def write_tags(self, file_path: Path, tags: dict, artwork_data: Optional[bytes] = None):
        """Writes ID3v2.3 tags with strict field mapping. Supports MP3 and AIFF."""
        from mutagen import File
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TCON, TIT1, COMM, TCOM, TDRC, TRCK, TPOS, TXXX, APIC

        try:
            # For AIFF, we need to ensure it's wrapped or handled by Mutagen correctly
            audio_file = File(file_path)
            if audio_file is None:
                logger.error(f"Mutagen could not open {file_path}")
                return

            if file_path.suffix.lower() == ".aiff":
                # AIFF might not have tags yet
                if not audio_file.tags:
                    audio_file.add_tags()
                audio = audio_file.tags
            else:
                # Standard ID3 for MP3
                try:
                    audio = ID3(file_path)
                except:
                    audio = ID3()
                    audio.save(file_path)
        except Exception as e:
            logger.error(f"Failed to initialize tags for {file_path}: {e}")
            return

        def _safe_text(val):
            return [str(val)] if val is not None and str(val).strip() != "" else []

        # Frame Mapping (ID3v2.3)
        # Using lists for 'text' to satisfy mutagen
        mapping = {
            "TIT2": (TIT2, tags.get("title")),
            "TPE1": (TPE1, tags.get("artist")),
            "TALB": (TALB, tags.get("album")),
            "TPE2": (TPE2, tags.get("album_artist")),
            "TCON": (TCON, tags.get("genre")),
            "TIT1": (TIT1, tags.get("grouping")),
            "TCOM": (TCOM, tags.get("composer")),
            "TDRC": (TDRC, tags.get("year")),
            "TRCK": (TRCK, tags.get("track_number")),
            "TPOS": (TPOS, tags.get("disc_number")),
        }

        for frame_class, value in mapping.values():
            text_list = _safe_text(value)
            if text_list:
                audio.add(frame_class(encoding=1, text=text_list))

        # Comment frame is special (needs lang and desc)
        comment_text = tags.get("comment")
        if comment_text:
            audio.add(COMM(encoding=1, lang="jpn", desc="", text=[str(comment_text)]))

        # Custom TXXX fields
        if tags.get("mbid"):
            audio.add(TXXX(encoding=1, desc="MusicBrainz Album Id", text=tags["mbid"]))
        if tags.get("steam_appid"):
            audio.add(TXXX(encoding=1, desc="Steam App Id", text=str(tags["steam_appid"])))
        if tags.get("vgmdb_url"):
            audio.add(TXXX(encoding=1, desc="VGMdb URL", text=tags["vgmdb_url"]))

        # Artwork
        if artwork_data:
            audio.add(APIC(
                encoding=1, mime="image/png", type=3, desc="Front Cover", data=artwork_data
            ))

        if file_path.suffix.lower() == ".aiff":
            audio_file.save()
        else:
            audio.save(file_path, v2_version=3)

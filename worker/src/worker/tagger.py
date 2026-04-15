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
        """Resizes and pads raw image data to 500x500 PNG with black bars."""
        import io
        try:
            with Image.open(io.BytesIO(source_img_data)) as img:
                img = img.convert("RGBA")
                img.thumbnail(TARGET_IMAGE_SIZE, Image.Resampling.LANCZOS)
                new_img = Image.new("RGBA", TARGET_IMAGE_SIZE, (0, 0, 0, 255))
                x = (TARGET_IMAGE_SIZE[0] - img.width) // 2
                y = (TARGET_IMAGE_SIZE[1] - img.height) // 2
                new_img.paste(img, (x, y))
                
                output = io.BytesIO()
                new_img.save(output, format="PNG")
                return output.getvalue()
        except Exception as e:
            logger.error(f"Artwork processing failed: {e}")
            return source_img_data

    def convert_and_limit(self, source_path: Path, quality_tier: str) -> Path:
        """
        Converts audio based on quality tier and strict constraints.
        :param quality_tier: 'lossless' -> AIFF, 'mp3' -> Pass, 'lossy' -> 320k MP3
        """
        target_ext = ".aiff" if quality_tier == "lossless" else ".mp3"
        target_path = self.output_dir / source_path.with_suffix(target_ext).name
        
        if quality_tier == "mp3" and source_path.suffix.lower() == ".mp3":
            logger.info(f"Passthrough MP3: {source_path.name}")
            import shutil
            shutil.copy2(source_path, target_path)
            return target_path

        # FFmpeg command for strict limits
        cmd = ["ffmpeg", "-i", str(source_path), "-y", "-loglevel", "error"]
        
        # Limit sample rate
        cmd += ["-ar", MAX_SAMPLE_RATE]

        if quality_tier == "lossless":
            # Convert to AIFF 24-bit
            cmd += ["-sample_fmt", "s32p", str(target_path)] 
        else:
            # Convert other lossy to 320kbps CBR MP3
            cmd += ["-codec:a", "libmp3lame", "-b:a", MP3_BITRATE, str(target_path)]

        try:
            subprocess.run(cmd, check=True)
            return target_path
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed for {source_path}: {e}")
            raise

    def write_tags(self, file_path: Path, tags: dict, artwork_data: Optional[bytes] = None):
        """Writes ID3v2.3 tags with strict field mapping."""
        try:
            audio = ID3(file_path)
        except:
            audio = ID3()

        # Frame Mapping (ID3v2.3)
        frames = {
            "TIT2": TIT2(encoding=3, text=tags.get("title")),
            "TPE1": TPE1(encoding=3, text=tags.get("artist")),
            "TALB": TALB(encoding=3, text=tags.get("album")),
            "TPE2": TPE2(encoding=3, text=tags.get("album_artist")),
            "TCON": TCON(encoding=3, text=tags.get("genre")),
            "TIT1": TIT1(encoding=3, text=tags.get("grouping")),
            "COMM": COMM(encoding=3, lang="eng", desc="", text=tags.get("comment")),
            "TCOM": TCOM(encoding=3, text=tags.get("composer")),
            "TDRC": TDRC(encoding=3, text=str(tags.get("year")) if tags.get("year") else ""),
            "TRCK": TRCK(encoding=3, text=tags.get("track_num")),
            "TPOS": TPOS(encoding=3, text=tags.get("disc_num")),
        }

        for frame in frames.values():
            if frame.text and frame.text[0]:
                audio.add(frame)

        # Custom TXXX fields
        if tags.get("mbid"):
            audio.add(TXXX(encoding=3, desc="MusicBrainz Album Id", text=tags["mbid"]))
        if tags.get("steam_appid"):
            audio.add(TXXX(encoding=3, desc="Steam App Id", text=str(tags["steam_appid"])))
        if tags.get("vgmdb_url"):
            audio.add(TXXX(encoding=3, desc="VGMdb URL", text=tags["vgmdb_url"]))

        # Artwork
        if artwork_data:
            audio.add(APIC(
                encoding=3, mime="image/png", type=3, desc="Front Cover", data=artwork_data
            ))

        audio.save(file_path, v2_version=3)

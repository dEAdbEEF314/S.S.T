import os
import shutil
import json
import logging
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional

from .utils import ensure_path, is_safe_subpath

logger = logging.getLogger("sst.packager")

# Extensions that are already heavily compressed and should NOT be re-compressed by default
# (saves significant CPU time and prevents archive generation bottlenecks)
MULTIMEDIA_EXTENSIONS = {
    ".flac", ".mp3", ".m4a", ".ogg", ".wav", ".aac", ".opus", ".wma",
    ".alac", ".aiff", ".aif",
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
}


def create_optimized_zip(
    source_dir: Path,
    zip_path: Path,
    strategy: str = "auto",
    deflate_level: int = 1,
) -> Path:
    """
    Creates a ZIP archive from source_dir using an optimized compression strategy.
    
    Strategies:
      - 'auto' (default): Multimedia files (FLAC, MP3, JPG, etc.) are stored uncompressed (ZIP_STORED)
                          since they are already compressed. Text, JSON, logs, cue sheets are
                          compressed with ZIP_DEFLATED.
      - 'stored': All files are stored without compression (ZIP_STORED, ultra-fast I/O speed).
      - 'deflate': All files are compressed using standard DEFLATE (legacy behavior).
    """
    source_dir = source_dir.resolve()
    temp_zip_file = zip_path.with_suffix(".tmp.zip")
    
    strategy = (strategy or "auto").strip().lower()
    if strategy not in {"auto", "stored", "deflate"}:
        strategy = "auto"

    compress_level = max(1, min(9, deflate_level))

    with zipfile.ZipFile(temp_zip_file, "w") as zf:
        for root, dirs, files in os.walk(source_dir):
            # Sort for deterministic archive order
            dirs.sort()
            files.sort()
            for file_name in files:
                full_path = Path(root) / file_name
                rel_path = full_path.relative_to(source_dir)
                ext = full_path.suffix.lower()

                if strategy == "stored":
                    compression_type = zipfile.ZIP_STORED
                    compress_kwargs = {}
                elif strategy == "deflate":
                    compression_type = zipfile.ZIP_DEFLATED
                    compress_kwargs = {"compresslevel": compress_level}
                else:  # auto
                    if ext in MULTIMEDIA_EXTENSIONS:
                        compression_type = zipfile.ZIP_STORED
                        compress_kwargs = {}
                    else:
                        compression_type = zipfile.ZIP_DEFLATED
                        compress_kwargs = {"compresslevel": compress_level}

                zf.write(full_path, arcname=str(rel_path), compress_type=compression_type, **compress_kwargs)

    # Atomically replace or move into destination
    temp_zip_file.replace(zip_path)
    return zip_path


class PackageManager:
    @staticmethod
    def save_local_package(
        app_id: int,
        status: str,
        album_name: str,
        source_dir: Path,
        logs: Dict[str, Any],
        output_root: str,
        compression_strategy: Optional[str] = None,
        deflate_level: Optional[int] = None,
    ) -> Optional[Path]:
        """
        Creates an optimized ZIP archive and preserves it under the configured output root.
        Guarantees path traversal prevention and high-speed compression.
        """
        try:
            # 1. Prepare and validate final destination
            final_output_root = ensure_path(output_root).resolve()
            
            # Sanitize status to prevent directory escape
            clean_status = "".join(c for c in str(status) if c.isalnum() or c in "_-").strip("._-")
            if not clean_status:
                clean_status = "review"

            output_base = (final_output_root / clean_status).resolve()
            if not is_safe_subpath(output_base, final_output_root):
                raise ValueError(f"Path traversal detected in status directory: {status}")
            output_base.mkdir(parents=True, exist_ok=True)

            # Sanitize filename for ZIP
            safe_name = "".join([c if c.isalnum() or c in ".-_" else "_" for c in album_name]).strip("._-")
            if not safe_name:
                safe_name = "album"
            zip_filename = f"{app_id}_{safe_name}.zip"
            final_zip_path = (output_base / zip_filename).resolve()

            if not is_safe_subpath(final_zip_path, final_output_root):
                raise ValueError(f"Path traversal detected in ZIP destination: {final_zip_path}")

            # 2. Write log files into the source directory safely (prevent path traversal)
            resolved_source = source_dir.resolve()
            for log_name, log_content in logs.items():
                if log_content:
                    clean_name = Path(log_name).name
                    if not clean_name:
                        continue
                    if clean_name.endswith(".json"):
                        json_dir = source_dir / "json"
                        json_dir.mkdir(exist_ok=True)
                        log_file = json_dir / clean_name
                        if is_safe_subpath(log_file, resolved_source):
                            with open(log_file, "w", encoding="utf-8") as f:
                                json.dump(log_content, f, indent=2, ensure_ascii=False)
                    else:
                        log_file = source_dir / clean_name
                        if is_safe_subpath(log_file, resolved_source):
                            log_file.write_text(str(log_content), encoding="utf-8")

            # 3. Read compression settings from environment if not explicitly provided
            strategy = compression_strategy or os.getenv("ZIP_COMPRESSION_STRATEGY", "auto")
            level = deflate_level if deflate_level is not None else int(os.getenv("ZIP_DEFLATE_LEVEL", "1"))

            # 4. Create optimized ZIP
            temp_zip_dest = source_dir.parent / f"bundle_{app_id}_{clean_status}.zip"
            create_optimized_zip(source_dir, temp_zip_dest, strategy=strategy, deflate_level=level)

            # 5. Move to final destination
            try:
                shutil.move(str(temp_zip_dest), str(final_zip_path))
            except OSError as move_err:
                logger.debug(f"shutil.move failed ({move_err}), falling back to copyfile+unlink")
                shutil.copyfile(str(temp_zip_dest), str(final_zip_path))
                if temp_zip_dest.exists():
                    temp_zip_dest.unlink()

            # 6. Success: Return the path to the preserved ZIP file
            logger.info(f"Package successfully created ({strategy}): {final_zip_path}")
            return final_zip_path

        except Exception as e:
            logger.error(f"Failed to save package for {app_id}: {e}")
            return None

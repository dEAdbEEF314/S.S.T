import shutil
import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("scout.packager")

class PackageManager:
    @staticmethod
    def save_local_package(app_id: int, status: str, album_name: str, source_dir: Path, logs: Dict[str, Any]):
        """
        Creates a ZIP archive in the native WSL2 temp directory and moves it to the final output.
        Atomic Move strategy to prevent corrupted files on Windows mounts.
        """
        try:
            # 1. Prepare final destination
            output_base = Path("output") / status
            output_base.mkdir(parents=True, exist_ok=True)
            
            # Sanitize filename
            safe_name = "".join([c if c.isalnum() or c in ".-_" else "_" for c in album_name])
            final_zip_path = output_base / f"{app_id}_{safe_name}.zip"

            # 2. Write log files into the source directory before zipping
            for log_name, log_content in logs.items():
                if log_content:
                    log_file = source_dir / log_name
                    if log_name.endswith(".json"):
                        with open(log_file, "w", encoding="utf-8") as f:
                            json.dump(log_content, f, indent=2, ensure_ascii=False)
                    else:
                        log_file.write_text(str(log_content), encoding="utf-8")

            # 3. Create ZIP in NATIVE temp directory first
            temp_zip_base = source_dir.parent / f"bundle_{app_id}"
            archive_result = shutil.make_archive(str(temp_zip_base), 'zip', source_dir)
            temp_zip_file = Path(archive_result)

            # 4. Atomic Move to final destination
            shutil.move(str(temp_zip_file), str(final_zip_path))
            
            logger.info(f"Local package saved: {final_zip_path}")
            return final_zip_path
            
        except Exception as e:
            logger.error(f"Failed to save local package for {app_id}: {e}")
            return None

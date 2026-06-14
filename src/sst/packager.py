import shutil
import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("sst.packager")

class PackageManager:
    @staticmethod
    def save_local_package(app_id: int, status: str, album_name: str, source_dir: Path, logs: Dict[str, Any], output_root: str):
        """
        Creates a ZIP archive, moves it to the target Windows output, and extracts it.
        """
        from .utils import ensure_wsl_path
        import subprocess
        
        try:
            # 1. Prepare final destination (Windows side)
            final_output_root = ensure_wsl_path(output_root)
            output_base = final_output_root / status
            output_base.mkdir(parents=True, exist_ok=True)
            
            # Sanitize filename for ZIP
            safe_name = "".join([c if c.isalnum() or c in ".-_" else "_" for c in album_name])
            zip_filename = f"{app_id}_{safe_name}.zip"
            final_zip_path = output_base / zip_filename
            extract_dir = output_base / f"{app_id}_{safe_name}"

            # 2. Write log files into the source directory
            for log_name, log_content in logs.items():
                if log_content:
                    if log_name.endswith(".json"):
                        json_dir = source_dir / "json"
                        json_dir.mkdir(exist_ok=True)
                        log_file = json_dir / log_name
                        with open(log_file, "w", encoding="utf-8") as f:
                            json.dump(log_content, f, indent=2, ensure_ascii=False)
                    else:
                        log_file = source_dir / log_name
                        log_file.write_text(str(log_content), encoding="utf-8")

            # 3. Create ZIP in NATIVE temp directory
            temp_zip_base = source_dir.parent / f"bundle_{app_id}"
            archive_result = shutil.make_archive(str(temp_zip_base), 'zip', source_dir)
            temp_zip_file = Path(archive_result)

            # 4. Move to final destination
            try:
                shutil.move(str(temp_zip_file), str(final_zip_path))
            except OSError as move_err:
                logger.debug(f"shutil.move failed ({move_err}), falling back to copyfile+unlink")
                shutil.copyfile(str(temp_zip_file), str(final_zip_path))
                temp_zip_file.unlink()
            
            # 5. Success: Return the path to the preserved ZIP file (Windows bulk transfer is a future roadmap)
            logger.info(f"Package successfully created as a ZIP archive: {final_zip_path}")
                
            return final_zip_path
            
        except Exception as e:
            logger.error(f"Failed to save package for {app_id}: {e}")
            return None

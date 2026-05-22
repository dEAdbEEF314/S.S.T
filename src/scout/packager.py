import shutil
import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("scout.packager")

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

            # 4. Move to Windows destination (Handle WSL metadata issues)
            try:
                shutil.move(str(temp_zip_file), str(final_zip_path))
            except OSError as move_err:
                logger.debug(f"shutil.move failed ({move_err}), falling back to copyfile+unlink")
                shutil.copyfile(str(temp_zip_file), str(final_zip_path))
                temp_zip_file.unlink()
            
            # 5. Extraction (Directly call Windows tar.exe from WSL)
            def wsl_to_win(wsl_p: Path) -> str:
                s = str(wsl_p)
                if s.startswith("/mnt/"):
                    parts = s.split("/")
                    drive = parts[2].upper()
                    rest = "\\".join(parts[3:])
                    return f"{drive}:\\{rest}"
                return s.replace("/", "\\")

            win_zip_path = wsl_to_win(final_zip_path)
            win_extract_dir = wsl_to_win(extract_dir)
            
            # Find tar.exe robustly
            def find_win_exe(name: str, fallback_path: str) -> str:
                exe = shutil.which(name)
                if not exe:
                    p = Path(fallback_path)
                    if p.exists(): exe = str(p)
                return exe

            raw_tar_exe = find_win_exe("tar.exe", "/mnt/c/Windows/System32/tar.exe")

            if not raw_tar_exe:
                logger.error(f"tar.exe not found in PATH or standard location. ZIP package remains at: {final_zip_path}")
                logger.warning("Please install or ensure tar.exe is available in your Windows system for automatic extraction.")
                return None

            if not final_zip_path.exists():
                logger.error(f"ZIP file disappeared before extraction: {final_zip_path}")
                return None

            # Create destination directory in Python (WSL side can do this on /mnt/)
            extract_dir.mkdir(parents=True, exist_ok=True)

            # Execute Windows tar.exe directly
            # Note: Win32 apps called from WSL expect Windows paths for their arguments
            logger.debug(f"Executing Windows tar: {raw_tar_exe} -xf {win_zip_path} -C {win_extract_dir}")
            result = subprocess.run([raw_tar_exe, "-xf", win_zip_path, "-C", win_extract_dir], capture_output=True)
            
            if result.returncode != 0:
                try:
                    err_msg = result.stderr.decode('cp932')
                except Exception:
                    err_msg = result.stderr.decode('utf-8', errors='replace')
                logger.error(f"Windows extraction failed for {app_id} (Code: {result.returncode}): {err_msg.strip()}")
                logger.warning(f"ZIP file preserved for manual extraction: {final_zip_path}")
                return None

            # 6. Success: Remove the ZIP file (SPEC: Intermediate ZIP should be deleted after successful extraction)
            try:
                final_zip_path.unlink(missing_ok=True)
                logger.info(f"Local package extracted and intermediate ZIP removed: {extract_dir}")
            except Exception as unlink_err:
                logger.warning(f"Failed to remove intermediate ZIP {final_zip_path}: {unlink_err}")
                
            return extract_dir
            
        except Exception as e:
            logger.error(f"Failed to save and extract package for {app_id}: {e}")
            return None

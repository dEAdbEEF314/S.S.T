import os
import shutil
import glob
import argparse
import sqlite3
from pathlib import Path
from sst.config import Config
from sst.utils import ensure_wsl_path

def clean(keep_steam_cache=False):
    print("--- S.S.T System Cleanup Started ---")
    
    config = Config()
    deleted_count = 0
    errors = []

    # 1. データベースのクリーンアップ (SST_DB_PATH に基づく)
    db_path = ensure_wsl_path(config.sst_db_path)
    if keep_steam_cache:
        try:
            if db_path.exists() and db_path.is_file():
                with sqlite3.connect(db_path) as conn:
                    conn.execute("DELETE FROM processed_albums;")
                print(f"Cleared processed_albums from database, kept steam cache: {db_path}")
                deleted_count += 1
        except Exception as e:
            errors.append(f"Failed to clear processed_albums from database {db_path}: {e}")
    else:
        db_dir = db_path.parent
        db_name = db_path.name
        if db_dir.exists() and db_dir.is_dir():
            for p in db_dir.glob(f"{db_name}*"):
                try:
                    if p.is_file():
                        p.unlink()
                        print(f"Removed database file: {p}")
                        deleted_count += 1
                except Exception as e:
                    errors.append(f"Failed to remove database file {p}: {e}")



    # 3. ログのクリーンアップ
    log_patterns = [
        ("logs", "SST_DEBUG_*.log"),
        ("logs", "*.log")
    ]
    for folder, pattern in log_patterns:
        folder_path = Path(folder)
        if folder_path.exists() and folder_path.is_dir():
            for p in folder_path.glob(pattern):
                try:
                    if p.is_file():
                        p.unlink()
                        print(f"Removed log file: {p}")
                        deleted_count += 1
                except Exception as e:
                    errors.append(f"Failed to remove log file {p}: {e}")

    # 4. 出力先ディレクトリ (SST_OUTPUT_DIR) 配下のクリーンアップ
    output_dir = ensure_wsl_path(config.sst_output_dir)
    output_dirs_to_clean = [output_dir]
    
    # フォールバックとして相対パスの output も確認
    try:
        resolved_out = Path("output").resolve()
        if Path("output").exists() and resolved_out != output_dir.resolve():
            output_dirs_to_clean.append(Path("output"))
    except Exception:
        pass


    for out_dir in output_dirs_to_clean:
        if out_dir.exists() and out_dir.is_dir():
            for p in out_dir.iterdir():
                try:
                    if p.is_file() or p.is_symlink():
                        p.unlink()
                        print(f"Removed output file: {p}")
                        deleted_count += 1
                    elif p.is_dir():
                        shutil.rmtree(p)
                        print(f"Removed output directory: {p}")
                        deleted_count += 1
                except Exception as e:
                    errors.append(f"Failed to remove output item {p}: {e}")

    # 5. 一時作業ディレクトリ (SST_WORKING_DIR) 配下のクリーンアップ
    working_dir = ensure_wsl_path(config.sst_working_dir)
    if working_dir.exists() and working_dir.is_dir():
        for p in working_dir.iterdir():
            try:
                if p.is_file() or p.is_symlink():
                    p.unlink()
                    print(f"Removed working file: {p}")
                    deleted_count += 1
                elif p.is_dir():
                    shutil.rmtree(p)
                    print(f"Removed working directory: {p}")
                    deleted_count += 1
            except Exception as e:
                errors.append(f"Failed to remove working item {p}: {e}")

    print(f"--- Cleanup Finished: {deleted_count} items removed ---")
    if errors:
        print("\nErrors encountered:")
        for err in errors:
            print(f"- {err}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean S.S.T system files.")
    parser.add_argument("--keep-steam-cache", action="store_true", help="Keep the Steam API/Store cache in the database")
    args = parser.parse_args()
    
    clean(keep_steam_cache=args.keep_steam_cache)


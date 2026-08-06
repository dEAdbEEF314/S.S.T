import os
import shutil
import argparse
import sqlite3
from pathlib import Path
from sst.config import Config
from sst.utils import ensure_path

def clean(keep_cache=True):
    print("--- S.S.T System Cleanup Started ---")
    
    config = Config()
    deleted_count = 0
    errors = []

    # 1. データベースのクリーンアップ (SST_DB_PATH に基づく)
    db_path = ensure_path(config.sst_db_path)
    if keep_cache:
        try:
            if db_path.exists() and db_path.is_file():
                with sqlite3.connect(db_path) as conn:
                    conn.execute("DELETE FROM processed_albums;")
                print(f"Cleared processed_albums from database, kept pre-fetch & steam caches: {db_path}")
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
    log_dir = Path("logs")
    if log_dir.exists() and log_dir.is_dir():
        for p in log_dir.glob("*.log"):
            try:
                p.unlink()
                print(f"Removed log file: {p}")
                deleted_count += 1
            except Exception as e:
                errors.append(f"Failed to remove log file {p}: {e}")

    # 4. Scanner/skill cache cleanup. The CLI currently passes data/sst_cache.json
    # as the ScannerCacheManager path, so this is a runtime cache, not disposable output.
    if not keep_cache:
        for cache_path in (Path("data/sst_cache.json"), Path("data/scout_cache.json")):
            try:
                if cache_path.is_file():
                    cache_path.unlink()
                    print(f"Removed scanner cache: {cache_path}")
                    deleted_count += 1
            except Exception as e:
                errors.append(f"Failed to remove scanner cache {cache_path}: {e}")

    # 5. 出力先ディレクトリ (SST_OUTPUT_DIR) 配下のクリーンアップ
    output_dir = ensure_path(config.sst_output_dir)
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

    # 6. 一時作業ディレクトリ (SST_WORKING_DIR) 配下のクリーンアップ
    working_dir = ensure_path(config.sst_working_dir)
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
    parser.add_argument("--keep-prefetch", action="store_true", help="Keep the pre-fetched API cache and Steam store data (Default behavior)")
    parser.add_argument("--clear-all-cache", action="store_true", help="Clear ALL caches from the database")
    parser.add_argument("--clear-steam-cache", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    
    keep_cache = not (args.clear_all_cache or args.clear_steam_cache)
    clean(keep_cache=keep_cache)


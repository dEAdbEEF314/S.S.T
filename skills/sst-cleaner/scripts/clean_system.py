import shutil
import argparse
import sqlite3
from pathlib import Path
from sst.config import Config
from sst.utils import ensure_path

def clean(keep_cache=True, app_ids=None):
    print("--- S.S.T System Cleanup Started ---")
    
    config = Config()
    db_path = ensure_path(config.sst_db_path)
    deleted_count = 0
    errors = []

    if app_ids:
        app_ids = sorted(set(app_ids))
        placeholders = ",".join("?" for _ in app_ids)
        try:
            with sqlite3.connect(db_path) as conn:
                for table in ("processed_albums", "steam_store_data", "api_cache"):
                    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                    if "app_id" not in columns:
                        continue
                    cursor = conn.execute(
                        f"DELETE FROM {table} WHERE app_id IN ({placeholders})",
                        app_ids,
                    )
                    deleted_count += cursor.rowcount
            print(f"Cleared AppID-scoped database rows: {', '.join(map(str, app_ids))}")
        except Exception as e:
            errors.append(f"Failed to clear AppID-scoped database rows: {e}")

        cache_path = Path("data/sst_cache.json")
        if cache_path.is_file():
            try:
                import json
                with cache_path.open("r", encoding="utf-8") as handle:
                    cache_data = json.load(handle)
                enriched = cache_data.get("enriched", {})
                removed_cache_keys = 0
                for app_id in app_ids:
                    if enriched.pop(str(app_id), None) is not None:
                        removed_cache_keys += 1
                if removed_cache_keys:
                    with cache_path.open("w", encoding="utf-8") as handle:
                        json.dump(cache_data, handle, indent=2, ensure_ascii=False)
                    deleted_count += removed_cache_keys
                print(f"Cleared {removed_cache_keys} scanner cache entries")
            except Exception as e:
                errors.append(f"Failed to clear scanner cache entries: {e}")

        output_dir = ensure_path(config.sst_output_dir)
        for output_base in (output_dir / "archive", output_dir / "review"):
            if output_base.is_dir():
                for app_id in app_ids:
                    for path in output_base.glob(f"{app_id}_*"):
                        try:
                            if path.is_dir():
                                shutil.rmtree(path)
                            else:
                                path.unlink()
                            deleted_count += 1
                        except Exception as e:
                            errors.append(f"Failed to remove targeted output {path}: {e}")

        working_dir = ensure_path(config.sst_working_dir)
        if working_dir.is_dir():
            for app_id in app_ids:
                for pattern in (f"final_{app_id}_*", f"buffer_{app_id}_*"):
                    for path in working_dir.glob(pattern):
                        try:
                            shutil.rmtree(path) if path.is_dir() else path.unlink()
                            deleted_count += 1
                        except Exception as e:
                            errors.append(f"Failed to remove targeted work item {path}: {e}")

        print(f"--- Targeted cleanup finished: {deleted_count} items removed ---")
        if errors:
            print("\nErrors encountered:")
            for err in errors:
                print(f"- {err}")
        return

    # 1. データベースのクリーンアップ (SST_DB_PATH に基づく)
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
    parser.add_argument("--appid", type=str, help="Comma-separated AppIDs for targeted cleanup")
    args = parser.parse_args()
    
    keep_cache = not (args.clear_all_cache or args.clear_steam_cache)
    app_ids = None
    if args.appid:
        raw_app_ids = [value.strip() for value in args.appid.split(",")]
        if any(not value for value in raw_app_ids):
            parser.error("--appid must contain comma-separated positive integers")
        try:
            parsed_app_ids = [int(value) for value in raw_app_ids]
        except ValueError:
            parser.error("--appid must contain comma-separated positive integers")
        if any(app_id <= 0 for app_id in parsed_app_ids):
            parser.error("--appid must contain comma-separated positive integers")
        app_ids = list(dict.fromkeys(parsed_app_ids))
    clean(keep_cache=keep_cache, app_ids=app_ids)


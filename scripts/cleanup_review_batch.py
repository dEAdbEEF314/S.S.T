#!/usr/bin/env python3
"""Cleanup Review Batch Artifacts and LLM Cache.

This script cleans up working directories, output artifacts, and DB records
specifically for the 69 Review AppIDs, while resetting data/llm_cache.json
and safely preserving external API caches (PICS, Steam Tags, AcoustID).
"""

import shutil
import sqlite3
from pathlib import Path

REVIEW_APP_IDS = [
    221001, 335370, 336860, 457840, 459851, 461050, 467300, 467870,
    553670, 584382, 584383, 689920, 692510, 698890, 706870, 789870,
    802640, 802980, 865290, 870530, 905290, 916190, 924330, 924331,
    925660, 942070, 954690, 1029810, 1075710, 1108260, 1224940, 1270860,
    1495710, 1568690, 1586580, 1593020, 1621040, 1702020, 1761580, 1796120,
    1851920, 1879310, 1944840, 2125650, 2195300, 2294270, 2337040, 2339210,
    2410560, 2455450, 2583400, 2716920, 2769790, 2845440, 2943720, 2966860,
    3107200, 3162910, 3205740, 3222820, 3282950, 3449720, 3508870, 3533020,
    3812400, 4206020, 4282460, 4304640, 4447100,
]


def cleanup():
    print(f"🧹 Starting cleanup for {len(REVIEW_APP_IDS)} Review AppIDs...")

    # 1. Delete LLM Cache
    llm_cache_path = Path("data/llm_cache.json")
    if llm_cache_path.exists():
        llm_cache_path.unlink()
        print("  ✓ Deleted data/llm_cache.json (LLM cache reset)")
    else:
        print("  - data/llm_cache.json did not exist")

    # 2. Cleanup working directory (sst-work/)
    sst_work_paths = [Path("sst-work"), Path("/tmp/sst-work")]
    for work_dir in sst_work_paths:
        if work_dir.exists():
            deleted_count = 0
            for item in work_dir.iterdir():
                if item.is_dir():
                    # Check if dirname contains any review app_id
                    for aid in REVIEW_APP_IDS:
                        if str(aid) in item.name:
                            shutil.rmtree(item, ignore_errors=True)
                            deleted_count += 1
                            break
            print(f"  ✓ Cleaned {deleted_count} app directories from {work_dir}")

    # 3. Cleanup output directory (output/review/, output/archive/)
    output_dir = Path("output")
    if output_dir.exists():
        deleted_output = 0
        for sub in ["review", "archive", "work"]:
            sub_dir = output_dir / sub
            if not sub_dir.exists():
                continue
            for item in list(sub_dir.iterdir()):
                for aid in REVIEW_APP_IDS:
                    if str(aid) in item.name:
                        if item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                        else:
                            item.unlink(missing_ok=True)
                        deleted_output += 1
                        break
        print(f"  ✓ Removed {deleted_output} artifact entries from output/ for review AppIDs")

    # 4. Cleanup DB records
    db_paths = [Path("data/sst_local_state.db"), Path("data/sst.db")]
    for db_path in db_paths:
        if db_path.exists():
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [r[0] for r in cursor.fetchall()]

                deleted_rows = 0
                for table in tables:
                    if table in ("local_process_results", '"local_process_results"', "processed_albums"):
                        cursor.execute(f"DELETE FROM {table} WHERE app_id IN ({','.join(map(str, REVIEW_APP_IDS))})")
                        deleted_rows += cursor.rowcount

                conn.commit()
                conn.close()
                print(f"  ✓ Deleted {deleted_rows} result rows from {db_path}")
            except Exception as e:
                print(f"  ! DB cleanup error for {db_path}: {e}")

    # 5. Verify preserved caches
    print("\n🔍 Verifying preserved caches:")
    for path_str in ["data/sst_cache.json", "data/steam_tags.json", "data/userdata.json"]:
        p = Path(path_str)
        if p.exists():
            print(f"  ✅ Preserved {path_str} ({p.stat().st_size} bytes)")
        else:
            print(f"  - {path_str} (not present)")

    print(f"\n✨ Cleanup completed successfully for all {len(REVIEW_APP_IDS)} Review AppIDs.")


if __name__ == "__main__":
    cleanup()

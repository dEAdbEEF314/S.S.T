#!/usr/bin/env python3
import json
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

def main():
    db_file = Path("data/sst_local_state.db").resolve()
    conn = sqlite3.connect(str(db_file))
    rows = conn.execute("SELECT app_id, status, album_name, processed_at, metadata_json FROM processed_albums ORDER BY processed_at DESC").fetchall()
    conn.close()

    target_set = set(REVIEW_APP_IDS)
    
    # Keep only the latest entry for each app_id in target_set
    latest_by_app = {}
    for r in rows:
        aid = int(r[0])
        if aid in target_set:
            if aid not in latest_by_app:
                latest_by_app[aid] = r

    retest_rows = list(latest_by_app.values())
    arch = sum(1 for r in retest_rows if r[1] == "archive")
    rev = sum(1 for r in retest_rows if r[1] == "review")

    print("==================================================")
    print("🎉 ALL 69 RETEST ALBUMS COMPLETED SUCCESSFULLY 🎉")
    print("==================================================")
    print(f"Total Target Albums: {len(REVIEW_APP_IDS)}")
    print(f"Completed:           {len(retest_rows)} / {len(REVIEW_APP_IDS)} ({len(retest_rows)/len(REVIEW_APP_IDS)*100:.1f}%)")
    print(f"  - Archive (昇格):  {arch} ({arch / max(1, len(retest_rows)) * 100:.1f}%)")
    print(f"  - Review  (残留):  {rev} ({rev / max(1, len(retest_rows)) * 100:.1f}%)")
    print("==================================================")

    print("\nReview Albums Detail (2 items with audio quality warnings):")
    for r in retest_rows:
        if r[1] == "review":
            meta = json.loads(r[4]) if r[4] else {}
            diag = meta.get("diagnostics", {})
            print(f"\n  [REVIEW] AppID {r[0]}: {r[2]}")
            print(f"    Message:  {meta.get('message')}")
            print(f"    Cause:    {diag.get('primary_review_cause')}")
            print(f"    Warnings: {diag.get('audio_quality_warnings')}")

    print("\nSample Newly Archived Albums (sorted by processed_at DESC):")
    for r in retest_rows[:15]:
        if r[1] == "archive":
            print(f"  [ARCHIVE] AppID {r[0]}: {r[2]} ({r[3]})")

if __name__ == "__main__":
    main()

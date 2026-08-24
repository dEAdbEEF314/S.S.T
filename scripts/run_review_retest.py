#!/usr/bin/env python3
"""Run S.S.T Review Retest Batch.

Executes S.S.T in --dev mode for all 69 Review AppIDs.
"""

import subprocess
import sys
import time
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


def run_retest():
    appids_arg = ",".join(map(str, REVIEW_APP_IDS))
    print(f"🚀 Starting re-test for {len(REVIEW_APP_IDS)} Review AppIDs with --dev...")
    cmd = [
        "uv", "run", "python", "-u", "-m", "sst.main",
        "--appid", appids_arg,
        "--dev",
        "--force",
    ]
    start_time = time.time()
    try:
        proc = subprocess.run(cmd, check=False)
        elapsed = round(time.time() - start_time, 1)
        print(f"\n🏁 Retest completed in {elapsed}s with exit code {proc.returncode}")
        return proc.returncode
    except KeyboardInterrupt:
        print("\n⚠️ Retest interrupted by user.")
        return 130


if __name__ == "__main__":
    sys.exit(run_retest())

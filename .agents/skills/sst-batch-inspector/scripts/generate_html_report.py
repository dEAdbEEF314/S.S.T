"""Compatibility entry point for the canonical post-batch HTML report."""

from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "sst-post-batch-investigator" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from generate_post_batch_report import analyze_and_generate_report


if __name__ == "__main__":
    analyze_and_generate_report()

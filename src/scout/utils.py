import re
import os
import subprocess
from pathlib import Path
from typing import Optional

def windows_to_wsl_path(win_path: str) -> Path:
    """
    Converts a Windows-style path (C:\...) to a WSL2 mount path (/mnt/c/...).
    If the path is already a valid WSL path, it returns it as a Path object.
    """
    if not win_path:
        return Path()

    # 1. Check if it's already a WSL path (starts with /)
    if win_path.startswith('/'):
        return Path(win_path)

    # 2. Handle Windows Drive Letter (e.g., C:\...)
    match = re.match(r'^([a-zA-Z]):\\?(.*)', win_path)
    if match:
        drive = match.group(1).lower()
        remainder = match.group(2).replace('\\', '/')
        return Path(f"/mnt/{drive}/{remainder}")

    # 3. If it doesn't match a drive letter, just normalize slashes
    return Path(win_path.replace('\\', '/'))

def ensure_wsl_path(any_path: str) -> Path:
    """Ensures the path is usable in the current WSL2 environment."""
    return windows_to_wsl_path(any_path)

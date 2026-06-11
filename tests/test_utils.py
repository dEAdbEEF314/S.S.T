import pytest
from pathlib import Path
from sst.utils import windows_to_wsl_path, ensure_wsl_path

def test_windows_to_wsl_path():
    # Test valid Windows paths
    assert windows_to_wsl_path(r"C:\Program Files (x86)\Steam") == Path("/mnt/c/Program Files (x86)/Steam")
    assert windows_to_wsl_path(r"D:\Games\SteamLibrary") == Path("/mnt/d/Games/SteamLibrary")
    
    # Test already valid WSL paths
    assert windows_to_wsl_path("/mnt/c/Program Files (x86)/Steam") == Path("/mnt/c/Program Files (x86)/Steam")
    assert windows_to_wsl_path("/home/user/test") == Path("/home/user/test")
    
    # Test paths without drive letter
    assert windows_to_wsl_path(r"folder\subfolder") == Path("folder/subfolder")
    
    # Test empty path
    assert windows_to_wsl_path("") == Path()

def test_ensure_wsl_path():
    # ensure_wsl_path is an alias
    assert ensure_wsl_path(r"C:\Test") == Path("/mnt/c/Test")

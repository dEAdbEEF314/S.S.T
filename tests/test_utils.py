from pathlib import Path
from sst.utils import normalize_path, ensure_path

def test_normalize_path():
    # Test valid Windows paths
    assert normalize_path(r"C:\Program Files (x86)\Steam") == Path("/mnt/c/Program Files (x86)/Steam")
    assert normalize_path(r"D:\Games\SteamLibrary") == Path("/mnt/d/Games/SteamLibrary")
    
    # Test already valid WSL paths
    assert normalize_path("/mnt/c/Program Files (x86)/Steam") == Path("/mnt/c/Program Files (x86)/Steam")
    assert normalize_path("/home/user/test") == Path("/home/user/test")
    
    # Test paths without drive letter
    assert normalize_path(r"folder\subfolder") == Path("folder/subfolder")
    
    # Test empty path
    assert normalize_path("") == Path()

def test_ensure_path():
    assert ensure_path(r"C:\Test") == Path("/mnt/c/Test")


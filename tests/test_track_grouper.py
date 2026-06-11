import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from sst.track_grouper import TrackManager

@pytest.fixture
def mock_dependencies():
    with patch("sst.track_grouper.EmbeddedMetadataExtractor.extract") as mock_extract, \
         patch("sst.track_grouper.TrackManager.get_duration") as mock_duration:
        # Default mock behavior
        mock_extract.return_value = {}
        mock_duration.return_value = 120.0
        yield mock_extract, mock_duration

def test_group_by_logical_track_basic(mock_dependencies):
    mock_extract, mock_duration = mock_dependencies
    
    # Simulate three files: two MP3s and one FLAC
    files = [
        Path("/mnt/c/Games/Soundtrack/01 - Main Theme.mp3"),
        Path("/mnt/c/Games/Soundtrack/01. Main Theme.flac"),
        Path("/mnt/c/Games/Soundtrack/02 - Battle.mp3")
    ]
    
    # The normalization logic should group "01 - Main Theme.mp3" and "01. Main Theme.flac" together
    groups = TrackManager.group_by_logical_track(files)
    
    # We expect 2 groups: "main theme" and "battle"
    assert len(groups) == 2
    
    # Find the keys (they should be tuples of (disc_num, normalized_stem))
    keys = list(groups.keys())
    stems = [k[1] for k in keys]
    
    assert "main theme" in stems
    assert "battle" in stems
    
    # "main theme" group should have 2 variants
    main_theme_key = next(k for k in keys if k[1] == "main theme")
    assert len(groups[main_theme_key]) == 2
    
    # "battle" group should have 1 variant
    battle_key = next(k for k in keys if k[1] == "battle")
    assert len(groups[battle_key]) == 1

def test_group_by_logical_track_with_album_name_removal(mock_dependencies):
    mock_extract, mock_duration = mock_dependencies
    
    files = [
        Path("/mnt/c/Games/Soundtrack/01 - Epic Game Soundtrack - Main Theme.mp3"),
    ]
    
    groups = TrackManager.group_by_logical_track(files, album_name="Epic Game Soundtrack")
    assert len(groups) == 1
    
    key = list(groups.keys())[0]
    # The album name and noise should be stripped, leaving just "main theme"
    assert key[1] == "main theme"

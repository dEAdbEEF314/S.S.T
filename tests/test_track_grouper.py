import pytest
from types import SimpleNamespace
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
    groups = TrackManager.build_file_records(files)
    
    # We expect 2 groups: "main theme" and "battle"
    assert len(groups) == 3
    
    # Find the keys (they should be tuples of (disc_num, normalized_stem))
    keys = list(groups.keys())
    stems = [k[1] for k in keys]
    
    assert sum(stem.startswith("main theme::") for stem in stems) == 2
    assert sum(stem.startswith("battle::") for stem in stems) == 1
    
    # Each physical format remains an independent record.
    main_theme_keys = [k for k in keys if k[1].startswith("main theme::")]
    assert len(main_theme_keys) == 2
    assert all(len(groups[key]) == 1 for key in main_theme_keys)
    
    # "battle" remains a single physical record.
    battle_key = next(k for k in keys if k[1].startswith("battle::"))
    assert len(groups[battle_key]) == 1

def test_group_by_logical_track_with_album_name_removal(mock_dependencies):
    mock_extract, mock_duration = mock_dependencies
    
    files = [
        Path("/mnt/c/Games/Soundtrack/01 - Epic Game Soundtrack - Main Theme.mp3"),
    ]
    
    groups = TrackManager.build_file_records(files, album_name="Epic Game Soundtrack")
    assert len(groups) == 1
    
    key = list(groups.keys())[0]
    # The album name and noise should be stripped, leaving just "main theme"
    assert key[1].startswith("main theme::")

def test_smart_normalization():
    test_cases = [
        ("01. Vermilion", "vermilion"),
        ("01. Title (Instrumental)", "title instrumental"),
        ("01. Title", "title"),
        ("Title (High-Res Lossless)", "title"),
        ("02 - Battle Theme [Arrange]", "battle theme arrange"),
        ("03 - Bonus Track", "bonus track"),
        ("Song (Short Ver.)", "song short ver"),
        ("Song (Remix)", "song remix")
    ]
    
    for stem, expected in test_cases:
        assert TrackManager.normalize_title(stem) == expected


def test_audio_quality_tiers_are_fixed():
    groups = {
        (1, "main theme"): [
            {"path": Path("track.wav"), "format": "wav", "filename_track": 1},
            {"path": Path("track.mp3"), "format": "mp3", "filename_track": 1},
        ],
        (1, "battle"): [
            {"path": Path("battle.ogg"), "format": "ogg", "filename_track": 2},
        ],
    }

    assert TrackManager.get_quality_tier(groups[(1, "main theme")][0]["format"]) == 0
    assert TrackManager.get_quality_tier(groups[(1, "main theme")][1]["format"]) == 3
    assert TrackManager.get_quality_tier(groups[(1, "battle")][0]["format"]) == 2


def test_audio_quality_tier_ignores_configurable_format_priority(monkeypatch):
    monkeypatch.setenv("AUDIO_QUALITY_TIER_PRIORITY", "mp3,wav")
    groups = {
        (1, "main theme"): [
            {"path": Path("track.mp3"), "format": "mp3", "filename_track": 1},
            {"path": Path("track.wav"), "format": "wav", "filename_track": 1},
        ],
    }

    assert TrackManager.get_audio_format_priority()[0] == "wav"
    assert TrackManager.get_quality_tier("wav") == 0


@pytest.mark.parametrize("file_format", ["wav", "ogg", "aac", "m4a"])
def test_get_best_artwork_reads_embedded_art_from_all_supported_formats(file_format):
    artwork = b"cover"
    fake_audio = SimpleNamespace(
        tags={"covr": [artwork]},
        pictures=[SimpleNamespace(data=artwork)],
    )

    with patch("mutagen.File", return_value=fake_audio):
        result = TrackManager.get_best_artwork([
            {"path": Path(f"track.{file_format}"), "format": file_format},
        ])

    assert result == artwork

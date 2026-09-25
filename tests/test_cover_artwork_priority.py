from unittest.mock import MagicMock, patch
from sst.models import SteamMetadata
from sst.processor_support import fetch_album_artwork

def test_single_soundtrack_prefers_parent_header():
    steam_meta = SteamMetadata(
        app_id=1001,
        name="Game OST",
        parent_app_id=2001,
        parent_name="Main Game",
        header_image_url="https://example.com/ost_header.jpg",
        parent_header_image_url="https://example.com/game_header.jpg",
        has_sibling_soundtracks=False
    )
    
    mock_config = MagicMock()
    mock_mbz = MagicMock()
    mock_mbz.get_release_artwork_url.return_value = None

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake_parent_image_bytes"
        mock_get.return_value = mock_resp

        art = fetch_album_artwork(mock_config, mock_mbz, steam_meta, [], track_groups=None)
        assert art == b"fake_parent_image_bytes"
        assert mock_get.call_args_list[0][0][0] == "https://example.com/game_header.jpg"

def test_sibling_soundtracks_prefer_soundtrack_header():
    steam_meta = SteamMetadata(
        app_id=1002,
        name="Game OST Vol.2",
        parent_app_id=2001,
        parent_name="Main Game",
        header_image_url="https://example.com/ost_vol2_header.jpg",
        parent_header_image_url="https://example.com/game_header.jpg",
        has_sibling_soundtracks=True
    )
    
    mock_config = MagicMock()
    mock_mbz = MagicMock()
    mock_mbz.get_release_artwork_url.return_value = None

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake_soundtrack_image_bytes"
        mock_get.return_value = mock_resp

        art = fetch_album_artwork(mock_config, mock_mbz, steam_meta, [], track_groups=None)
        assert art == b"fake_soundtrack_image_bytes"
        assert mock_get.call_args_list[0][0][0] == "https://example.com/ost_vol2_header.jpg"

def test_standalone_soundtrack_uses_soundtrack_header():
    steam_meta = SteamMetadata(
        app_id=1003,
        name="Standalone Album",
        parent_app_id=None,
        header_image_url="https://example.com/standalone_header.jpg",
        has_sibling_soundtracks=False
    )
    
    mock_config = MagicMock()
    mock_mbz = MagicMock()
    mock_mbz.get_release_artwork_url.return_value = None

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake_standalone_image_bytes"
        mock_get.return_value = mock_resp

        art = fetch_album_artwork(mock_config, mock_mbz, steam_meta, [], track_groups=None)
        assert art == b"fake_standalone_image_bytes"
        assert mock_get.call_args_list[0][0][0] == "https://example.com/standalone_header.jpg"

def test_embedded_artwork_skips_lazy_mbz_candidate_search():
    steam_meta = SteamMetadata(app_id=1004, name="Embedded OST")
    mbz_artwork_candidate_provider = MagicMock(return_value={"mbid": "release-id"})

    with patch("sst.processor_support.TrackManager.get_best_artwork", return_value=b"embedded_art"):
        art = fetch_album_artwork(
            MagicMock(),
            MagicMock(),
            steam_meta,
            [],
            track_groups={(1, "track"): [{}]},
            mbz_artwork_candidate_provider=mbz_artwork_candidate_provider,
        )

    assert art == b"embedded_art"
    mbz_artwork_candidate_provider.assert_not_called()

def test_lazy_mbz_artwork_candidate_precedes_steam_fallback():
    steam_meta = SteamMetadata(
        app_id=1005,
        name="MBZ OST",
        header_image_url="https://example.com/steam_header.jpg",
    )
    mock_mbz = MagicMock()
    mock_mbz.get_release_artwork_url.return_value = "https://example.com/mbz_cover.jpg"
    mbz_artwork_candidate_provider = MagicMock(return_value={"mbid": "release-id"})

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"mbz_cover_bytes"
        mock_get.return_value = mock_resp

        art = fetch_album_artwork(
            MagicMock(),
            mock_mbz,
            steam_meta,
            [],
            track_groups=None,
            mbz_artwork_candidate_provider=mbz_artwork_candidate_provider,
        )

    assert art == b"mbz_cover_bytes"
    mbz_artwork_candidate_provider.assert_called_once_with()
    mock_mbz.get_release_artwork_url.assert_called_once_with("release-id")
    assert mock_get.call_args_list[0][0][0] == "https://example.com/mbz_cover.jpg"

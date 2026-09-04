from unittest.mock import MagicMock, patch

from sst.processor_support import fetch_album_artwork
from sst.models import SteamMetadata
from sst.validator import ResultValidator
from sst.llm.organizer import LLMOrganizer
from sst.track_grouper import TrackManager


def test_fetch_album_artwork_steam_fallback():
    """mbz_client.download_artwork を呼ばず requests.get で Steam ヘッダー画像を取得できること"""
    config = MagicMock()
    mbz_client = MagicMock(spec=["get_release_artwork_url"]) # download_artwork を持たない
    steam_meta = SteamMetadata(
        app_id=1832420,
        name="Test Score",
        header_image_url="http://example.com/header.jpg",
    )

    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"FAKE_JPEG_BINARY"
        
        art = fetch_album_artwork(
            config=config,
            mbz_client=mbz_client,
            steam_meta=steam_meta,
            mbz_candidates=[],
            track_groups=None,
        )
        assert art == b"FAKE_JPEG_BINARY"
        mock_get.assert_called_once_with("http://example.com/header.jpg", timeout=15)


def test_validator_uses_unassigned_manifest():
    """ResultValidator が alignment_res の生データではなく unassigned_manifest（空）を真実として判定すること"""
    llm_log = {
        "phase1_res": {
            "identity_confidence": 100,
            "integrity_quality": 100,
            "strategy": "STEAM_BASED",
            "archive_vs_review_ratio": {"archive": 100, "review": 0},
            "confidence_reason": "STEAM-TRUST",
        },
        "alignment_res": {
            "unassigned_files": ["stale_file_id_flac_variant"], # 古い生データ
        },
    }
    steam_meta = SteamMetadata(
        app_id=706870,
        name="X-Morph",
        store_tracklist=[{"disc": 1, "number": "1", "title": "Track 1"}],
    )
    tracks = [{
        "tags": {"disc_number": "1", "track_number": "1", "title": "Track 1"},
        "title_source": "STEAM",
    }]
    
    # unassigned_manifest が空（バリアント統合で解決済み）の場合、archive と判定されること
    status, message, score, quality, reason = ResultValidator.validate(
        app_id=706870,
        tracks=tracks,
        llm_log=llm_log,
        mbz_candidates=[],
        steam_meta=steam_meta,
        audio_fail=False,
        audio_warn=False,
        unassigned_manifest=[], # 最終マニフェストは空
    )
    assert status == "archive"
    assert "Unassigned Files" not in message


def test_resolve_slot_key_0_indexed():
    """LLM が '0' から始まる 0-indexed スロットキーを返しても先頭スロット（v_idx=0）に解決されること"""
    full_ref_steam = [
        {"v_idx": 0, "n": 1, "t": "Track 1"},
        {"v_idx": 1, "n": 2, "t": "Track 2"},
    ]
    
    # "0" が渡された場合 -> 0番目のスロット（v_idx=0）に解決
    idx_0 = LLMOrganizer._resolve_slot_key_to_v_idx("0", full_ref_steam)
    assert idx_0 == 0

    # "1" が渡された場合 -> 直接マッチまたは 1番目のスロット（v_idx=0）に解決
    idx_1 = LLMOrganizer._resolve_slot_key_to_v_idx("1", full_ref_steam)
    assert idx_1 == 0


def test_track_grouper_multi_disc_compound_pattern(tmp_path):
    """'1_1背景音乐.mp3' や '2_1歌曲.mp3' の形式から Disc と Track 番号が正しく抽出されること"""
    f1 = tmp_path / "1_1背景音乐 公园正门.mp3"
    f2 = tmp_path / "2_1歌曲 爆炸.mp3"
    f1.write_bytes(b"dummy")
    f2.write_bytes(b"dummy")

    with patch("sst.track_grouper.EmbeddedMetadataExtractor.extract", return_value={}), \
         patch("sst.track_grouper.TrackManager.get_duration", return_value=120.0):
        records = TrackManager.build_file_records([f1, f2], album_name="Chicken Hill OST")
        
        # 2つのレコードがそれぞれ (disc=1, ...) と (disc=2, ...) に分かれていること
        discs = [k[0] for k in records.keys()]
        assert 1 in discs
        assert 2 in discs
        
        # ファイルの filename_track が 1（Disc 1 の Track 1, Disc 2 の Track 1）であること
        for key, vars in records.items():
            disc_num = key[0]
            track_rec = vars[0]
            assert track_rec["disc"] == disc_num
            assert track_rec["filename_track"] == 1

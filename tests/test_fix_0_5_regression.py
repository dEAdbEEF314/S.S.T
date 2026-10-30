from pathlib import Path
from unittest.mock import patch, MagicMock

from sst.models import SteamMetadata
from sst.processing.slot_variants import build_slot_variant_index
from sst.tagger import AudioTagger
from sst.llm.prompts import build_differential_mapping_prompt, build_mapping_prompt
from sst.track_grouper import TrackManager


def test_ffmpeg_vn_suppresses_video_stream(tmp_path: Path):
    """Test that AudioTagger.convert_and_limit includes '-vn' to safely discard embedded artwork videos."""
    tagger = AudioTagger(tmp_path)
    source_file = tmp_path / "test_track.mp3"
    source_file.write_bytes(b"dummy audio content")

    with patch("subprocess.run") as mock_run:
        # Mock successful ffmpeg execution
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stderr = b""
        mock_run.return_value = mock_proc

        # Mock target path creation
        target_path = tmp_path / "test_track.mp3"
        target_path.write_bytes(b"output audio content")

        res_path, has_warn = tagger.convert_and_limit(source_file, tier="lossy")

        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert "-vn" in cmd, f"Expected '-vn' in ffmpeg command, but got: {cmd}"
        assert cmd[cmd.index("-vn") - 1] == str(source_file) or "-vn" in cmd


def test_multidisc_continuous_numbering_real_case_integration():
    """Test that AppID 1879310 pattern (continuous numbered brother WAV/MP3 in flat folder
    where Steam Disc 2 starts at track 1 with Japanese title) integrates WAV into Disc 2 slot.
    """
    final_metadata = {
        "2_stage 5 boss::mp3_20": {
            "matched_v_idx": 1,
        }
    }

    track_groups = {
        (2, "stage 5 boss::mp3_20"): [
            {
                "file_id": "mp3_20",
                "path": Path("/music/20. Stage 5 Boss.mp3"),
                "format": "mp3",
                "duration": 180.0,
                "norm_stem": "stage 5 boss",
                "disc": 1,
                "t_num_val": "20",
            }
        ],
        (1, "stage 5 boss::wav_20"): [
            {
                "file_id": "wav_20",
                "path": Path("/music/20. Stage 5 Boss.wav"),
                "format": "wav",
                "duration": 180.0,
                "norm_stem": "stage 5 boss",
                "disc": 1,
                "t_num_val": "20",
            }
        ],
    }

    steam_meta = SteamMetadata(
        app_id="1879310",
        name="TCSTRIKERS4",
        store_tracklist=[
            {"disc": 1, "number": 1, "title": "Track 1"},
            {"disc": 2, "number": 1, "title": "テクノロジークライシス"},
        ],
    )

    orig_get_dur = TrackManager.get_duration
    try:
        TrackManager.get_duration = staticmethod(lambda p: 180.0)
        slot_variants, track_to_slot = build_slot_variant_index(
            final_metadata=final_metadata,
            track_groups=track_groups,
            steam_meta=steam_meta,
        )
    finally:
        TrackManager.get_duration = orig_get_dur

    # Slot (2, '1') must exist and hold both mp3 and wav variants
    assert (2, "1") in slot_variants
    assert len(slot_variants[(2, "1")]) == 2
    variant_fids = [v["file_id"] for v in slot_variants[(2, "1")]]
    assert "mp3_20" in variant_fids
    assert "wav_20" in variant_fids

    # Unaligned wav must not remain in its own unaligned slot key
    assert (1, "stage 5 boss::wav_20") not in slot_variants
    assert track_to_slot["1_stage 5 boss::wav_20"] == (2, "1")


def test_prompts_include_track_number_anchor_rules():
    """Test that LLM prompts enforce track number matching over minor duration differences."""
    diff_prompt = build_differential_mapping_prompt(
        global_res={"global_tags": {"album": "Test"}},
        unfilled_steam_slots=[{"slot_key": "1_1", "t": "Track 1"}],
        unmatched_local_tracks=[{"local_key": [1, "01_track1"]}],
        user_language="ja",
    )
    assert "prioritize matching by track number over slight differences in duration" in diff_prompt
    assert "NEVER swap adjacent numbered tracks simply because of minor duration differences" in diff_prompt

    mapping_prompt = build_mapping_prompt(
        global_res={"global_tags": {"album": "Test"}},
        s_mbz_search={},
        v_mbz_search=None,
        ref_steam=[{"slot_key": "1_1", "t": "Track 1"}],
        ref_fingerprint=[],
        s_chunk=[{"local_key": [1, "01_track1"]}],
        start_idx=0,
        user_language="ja",
    )
    assert "prioritize matching by track number over slight differences in duration" in mapping_prompt
    assert "NEVER swap adjacent numbered tracks simply because of minor duration differences" in mapping_prompt

from sst.llm.prematch import resolve_prematch_signals


def test_acoustid_match_resolves_steam_slot():
    local_tracks = [
        {"file_ids": ["fid-1"], "track_num": 1, "v_idx": 0, "title": "Track 1"},
        {"file_ids": ["fid-2"], "track_num": 2, "v_idx": 1, "title": "Track 2"},
    ]
    full_ref_steam = [
        {"v_idx": 0, "n": 1, "t": "Track 1"},
        {"v_idx": 1, "n": 2, "t": "Track 2"},
    ]
    full_ref_fingerprint = [
        {"v_idx": 0, "n": 1, "mbz_idx": 10, "t": "Track 1 (MBZ)"},
        {"v_idx": 1, "n": 2, "mbz_idx": 11, "t": "Track 2 (MBZ)"},
    ]

    prematch = resolve_prematch_signals(
        local_tracks=local_tracks,
        full_ref_steam=full_ref_steam,
        full_ref_fingerprint=full_ref_fingerprint,
        full_ref_mbz_search=[],
    )

    assert "fid-1" in prematch
    assert prematch["fid-1"].acoustid_steam_slot == 1
    assert prematch["fid-1"].mbz_track_index == 10
    assert prematch["fid-1"].override_track == "1"
    assert "acoustid_match" in prematch["fid-1"].evidence

    assert "fid-2" in prematch
    assert prematch["fid-2"].acoustid_steam_slot == 2
    assert prematch["fid-2"].mbz_track_index == 11


def test_mbz_search_match_by_track_number():
    local_tracks = [
        {"file_ids": ["fid-search"], "track_num": 3, "title": "Search Song"},
    ]
    full_ref_steam = [
        {"v_idx": 2, "n": 3, "t": "Search Song"},
    ]
    full_ref_mbz_search = [
        {"v_idx": 2, "n": 3, "mbz_idx": 5, "t": "Search Song"},
    ]

    prematch = resolve_prematch_signals(
        local_tracks=local_tracks,
        full_ref_steam=full_ref_steam,
        full_ref_fingerprint=[],
        full_ref_mbz_search=full_ref_mbz_search,
        v_mbz_search={"tracks": [{"title": "Search Song"}]},
    )

    assert "fid-search" in prematch
    assert prematch["fid-search"].mbz_search_steam_slot == 3
    assert prematch["fid-search"].mbz_track_index == 5
    assert "mbz_search_match" in prematch["fid-search"].evidence


def test_prematch_with_no_signals():
    local_tracks = [
        {"file_ids": ["fid-none"], "title": "Unknown"},
    ]

    prematch = resolve_prematch_signals(
        local_tracks=local_tracks,
        full_ref_steam=[],
        full_ref_fingerprint=[],
        full_ref_mbz_search=[],
    )

    assert "fid-none" in prematch
    assert prematch["fid-none"].acoustid_steam_slot is None
    assert prematch["fid-none"].mbz_track_index is None
    assert prematch["fid-none"].evidence == []


def test_prematch_multiformat_same_slot():
    local_tracks = [
        {"file_ids": ["fid-wav", "fid-mp3"], "track_num": 1, "v_idx": 0, "title": "Main Theme"},
    ]
    full_ref_steam = [
        {"v_idx": 0, "n": 1, "t": "Main Theme"},
    ]
    full_ref_fingerprint = [
        {"v_idx": 0, "n": 1, "mbz_idx": 0, "t": "Main Theme"},
    ]

    prematch = resolve_prematch_signals(
        local_tracks=local_tracks,
        full_ref_steam=full_ref_steam,
        full_ref_fingerprint=full_ref_fingerprint,
        full_ref_mbz_search=[],
    )

    assert prematch["fid-wav"].acoustid_steam_slot == 1
    assert prematch["fid-mp3"].acoustid_steam_slot == 1
    assert prematch["fid-wav"].mbz_track_index == 0
    assert prematch["fid-mp3"].mbz_track_index == 0

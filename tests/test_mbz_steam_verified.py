from pathlib import Path
from types import SimpleNamespace

import pytest

from sst.alignment_flow import collect_alignment_inputs, execute_alignment_flow
from sst.alignment_inputs import (
    AlignmentInputBuilder,
    verify_steam_linked_mbz_release,
)
from sst.builder import MetadataBuilder
from sst.ident.mbz import MusicBrainzIdentifier
from sst.models import SteamMetadata


def test_direct_steam_link_requires_exact_store_app_path():
    assert MusicBrainzIdentifier._is_direct_steam_link(
        "https://store.steampowered.com/app/692510/", 692510
    )
    assert MusicBrainzIdentifier._is_direct_steam_link(
        "https://store.steampowered.com/app/692510", 692510
    )
    assert not MusicBrainzIdentifier._is_direct_steam_link(
        "https://store.steampowered.com/app/6925100/", 692510
    )
    assert not MusicBrainzIdentifier._is_direct_steam_link(
        "https://example.invalid/store.steampowered.com/app/692510/", 692510
    )
    assert not MusicBrainzIdentifier._is_direct_steam_link(
        "https://steamdb.info/app/692510/", 692510
    )


def test_direct_steam_link_candidate_outranks_higher_scoring_release(monkeypatch):
    identifier = MusicBrainzIdentifier(
        "test", "1", "test@example.invalid", rate_limit_delay=0,
        scoring_config={"direct_steam_link": -1000},
    )
    release_details = {
        "linked-release": {
            "url-relation-list": [{
                "target": "https://store.steampowered.com/app/692510/",
            }],
            "medium-list": [{
                "position": 1,
                "format": "Digital Media",
                "track-list": [{
                    "position": 1,
                    "length": "100000",
                    "recording": {
                        "id": "recording-linked",
                        "title": "Linked Theme",
                        "length": "100000",
                        "artist-credit-phrase": "Linked Artist",
                    },
                }],
            }],
        },
        "scored-release": {
            "url-relation-list": [],
            "medium-list": [{
                "position": 1,
                "format": "Digital Media",
                "track-list": [{
                    "position": 1,
                    "length": "100000",
                    "recording": {
                        "id": "recording-other",
                        "title": "Other Theme",
                        "length": "100000",
                        "artist-credit-phrase": "Other Artist",
                    },
                }],
            }],
        },
    }
    monkeypatch.setattr(
        "sst.ident.mbz.musicbrainzngs.search_releases",
        lambda **kwargs: {
            "release-list": [
                {"id": "scored-release", "title": "Candidate"},
                {"id": "linked-release", "title": "Candidate"},
            ]
        },
    )
    monkeypatch.setattr(
        identifier,
        "_fetch_release",
        lambda mbid, includes=None: release_details[mbid],
    )

    candidates, search_log = identifier.search_release(
        "Candidate", 1, app_id=692510
    )

    assert candidates[0]["mbid"] == "linked-release"
    assert candidates[0]["direct_steam_link"] is True
    assert candidates[0]["tracks"][0]["recording_id"] == "recording-linked"
    assert candidates[0]["tracks"][0]["disc"] == 1
    assert candidates[0]["direct_steam_link_candidate_count"] == 1
    assert search_log["ranked_candidates"][0]["mbid"] == "linked-release"


def test_forced_fingerprint_scan_checks_every_local_file():
    class FakeAcoustID:
        def __init__(self):
            self.scanned = []

        def identify_track(self, path):
            self.scanned.append(path)
            return []

    class FakeMusicBrainz:
        pass

    client = FakeAcoustID()
    builder = AlignmentInputBuilder(
        client, FakeMusicBrainz(), fingerprint_all=False, fingerprint_sample_size=2
    )
    groups = {
        (1, f"track-{index}"): [{"path": Path(f"track-{index}.flac")}]
        for index in range(5)
    }
    candidates_by_key = {}
    completed = []

    result = builder.build_fingerprint_album(
        groups,
        on_track_complete=lambda: completed.append(True),
        force_all=True,
        on_track_candidates=lambda key, candidates: candidates_by_key.update(
            {key: candidates}
        ),
    )

    assert result is None
    assert len(client.scanned) == len(groups)
    assert set(candidates_by_key) == set(groups)
    assert len(completed) == len(groups)


def test_steam_linked_release_verification_allows_format_variants():
    release = {
        "direct_steam_link": True,
        "direct_steam_link_candidate_count": 1,
        "tracks": [
            {"mbid": "recording-1", "disc": 1, "position": 1, "title": "First"},
            {"mbid": "recording-2", "disc": 2, "position": 1, "title": "Second"},
        ],
    }
    groups = {
        (1, "first-flac"): [{}],
        (1, "first-mp3"): [{}],
        (2, "second-flac"): [{}],
    }
    acoustid = {
        (1, "first-flac"): [{"mbid": "recording-1"}],
        (1, "first-mp3"): [{"mbid": "recording-1"}],
        (2, "second-flac"): [{"mbid": "recording-2"}],
    }

    mapping = verify_steam_linked_mbz_release(release, groups, acoustid)

    assert mapping is not None
    assert mapping["1_first-flac"]["position"] == 1
    assert mapping["1_first-mp3"]["mbid"] == "recording-1"
    assert mapping["2_second-flac"]["disc"] == 2


def test_verified_release_survives_same_mbid_signal_unification():
    release_bundle = {
        "direct_steam_link": True,
        "direct_steam_link_candidate_count": 1,
        "mbid": "same-release",
        "album_name": "Verified Album",
        "tracks": [{
            "disc": 1,
            "position": 1,
            "title": "Verified Track",
            "mbid": "recording-1",
            "mbz_track_index": 0,
        }],
    }

    class FakeBuilder:
        def build_steam_album(self, steam_meta):
            return {"tracks": []}

        def build_local_album(self, track_groups):
            return {"tracks": []}

        def build_mbz_search_album(self, *args):
            return release_bundle.copy()

        def build_fingerprint_album(
            self, track_groups, on_track_candidates=None, **kwargs
        ):
            if on_track_candidates:
                on_track_candidates(
                    (1, "local track"), [{"mbid": "recording-1"}]
                )
            return {"mbid": "same-release", "tracks": []}

    _, _, fingerprint_bundle, mbz_bundle, _ = collect_alignment_inputs(
        692510,
        SteamMetadata(app_id=692510, name="Steam Product", store_tracklist=[]),
        {(1, "local track"): [{}]},
        FakeBuilder(),
        lambda *args, **kwargs: None,
    )

    assert fingerprint_bundle is not None
    assert mbz_bundle is not None
    assert mbz_bundle["steam_link_verified"] is True
    assert mbz_bundle["verified_local_mapping"]["1_local track"]["mbid"] == "recording-1"


@pytest.mark.parametrize(
    ("release_overrides", "acoustid_overrides"),
    [
        ({"direct_steam_link": False}, {}),
        ({"direct_steam_link_candidate_count": 2}, {}),
        ({}, {(1, "first"): []}),
        ({}, {(1, "first"): [{"mbid": "recording-1"}, {"mbid": "recording-2"}]}),
        ({}, {(1, "second"): [{"mbid": "recording-1"}]}),
    ],
)
def test_steam_linked_release_verification_rejects_unproven_mapping(
    release_overrides, acoustid_overrides
):
    release = {
        "direct_steam_link": True,
        "direct_steam_link_candidate_count": 1,
        "tracks": [
            {"mbid": "recording-1", "disc": 1, "position": 1, "title": "First"},
            {"mbid": "recording-2", "disc": 1, "position": 2, "title": "Second"},
        ],
        **release_overrides,
    }
    groups = {(1, "first"): [{}], (1, "second"): [{}]}
    acoustid = {
        (1, "first"): [{"mbid": "recording-1"}],
        (1, "second"): [{"mbid": "recording-2"}],
        **acoustid_overrides,
    }

    assert verify_steam_linked_mbz_release(release, groups, acoustid) is None


def test_verified_mbz_alignment_bypasses_llm_and_uses_release_slots():
    steam = SteamMetadata(
        app_id=692510,
        name="Steam Product",
        store_tracklist=[{"disc": 1, "number": "1", "title": "Steam Title"}],
    )
    track_groups = {(1, "local track"): [{}]}
    verified_search = {
        "steam_link_verified": True,
        "mbid": "release-id",
        "album_name": "MBZ Album",
        "artist": "MBZ Album Artist",
        "year": "2020",
        "label": "MBZ Label",
        "score": 500,
        "tracks": [{
            "disc": 2,
            "position": 3,
            "title": "MBZ Track",
            "recording_artist": "MBZ Track Artist",
            "mbid": "recording-id",
            "mbz_track_index": 0,
        }],
        "verified_local_mapping": {
            "1_local track": {
                "disc": 2,
                "position": 3,
                "title": "MBZ Track",
                "recording_artist": "MBZ Track Artist",
                "recording_id": "recording-id",
                "mbz_track_index": 0,
            }
        },
        "authoritative_tracklist": [{
            "disc": 2,
            "number": "3",
            "title": "MBZ Track",
            "recording_id": "recording-id",
        }],
    }
    local = {
        "tracks": [{
            "local_key": (1, "local track"),
            "file_ids": ["synthetic-file-id"],
        }]
    }

    result = execute_alignment_flow(
        app_id=692510,
        steam_meta=steam,
        track_groups=track_groups,
        execution_profile=SimpleNamespace(prefer_one_shot=True),
        alignment_input_builder=SimpleNamespace(),
        llm=object(),
        diagnostics={},
        diag=lambda *args, **kwargs: None,
        on_track_complete=None,
        llm_progress_callback=None,
        check_fast_track=lambda *args, **kwargs: (False, None, None),
        build_fast_track_alignment_result=lambda *args, **kwargs: None,
        build_mbz_candidates=lambda *args, **kwargs: [{"steam_link_verified": True}],
        resolve_duplicate_mappings=lambda *args, **kwargs: None,
        reconcile_unassigned_slots=lambda *args, **kwargs: [],
        build_slot_variant_index=lambda *args, **kwargs: ({}, {}),
        collect_inputs=lambda *args, **kwargs: (
            {"tracks": []},
            local,
            None,
            verified_search,
            {},
        ),
        consolidate_inputs=lambda *args, **kwargs: pytest.fail(
            "LLM must not run for a verified MBZ release"
        ),
    )

    assert result[5] == "MBZ_STEAM_VERIFIED"
    assert result[0]["1_local track"]["override_track"] == "3"
    assert result[0]["1_local track"]["override_disc"] == "2"
    assert result[0]["1_local track"]["acoustid_mbid"] == "recording-id"
    assert result[1]["phase1_res"]["strategy"] == "MBZ_STEAM_VERIFIED"
    assert result[1]["alignment_res"]["slots"]["2_3"]["files"] == [
        "synthetic-file-id"
    ]
    assert result[8]["tracks"] == []
    assert result[11]["authoritative_tracklist"][0]["number"] == "3"


def test_verified_mbz_fields_override_steam_in_tag_map():
    steam = SteamMetadata(
        app_id=692510,
        name="Steam Product",
        developer="Steam Developer",
        publisher="Steam Publisher",
        release_date="2017-01-01",
        genres=["Action"],
        store_tracklist=[{
            "disc": 1,
            "number": "1",
            "title": "Steam Title",
        }],
    )
    mbz_candidates = [{
        "steam_link_verified": True,
        "album": "MBZ Album",
        "artist": "MBZ Album Artist",
        "year": "2020",
        "tracks": [{
            "disc": 2,
            "position": 3,
            "title": "MBZ Track",
            "recording_artist": "MBZ Track Artist",
        }],
    }]

    tags = MetadataBuilder.build_tag_map(
        app_id=692510,
        disc=1,
        clean_title="local track",
        adopted_info={"filename_track": 1, "path": Path("synthetic.flac")},
        steam_meta=steam,
        instr={
            "matched_v_idx": 0,
            "override_track": "3",
            "override_disc": "2",
            "chosen_mbz_index": 0,
            "mbz_track_index": 0,
            "mbz_track_artist": "MBZ Track Artist",
        },
        mbz_candidates=mbz_candidates,
        track_sources={},
        user_language_639_2="jpn",
        slot_embedded_tags={},
        global_identity={},
        total_discs=1,
    )

    assert tags["title"] == "MBZ Track"
    assert tags["title_source"] == "MBZ_STEAM_VERIFIED"
    assert tags["artist"] == "MBZ Track Artist"
    assert tags["album"] == "MBZ Album"
    assert tags["album_artist"] == "MBZ Album Artist"
    assert tags["year"] == "2020"
    assert tags["track_number"] == "3"
    assert tags["disc_number"] == "2/2"
    assert tags["genre"] == "STEAM VGM, Action"
    assert tags["_field_provenance"]["title"] == "MBZ_STEAM_VERIFIED"
    assert tags["_field_provenance"]["album"] == "MBZ_STEAM_VERIFIED"
    assert tags["_field_provenance"]["album_artist"] == "MBZ_STEAM_VERIFIED"
    assert tags["_field_provenance"]["year"] == "MBZ_STEAM_VERIFIED"
    assert tags["_field_provenance"]["track_number"] == "MBZ_STEAM_VERIFIED"
    assert tags["_field_provenance"]["disc_number"] == "MBZ_STEAM_VERIFIED"

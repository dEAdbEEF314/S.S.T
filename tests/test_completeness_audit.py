import importlib.util
import json
from pathlib import Path


def _load_audit_module():
    script = Path(__file__).resolve().parents[1] / "scripts/completeness_audit.py"
    spec = importlib.util.spec_from_file_location("sst_completeness_audit", script)
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load completeness audit script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(app_id, route, status="archive"):
    tracks = [
        {
            "file_path": "disc_1/01 Theme.aif",
            "title_source": "STEAM",
            "source_format": "flac",
            "tags": {"disc_number": "1/1", "track_number": "1", "title": "Theme"},
        },
        {
            "file_path": "disc_1/02 Other.aif",
            "title_source": "STEAM",
            "source_format": "wav",
            "tags": {"disc_number": "1/1", "track_number": "2", "title": "Other"},
        },
    ]
    meta = {
        "processing_route": route,
        "tracks": tracks,
        "steam_info": {
            "store_tracklist": [
                {"disc": 1, "number": "1", "title": "Theme"},
                {"disc": 1, "number": "2", "title": "Other"},
            ]
        },
    }
    return {
        "app_id": app_id,
        "album_name": f"Synthetic Album {app_id}",
        "status": status,
        "metadata_json": json.dumps(meta),
    }


def test_route_stratified_sample_is_reproducible_and_path_safe():
    module = _load_audit_module()
    rows = [
        _row(1, "FAST_TRACK"),
        _row(2, "FAST_TRACK"),
        _row(3, "LLM_ONE_SHOT"),
        _row(4, "LLM_ONE_SHOT", status="review"),
    ]

    first = module.build_sample_manifest(rows, per_stratum=1, tracks_per_album=1, seed=17)
    second = module.build_sample_manifest(rows, per_stratum=1, tracks_per_album=1, seed=17)

    assert [sample["app_id"] for sample in first["samples"]] == [sample["app_id"] for sample in second["samples"]]
    assert {(item["route"], item["status"]) for item in first["samples"]} == {
        ("FAST_TRACK", "archive"),
        ("LLM_ONE_SHOT", "archive"),
        ("LLM_ONE_SHOT", "review"),
    }
    assert all(sample["audit_labels"]["product_identity_correct"] is None for sample in first["samples"])
    assert all(not track["zip_member"].startswith("/") for sample in first["samples"] for track in sample["sampled_tracks"])
    assert module._safe_zip_member("../../private/audio.aif") is None


def test_accuracy_summary_excludes_unrated_labels_and_reports_wilson_interval():
    module = _load_audit_module()
    manifest = module.build_sample_manifest(
        [_row(1, "FAST_TRACK"), _row(2, "FAST_TRACK")],
        per_stratum=2,
        tracks_per_album=1,
        seed=3,
    )
    manifest["samples"][0]["audit_labels"]["product_identity_correct"] = True
    manifest["samples"][1]["audit_labels"]["product_identity_correct"] = False
    manifest["samples"][0]["sampled_tracks"][0][module.TRACK_LABEL] = True

    summary = module.analyze_manifest(manifest)
    route = summary["route_metrics"]["FAST_TRACK"]
    identity = route["product_identity_correct"]

    assert identity["successes"] == 1
    assert identity["failures"] == 1
    assert identity["unrated"] == 0
    assert identity["rate_pct"] == 50.0
    assert identity["wilson_95_pct"][0] < 50 < identity["wilson_95_pct"][1]
    assert route[module.TRACK_LABEL]["rated"] == 1
    assert route[module.TRACK_LABEL]["unrated"] == 1
    assert route[module.DERIVED_AUDIO_LABEL]["successes"] == 1
    assert route[module.DERIVED_AUDIO_LABEL]["unrated"] == 1
    assert summary["stratum_metrics"]["FAST_TRACK|archive"]["album_sample_count"] == 2


def test_unrated_sample_does_not_report_accuracy_as_zero_or_perfect():
    module = _load_audit_module()
    manifest = module.build_sample_manifest([_row(1, "MBZ_STEAM_VERIFIED")], seed=5)

    metric = module.analyze_manifest(manifest)["route_metrics"]["MBZ_STEAM_VERIFIED"][
        "audio_content_matches_title"
    ]

    assert metric["rated"] == 0
    assert metric["unrated"] == 2
    assert metric["rate_pct"] is None
    assert metric["wilson_95_pct"] is None

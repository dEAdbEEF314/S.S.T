from sst.models import SteamMetadata
from sst.builder import MetadataBuilder
from sst.processor_support import resolve_duplicate_mappings

def test_builder_sanitizes_clean_title_hash():
    steam_meta = SteamMetadata(
        app_id=123,
        name="Test Album",
        developer="Test Dev",
        publisher="Test Pub",
        parent_name="Test Game"
    )
    
    # Simulate a fallback track where clean_title has internal ::hash
    tag_map = MetadataBuilder.build_tag_map(
        app_id=123,
        disc=1,
        clean_title="gingebread house::d15114fae86548aa",
        adopted_info={"format": "wav", "tier": "lossless"},
        steam_meta=steam_meta,
        instr={"action": "use_local_tag"},
        mbz_candidates=[],
        track_sources={},
        user_language_639_2="jpn",
        slot_embedded_tags={},
        global_identity={}
    )
    
    assert tag_map["title"] == "gingebread house"
    assert "::" not in tag_map["title"]

def test_builder_unescapes_album_artist_html_entities():
    steam_meta = SteamMetadata(
        app_id=123,
        name="Test Album",
        developer="Hammer &amp; Ravens",
        publisher="Hammer &amp; Ravens",
        parent_name="Test Game"
    )
    
    tag_map = MetadataBuilder.build_tag_map(
        app_id=123,
        disc=1,
        clean_title="Track 1",
        adopted_info={"format": "flac", "tier": "lossless"},
        steam_meta=steam_meta,
        instr={"action": "use_steam", "steam_title": "Track 1", "steam_track": 1},
        mbz_candidates=[],
        track_sources={},
        user_language_639_2="jpn",
        slot_embedded_tags={},
        global_identity={}
    )
    
    assert tag_map["album_artist"] == "Hammer & Ravens, Hammer & Ravens"
    assert "&amp;" not in tag_map["album_artist"]

def test_resolve_duplicate_mappings_merges_multiformat_variants():
    steam_meta = SteamMetadata(
        app_id=123,
        name="Test Album",
        store_tracklist=[
            {"disc": 1, "track": 1, "title": "Track 1", "duration_s": "120"}
        ]
    )
    
    # 2 track groups for the same slot (v_idx=0): WAV and MP3 with different filename stems but same duration
    track_groups = {
        (1, "theme wav::111"): [{"format": "wav", "duration": 120.2, "file_id": "111"}],
        (1, "theme mp3::222"): [{"format": "mp3", "duration": 120.0, "file_id": "222"}]
    }
    
    final_metadata = {
        "1_theme wav::111": {"matched_v_idx": 0, "action": "use_steam"},
        "1_theme mp3::222": {"matched_v_idx": 0, "action": "use_steam"}
    }
    
    resolve_duplicate_mappings(123, final_metadata, steam_meta, track_groups)
    
    # WAV and MP3 should be merged into one group, and the duplicate final_metadata entry removed
    assert len(track_groups) == 1
    assert len(final_metadata) == 1
    # Both variants should be retained in the winning group
    merged_variants = list(track_groups.values())[0]
    assert len(merged_variants) == 2

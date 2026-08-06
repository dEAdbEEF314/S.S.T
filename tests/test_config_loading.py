from sst.config import Config, DEFAULT_METADATA_SOURCE_PRIORITY
from sst.track_grouper import TrackManager


def test_config_uses_new_metadata_fallback_priority_field_for_reports_and_llm():
    config = Config(
        steam_install_path="/tmp",
        metadata_source_priority="STEAM,FINGERPRINT,MBZ_SEARCH,LOCAL",
        metadata_field_fallback_priority="STEAM,ACOUSTID,MBZ_RELEASE,MBZ_SEARCH,EMBED,LOCAL",
    )

    assert config.resolved_metadata_source_priority == DEFAULT_METADATA_SOURCE_PRIORITY
    assert config.build_llm_organizer_kwargs()["metadata_source_priority"] == DEFAULT_METADATA_SOURCE_PRIORITY


def test_track_manager_uses_spec_audio_format_priority(monkeypatch):
    monkeypatch.setenv("AUDIO_QUALITY_TIER_PRIORITY", "wav,flac,mp3")
    monkeypatch.setenv("AUDIO_FORMAT_PRIORITY", "mp3,wav")

    assert TrackManager.get_audio_format_priority() == ["wav", "flac", "alac", "aiff", "aif", "ogg", "aac", "m4a", "mp3"]


def test_track_manager_ignores_legacy_audio_format_env_name(monkeypatch):
    monkeypatch.delenv("AUDIO_QUALITY_TIER_PRIORITY", raising=False)
    monkeypatch.setenv("AUDIO_FORMAT_PRIORITY", "flac,mp3")

    assert TrackManager.get_audio_format_priority() == ["wav", "flac", "alac", "aiff", "aif", "ogg", "aac", "m4a", "mp3"]


def test_track_manager_uses_fixed_spec_audio_priority_when_env_is_absent(monkeypatch):
    monkeypatch.delenv("AUDIO_QUALITY_TIER_PRIORITY", raising=False)
    monkeypatch.delenv("AUDIO_FORMAT_PRIORITY", raising=False)

    assert TrackManager.get_audio_format_priority() == ["wav", "flac", "alac", "aiff", "aif", "ogg", "aac", "m4a", "mp3"]
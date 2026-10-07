import re
from datetime import datetime
from pathlib import Path
from unittest.mock import call, MagicMock, patch

import pytest
from pydantic import ValidationError

from sst.config import Config
from sst.llm.organizer import LLMOrganizer
from sst.notify import NotificationManager
from sst.track_grouper import TrackManager


def make_test_config(**kwargs):
    kwargs.setdefault("steam_install_path", "/tmp")
    kwargs.setdefault("steam_library_path", "/tmp/steam-library")
    return Config(**kwargs)


def test_steam_library_path_is_required(monkeypatch):
    monkeypatch.delenv("STEAM_LIBRARY_PATH", raising=False)

    with pytest.raises(ValidationError, match="steam_library_path"):
        Config(steam_install_path="/tmp", _env_file=None)


def test_config_uses_new_metadata_fallback_priority_field_for_reports_and_llm(caplog):
    config = make_test_config(
        steam_install_path="/tmp",
        metadata_source_priority="LEGACY,LOCAL",
        metadata_field_fallback_priority="CURRENT,LOCAL",
    )

    assert config.resolved_metadata_source_priority == "CURRENT,LOCAL"
    assert config.build_llm_organizer_kwargs()["metadata_source_priority"] == "CURRENT,LOCAL"
    assert "METADATA_SOURCE_PRIORITY" in caplog.text
    assert "無視されます" in caplog.text


def test_legacy_metadata_priority_is_used_when_current_field_is_unset(monkeypatch, caplog):
    monkeypatch.delenv("METADATA_FIELD_FALLBACK_PRIORITY", raising=False)
    config = make_test_config(
        steam_install_path="/tmp",
        metadata_source_priority="LEGACY,LOCAL",
        _env_file=None,
    )

    assert config.resolved_metadata_source_priority == "LEGACY,LOCAL"
    assert "METADATA_FIELD_FALLBACK_PRIORITY" in caplog.text
    assert "直ちに移し" in caplog.text


def test_legacy_metadata_priority_environment_is_used_as_fallback(monkeypatch, caplog):
    monkeypatch.delenv("METADATA_FIELD_FALLBACK_PRIORITY", raising=False)
    monkeypatch.setenv("STEAM_INSTALL_PATH", "/tmp")
    monkeypatch.setenv("METADATA_SOURCE_PRIORITY", "LEGACY_ENV,LOCAL")

    config = make_test_config(_env_file=None)

    assert config.resolved_metadata_source_priority == "LEGACY_ENV,LOCAL"
    assert "METADATA_FIELD_FALLBACK_PRIORITY" in caplog.text


def test_default_mbz_scoring_matches_documented_penalties():
    config = make_test_config(_env_file=None)

    scoring = config.build_mbz_scoring_config()

    assert scoring["track_count_penalty_per_track"] == 20
    assert scoring["track_count_penalty_max"] == 300


def test_active_config_fields_are_sampled_and_documented():
    repository_root = Path(__file__).parents[1]
    env_example = (repository_root / ".env.example").read_text(encoding="utf-8")
    configuration_guide = (repository_root / "docs/configuration.md").read_text(encoding="utf-8")
    sample_keys = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", env_example, re.MULTILINE))
    documentation_keys = set(re.findall(r"`([A-Z][A-Z0-9_]*)`", configuration_guide))
    env_aliases = {"fingerprint_all": "SST_FINGERPRINT_ALL"}
    documented_legacy_only = {"metadata_source_priority"}

    for field_name in Config.model_fields:
        env_name = env_aliases.get(field_name, field_name.upper())
        assert env_name in documentation_keys, f"{env_name} is missing from docs/configuration.md"
        if field_name not in documented_legacy_only:
            assert env_name in sample_keys, f"{env_name} is missing from .env.example"


def test_documented_config_defaults_match_config_fields():
    repository_root = Path(__file__).parents[1]
    documentation_lines = (repository_root / "docs/configuration.md").read_text(
        encoding="utf-8"
    ).splitlines()
    env_aliases = {"fingerprint_all": "SST_FINGERPRINT_ALL"}

    for field_name, model_field in Config.model_fields.items():
        default = model_field.default
        if default is None or str(default) == "PydanticUndefined":
            continue

        env_name = env_aliases.get(field_name, field_name.upper())
        field_lines = [
            line
            for line in documentation_lines
            if line.lstrip().startswith("-") and f"`{env_name}`" in line
        ]
        assert len(field_lines) == 1, (
            f"{env_name} must have exactly one setting entry in docs/configuration.md"
        )
        documented_line = field_lines[0]
        assert "既定" in documented_line, f"{env_name} default is not documented"

        normalized_line = documented_line.replace(",", "")
        if isinstance(default, bool):
            expected_value = str(default).lower()
            assert expected_value in normalized_line.lower(), env_name
        elif isinstance(default, (int, float)):
            expected_values = [str(default)]
            if isinstance(default, float) and default.is_integer():
                expected_values.append(str(int(default)))
            assert any(
                re.search(
                    rf"(?<![\d.]){re.escape(expected_value)}(?![\d.])",
                    normalized_line,
                )
                for expected_value in expected_values
            ), env_name
        else:
            assert f"`{default}`" in documented_line, env_name


def test_config_unit_metadata_matches_documented_units():
    repository_root = Path(__file__).parents[1]
    documentation_lines = (repository_root / "docs/configuration.md").read_text(
        encoding="utf-8"
    ).splitlines()
    env_aliases = {"fingerprint_all": "SST_FINGERPRINT_ALL"}

    for field_name, model_field in Config.model_fields.items():
        metadata = model_field.json_schema_extra
        if not isinstance(metadata, dict) or "unit" not in metadata:
            continue

        env_name = env_aliases.get(field_name, field_name.upper())
        field_lines = [
            line
            for line in documentation_lines
            if line.lstrip().startswith("-") and f"`{env_name}`" in line
        ]
        assert len(field_lines) == 1, f"{env_name} must have one docs entry"
        assert model_field.description, f"{env_name} is missing its field description"
        display_unit = metadata.get("display_unit")
        assert isinstance(display_unit, str) and display_unit in field_lines[0], env_name


def test_env_example_overrides_only_the_documented_profile():
    repository_root = Path(__file__).parents[1]
    documented_overrides = {
        "steam_install_path",
        "sst_output_dir",
        "steam_library_path",
        "steam_login_secure",
        "steam_pics_bridge_api_key",
        "steam_web_api_key",
        "llm_backend",
        "llm_api_key",
        "llm_model",
        "llm_ollama_num_ctx",
        "llm_ollama_num_predict",
        "llm_request_parallelism_max_workers",
        "metadata_field_fallback_priority",
        "mbz_contact",
        "acoustid_api_key",
        "discord_webhook_critical",
        "discord_webhook_warning",
        "discord_webhook_info",
        "discord_webhook_completion",
    }

    with patch.dict("os.environ", {}, clear=True):
        defaults = make_test_config(steam_install_path="/synthetic", _env_file=None)
        sample = Config(_env_file=repository_root / ".env.example")

    actual_overrides = {
        field_name
        for field_name in Config.model_fields
        if getattr(defaults, field_name) != getattr(sample, field_name)
    }

    assert actual_overrides == documented_overrides


def test_fingerprint_all_reads_supported_name_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("SST_FINGERPRINT_ALL", raising=False)
    monkeypatch.delenv("FINGERPRINT_ALL", raising=False)
    env_file = tmp_path / "settings.env"
    env_file.write_text(
        "STEAM_INSTALL_PATH=/tmp\nSTEAM_LIBRARY_PATH=/tmp/library\nSST_FINGERPRINT_ALL=false\n",
        encoding="utf-8",
    )

    config = make_test_config(_env_file=env_file)

    assert config.fingerprint_all is False


def test_local_path_and_userdata_timeout_settings_read_environment(monkeypatch):
    monkeypatch.setenv("SST_LOG_DIR", "custom/logs")
    monkeypatch.setenv("SST_LOCK_PATH", "custom/run.lock")
    monkeypatch.setenv("SST_USERDATA_PATH", "custom/userdata.json")
    monkeypatch.setenv("SST_STEAM_CACHE_PATH", "custom/steam-cache.json")
    monkeypatch.setenv("SST_STEAM_TAG_CACHE_PATH", "custom/steam-tag-cache.json")
    monkeypatch.setenv("SST_AUDIT_REPORT_DIR", "custom/audit")
    monkeypatch.setenv("STEAM_USERDATA_TIMEOUT", "23")

    config = make_test_config(_env_file=None)

    assert config.sst_log_dir == "custom/logs"
    assert config.sst_lock_path == "custom/run.lock"
    assert config.sst_userdata_path == "custom/userdata.json"
    assert config.sst_steam_cache_path == "custom/steam-cache.json"
    assert config.sst_steam_tag_cache_path == "custom/steam-tag-cache.json"
    assert config.sst_audit_report_dir == "custom/audit"
    assert config.steam_userdata_timeout == 23


def test_load_env_overrides_checks_env_file_permissions():
    with patch("sst.config.check_env_security") as check_env_security:
        config = make_test_config(_env_file=None)

        assert config.load_env_overrides() is config

    check_env_security.assert_called_once_with()


def test_ollama_thinking_is_disabled_by_default_and_passed_to_llm_client():
    config = make_test_config()

    assert config.llm_ollama_think is False
    assert config.build_llm_organizer_kwargs()["ollama_think"] is False


def test_vram_manager_timeouts_are_configurable():
    from sst.vram_manager import VramResourceManager

    config = make_test_config(
        steam_install_path="/tmp",
        _env_file=None,
        llm_preflight_timeout=23,
        llm_health_check_timeout=11,
    )
    gpu_result = MagicMock(returncode=0, stdout="8192\n")
    ps_response = MagicMock()
    ps_response.json.return_value = {"models": [{"name": "test-model", "size_vram": 1}]}

    with patch("sst.vram_manager.subprocess.run", return_value=gpu_result) as run, patch(
        "sst.vram_manager.requests.post"
    ) as post, patch("sst.vram_manager.requests.get", return_value=ps_response) as get:
        VramResourceManager(
            "http://localhost:11434",
            "test-model",
            preflight_timeout=config.llm_preflight_timeout,
            health_check_timeout=config.llm_health_check_timeout,
        )

    assert run.call_args.kwargs["timeout"] == 5
    assert post.call_args.kwargs["timeout"] == 23
    assert get.call_args.kwargs["timeout"] == 11


def test_deferred_copy_delay_defaults_to_ten_minutes(monkeypatch):
    monkeypatch.delenv("SST_DEFERRED_COPY_DELAY_SECONDS", raising=False)

    config = make_test_config()

    assert config.sst_deferred_copy_delay_seconds == 600


def test_deferred_copy_delay_reads_environment_override(monkeypatch):
    monkeypatch.setenv("SST_DEFERRED_COPY_DELAY_SECONDS", "42")

    config = make_test_config()

    assert config.sst_deferred_copy_delay_seconds == 42


def test_notification_retry_settings_read_environment(monkeypatch):
    monkeypatch.setenv("NOTIFY_REQUEST_TIMEOUT", "17")
    monkeypatch.setenv("NOTIFY_MAX_RETRIES", "4")
    monkeypatch.setenv("NOTIFY_RETRY_DELAY", "3.5")
    monkeypatch.setenv("NOTIFY_RETRY_BACKOFF", "2")

    config = make_test_config(_env_file=None)

    assert config.notify_request_timeout == 17
    assert config.notify_max_retries == 4
    assert config.notify_retry_delay == 3.5
    assert config.notify_retry_backoff == 2


def test_notification_uses_configured_timeout_and_retry_schedule():
    config = make_test_config(
        steam_install_path="/tmp",
        _env_file=None,
        notify_enabled=True,
        discord_webhook_info="https://example.invalid/webhook/test",
        notify_request_timeout=17,
        notify_max_retries=3,
        notify_retry_delay=3,
        notify_retry_backoff=2,
    )
    success_response = MagicMock()

    with patch(
        "sst.notify.requests.post",
        side_effect=[RuntimeError("temporary failure"), RuntimeError("temporary failure"), success_response],
    ) as post, patch("sst.notify.time.sleep") as sleep:
        NotificationManager(config).notify("info", "title", "message")

    assert post.call_count == 3
    assert all(request.kwargs["timeout"] == 17 for request in post.call_args_list)
    assert sleep.call_args_list == [call(3.0), call(6.0)]


def test_notification_embed_timestamp_is_local_timezone_aware():
    config = make_test_config(
        steam_install_path="/tmp",
        _env_file=None,
        notify_enabled=True,
        discord_webhook_info="https://example.invalid/webhook/test",
    )

    with patch("sst.notify.requests.post") as post:
        NotificationManager(config).notify("info", "title", "message")

    timestamp = post.call_args.kwargs["json"]["embeds"][0]["timestamp"]
    parsed = datetime.fromisoformat(timestamp)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == datetime.now().astimezone().utcoffset()


def test_organizer_forwards_ollama_think_to_client(tmp_path):
    config = make_test_config(
        steam_install_path="/tmp",
        sst_llm_cache_path=str(tmp_path / "llm_cache.json"),
    )

    organizer = LLMOrganizer(**config.build_llm_organizer_kwargs())

    assert organizer.client.ollama_think is False


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
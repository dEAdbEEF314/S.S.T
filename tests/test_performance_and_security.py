import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sst.config import Config, check_env_security
from sst.utils import (
    is_private_ip,
    safe_validate_url,
    mask_secret,
    sanitize_log_text,
    is_safe_subpath,
)
from sst.packager import PackageManager
from sst.track_grouper import TrackManager
from sst.processor_support import safe_download_image
from sst.tagger import AudioTagger
from sst.ident.embedded import EmbeddedMetadataExtractor
from sst.processor import LocalProcessor
from sst.models import SteamMetadata
import subprocess


# ==============================================================================
# 1. Performance Tests
# ==============================================================================

def test_track_manager_duration_fast_path():
    """Verify that TrackManager.get_duration uses mutagen directly without subprocess."""
    work_files = list(Path("sst-work").rglob("*.flac")) + list(Path("sst-work").rglob("*.mp3"))
    if not work_files:
        pytest.skip("No sample audio files found in sst-work")

    sample_file = work_files[0]
    with patch("subprocess.run") as mock_sub:
        duration = TrackManager.get_duration(sample_file)
        assert duration > 0.0
        # subprocess.run (ffprobe) should NOT be called because mutagen resolved it
        assert not mock_sub.called


def test_track_manager_duration_ffprobe_fallback():
    """Verify fallback to ffprobe when mutagen is unable to parse the file."""
    with tempfile.NamedTemporaryFile(suffix=".mp3") as tmp:
        tmp.write(b"not a valid audio file header")
        tmp.flush()

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(stdout="42.5\n")
            duration = TrackManager.get_duration(Path(tmp.name))
            assert duration == 42.5
            assert mock_sub.called


def test_hybrid_zip_compression_strategies():
    """Verify the 3 compression strategies (auto, stored, deflate) and path traversal guard."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "source"
        src.mkdir()
        (src / "song.flac").write_bytes(b"FLAC_DATA" * 50)
        (src / "cover.jpg").write_bytes(b"JPEG_DATA" * 50)
        (src / "lyrics.txt").write_text("Hello lyrics " * 50)
        (src / "album.json").write_text('{"name": "test"}')

        out = Path(tmpdir) / "output"
        out.mkdir()

        # Strategy 1: auto (multimedia stored, text deflated)
        pkg_auto = PackageManager.save_local_package(
            app_id=100,
            status="archive",
            album_name="Auto Album",
            source_dir=src,
            logs={"summary.json": {"ok": True}},
            output_root=str(out),
            compression_strategy="auto",
        )
        assert pkg_auto is not None and pkg_auto.exists()
        with zipfile.ZipFile(pkg_auto, "r") as zf:
            info_map = {zi.filename: zi.compress_type for zi in zf.infolist()}
            assert info_map["song.flac"] == zipfile.ZIP_STORED
            assert info_map["cover.jpg"] == zipfile.ZIP_STORED
            assert info_map["lyrics.txt"] == zipfile.ZIP_DEFLATED
            assert info_map["album.json"] == zipfile.ZIP_DEFLATED

        # Strategy 2: stored (everything stored)
        pkg_stored = PackageManager.save_local_package(
            app_id=200,
            status="archive",
            album_name="Stored Album",
            source_dir=src,
            logs={},
            output_root=str(out),
            compression_strategy="stored",
        )
        assert pkg_stored is not None and pkg_stored.exists()
        with zipfile.ZipFile(pkg_stored, "r") as zf:
            for zi in zf.infolist():
                assert zi.compress_type == zipfile.ZIP_STORED

        # Strategy 3: deflate (everything deflated)
        pkg_deflate = PackageManager.save_local_package(
            app_id=300,
            status="archive",
            album_name="Deflate Album",
            source_dir=src,
            logs={},
            output_root=str(out),
            compression_strategy="deflate",
        )
        assert pkg_deflate is not None and pkg_deflate.exists()
        with zipfile.ZipFile(pkg_deflate, "r") as zf:
            for zi in zf.infolist():
                assert zi.compress_type == zipfile.ZIP_DEFLATED


# ==============================================================================
# 2. Security Tests
# ==============================================================================

def test_ssrf_private_ip_detection():
    """Verify that is_private_ip detects loopback, RFC1918, link-local, and reserved ranges."""
    assert is_private_ip("127.0.0.1") is True
    assert is_private_ip("127.0.1.1") is True
    assert is_private_ip("10.0.0.5") is True
    assert is_private_ip("172.16.0.1") is True
    assert is_private_ip("192.168.1.1") is True
    assert is_private_ip("169.254.169.254") is True  # Cloud metadata IP
    assert is_private_ip("localhost") is True
    assert is_private_ip("::1") is True
    assert is_private_ip("0.0.0.0") is True

    # Public IPs
    assert is_private_ip("8.8.8.8") is False
    assert is_private_ip("1.1.1.1") is False


def test_safe_validate_url_ssrf():
    """Verify safe_validate_url blocks non-http schemes and private IPs."""
    # Schemes
    assert safe_validate_url("file:///etc/passwd")[0] is False
    assert safe_validate_url("ftp://example.com/test.jpg")[0] is False
    assert safe_validate_url("gopher://example.com/")[0] is False
    assert safe_validate_url("javascript:alert(1)")[0] is False

    # SSRF / private targets
    assert safe_validate_url("http://127.0.0.1:8080/secret")[0] is False
    assert safe_validate_url("http://169.254.169.254/latest/meta-data")[0] is False
    assert safe_validate_url("http://localhost:11434/api/tags")[0] is False

    # Valid public target
    valid, reason = safe_validate_url("https://example.com/cover.jpg")
    assert valid is True
    assert reason == "OK"


def test_safe_download_image_ssrf_guard():
    """Verify safe_download_image rejects SSRF requests without making network calls."""
    with patch("requests.get") as mock_get:
        assert safe_download_image("http://127.0.0.1:8080/art.jpg") is None
        assert safe_download_image("http://169.254.169.254/meta") is None
        assert safe_download_image("http://localhost:11434/") is None
        assert safe_download_image("file:///etc/hosts") is None
        assert not mock_get.called


def test_mask_secret():
    """Verify sensitive string masking for safe logging."""
    assert mask_secret("sk-1234567890abcdef") == "sk-1...cdef"
    assert mask_secret("short") == "***"
    assert mask_secret(None) == ""


def test_sanitize_log_text():
    """Verify secret redaction in log messages and webhook URLs."""
    raw = "Webhook error for https://discord.com/api/webhooks/123456789/SecretToken-Abc-987"
    sanitized = sanitize_log_text(raw)
    assert "SecretToken-Abc-987" not in sanitized
    assert "[REDACTED_WEBHOOK_TOKEN]" in sanitized

    # Custom secret redaction
    custom_msg = "Failed with api_key=super_secret_key_12345"
    sanitized_custom = sanitize_log_text(custom_msg, secrets=["super_secret_key_12345"])
    assert "super_secret_key_12345" not in sanitized_custom
    assert "[REDACTED]" in sanitized_custom


def test_is_safe_subpath():
    """Verify path traversal prevention."""
    base = Path("/tmp/base_dir")
    safe = Path("/tmp/base_dir/subdir/file.txt")
    unsafe = Path("/tmp/base_dir/../../etc/passwd")

    assert is_safe_subpath(safe, base) is True
    assert is_safe_subpath(unsafe, base) is False


def test_check_env_security_no_crash():
    """Verify check_env_security runs without throwing exceptions."""
    check_env_security(".env")
    check_env_security("non_existent_file.env")


# ==============================================================================
# 3. Config & Classification Tests
# ==============================================================================

def test_config_classified_defaults():
    """Verify default values of newly categorized configuration settings."""
    cfg = Config(steam_install_path="/tmp/steam")

    # Category 1: Steam API
    assert cfg.steam_api_timeout == 15.0
    assert cfg.steam_pics_timeout == 30.0
    assert cfg.steam_api_max_retries == 3
    assert cfg.steam_throttle_delay == 2.0

    # Category 2: LLM Reliability
    assert cfg.llm_health_check_timeout == 10.0
    assert cfg.llm_retry_delay == 5.0
    assert cfg.llm_retry_backoff == 1.5

    # Category 3: MusicBrainz & AcoustID
    assert cfg.acoustid_timeout == 10.0
    assert cfg.acoustid_rate_limit_wait_min == 1.5
    assert cfg.acoustid_rate_limit_wait_max == 2.0
    assert cfg.mbz_rate_limit_delay == 1.0
    assert cfg.mbz_search_limit == 20
    assert cfg.sst_fingerprint_sample_size == 3

    # Category 4: Packaging & Audio
    assert cfg.zip_compression_strategy == "auto"
    assert cfg.zip_deflate_level == 1
    assert cfg.ffprobe_timeout == 10.0
    assert cfg.ffmpeg_timeout == 600.0
    assert cfg.image_download_timeout == 15.0
    assert cfg.image_download_max_bytes == 25 * 1024 * 1024

    # Category 5: Security
    assert cfg.security_block_private_ips is True
    assert cfg.security_mask_secrets_in_logs is True


def test_config_env_overrides():
    """Verify that environment variable overrides work cleanly."""
    with patch.dict(os.environ, {
        "STEAM_API_TIMEOUT": "25.5",
        "ZIP_COMPRESSION_STRATEGY": "stored",
        "SST_FINGERPRINT_SAMPLE_SIZE": "5",
        "SECURITY_BLOCK_PRIVATE_IPS": "false",
    }):
        cfg = Config(steam_install_path="/tmp/steam").load_env_overrides()
        assert cfg.steam_api_timeout == 25.5
        assert cfg.zip_compression_strategy == "stored"
        assert cfg.sst_fingerprint_sample_size == 5
        assert cfg.security_block_private_ips is False


# ==============================================================================
# 4. Fast Audio Properties & Single-pass Metadata Tests
# ==============================================================================

def test_audio_tagger_get_audio_properties_fast_path():
    """Verify AudioTagger._get_audio_properties extracts properties via Mutagen without ffprobe."""
    with tempfile.TemporaryDirectory() as td:
        flac_path = Path(td) / "test.flac"
        # Create a sample FLAC using ffmpeg
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.1", "-c:a", "flac", "-sample_fmt", "s32", "-ar", "96000", str(flac_path)],
            check=True,
            capture_output=True,
        )

        tagger = AudioTagger(output_dir=Path(td))
        with patch("subprocess.run") as mock_sub:
            rate, depth = tagger._get_audio_properties(flac_path)
            assert rate == 96000
            assert depth == 24
            # Subprocess (ffprobe) should NOT be invoked
            assert not mock_sub.called


def test_audio_tagger_get_audio_properties_ffprobe_fallback():
    """Verify AudioTagger._get_audio_properties falls back to ffprobe when mutagen cannot parse."""
    with tempfile.NamedTemporaryFile(suffix=".flac") as tmp:
        tmp.write(b"corrupted flac header content")
        tmp.flush()

        tagger = AudioTagger(output_dir=Path(tmp.name).parent)
        fake_ffprobe_output = '{"streams": [{"sample_rate": "44100", "bits_per_sample": 16}]}'
        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(stdout=fake_ffprobe_output)
            rate, depth = tagger._get_audio_properties(Path(tmp.name))
            assert rate == 44100
            assert depth == 16
            assert mock_sub.called


def test_embedded_metadata_extractor_single_pass():
    """Verify EmbeddedMetadataExtractor.extract parses all fields in a single pass without reopening the file."""
    with tempfile.TemporaryDirectory() as td:
        mp3_path = Path(td) / "test.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=0.1", "-c:a", "libmp3lame", str(mp3_path)],
            check=True,
            capture_output=True,
        )

        from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, COMM, TCOM
        id3 = ID3(mp3_path)
        id3.add(TIT2(encoding=3, text=["SinglePass Title"]))
        id3.add(TPE1(encoding=3, text=["SinglePass Artist"]))
        id3.add(TALB(encoding=3, text=["SinglePass Album"]))
        id3.add(TCOM(encoding=3, text=["SinglePass Composer"]))
        id3.add(COMM(encoding=3, lang="eng", desc="", text=["SinglePass Comment"]))
        id3.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=b"fakejpeg"))
        id3.save()

        # Count mutagen.File calls: exactly 1 call should happen
        import mutagen
        original_file = mutagen.File
        file_call_count = 0

        def counting_file(*args, **kwargs):
            nonlocal file_call_count
            file_call_count += 1
            return original_file(*args, **kwargs)

        with patch("sst.ident.embedded.File", side_effect=counting_file):
            meta = EmbeddedMetadataExtractor.extract(mp3_path)

        assert file_call_count == 1
        assert meta.get("title") == "SinglePass Title"
        assert meta.get("artist") == "SinglePass Artist"
        assert meta.get("album") == "SinglePass Album"
        assert meta.get("composer") == "SinglePass Composer"
        assert meta.get("comment") == "SinglePass Comment"
        assert meta.get("has_artwork") is True
        assert meta.get("duration", 0) > 0


def test_processor_uses_pre_scanned_files():
    """Verify LocalProcessor._init_album_context uses pre_scanned_files without re-scanning."""
    with tempfile.TemporaryDirectory() as td:
        dummy_file = Path(td) / "track01.flac"
        dummy_file.write_bytes(b"fake")

        config = Config(steam_install_path="/tmp")
        db = MagicMock()
        processor = LocalProcessor(config, db)

        steam_meta = SteamMetadata(app_id=999, name="Test Album")
        diag_events = []

        with patch("sst.track_grouper.TrackManager.list_audio_files") as mock_list,              patch("sst.track_grouper.TrackManager.build_file_records", return_value={}):
            context = processor._init_album_context(
                app_id=999,
                install_dir=Path(td),
                steam_meta=steam_meta,
                _diag=lambda s, **kw: diag_events.append(s),
                pre_scanned_files=[dummy_file],
            )
            assert not mock_list.called
            assert context is not None
            assert context[0] == [dummy_file]


def test_track_manager_list_audio_files_filtering():
    """Verify TrackManager.list_audio_files rejects hidden files and non-audio files efficiently."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "song.flac").write_bytes(b"flac")
        (base / "song.mp3").write_bytes(b"mp3")
        (base / ".hidden.flac").write_bytes(b"hidden")
        (base / "._apple_double.mp3").write_bytes(b"appledouble")
        (base / "readme.txt").write_bytes(b"text")
        (base / "cover.jpg").write_bytes(b"jpg")

        subdir = base / "__macosx"
        subdir.mkdir()
        (subdir / "sub.flac").write_bytes(b"sub")

        found = TrackManager.list_audio_files(base)
        found_names = {f.name for f in found}
        assert "song.flac" in found_names
        assert "song.mp3" in found_names
        assert ".hidden.flac" not in found_names
        assert "._apple_double.mp3" not in found_names
        assert "readme.txt" not in found_names
        assert "cover.jpg" not in found_names
        assert "sub.flac" not in found_names

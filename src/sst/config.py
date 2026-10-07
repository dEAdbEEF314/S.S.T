from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any, Optional
import os
import stat
import logging

logger = logging.getLogger("sst.config")


def _unit_field(
    default: Any,
    description: str,
    unit: str,
    display_unit: str,
    **constraints: Any,
) -> Any:
    return Field(
        default=default,
        description=description,
        json_schema_extra={"unit": unit, "display_unit": display_unit},
        **constraints,
    )


DEFAULT_METADATA_SOURCE_PRIORITY = "STEAM,ACOUSTID,MBZ_RELEASE,MBZ_SEARCH,EMBED,LOCAL"


def check_env_security(env_path: str = ".env") -> None:
    """
    Checks whether the .env file has overly permissive file permissions on POSIX systems.
    Warns the user to secure API keys and tokens if world-readable.
    """
    try:
        if os.path.exists(env_path) and os.name == "posix":
            file_stat = os.stat(env_path)
            mode = file_stat.st_mode
            if mode & stat.S_IROTH:
                logger.warning(
                    f"セキュリティ警告: '{env_path}' が他ユーザーから読み取り可能です（パーミッション: {oct(mode)[-3:]}）。"
                    "APIキーやシークレット保護のため 'chmod 600 .env' を推奨します。"
                )
    except Exception as e:
        logger.debug(f"環境設定ファイル権限チェック中にエラー: {e}")


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,
        case_sensitive=False,
        env_prefix=""
    )

    steam_install_path: str
    steam_library_path: str
    sst_working_dir: str = "/tmp/sst-work"
    sst_db_path: str = "data/sst_local_state.db"
    sst_output_dir: str = "output"
    sst_log_dir: str = "logs"
    sst_lock_path: str = "data/sst.lock"
    sst_userdata_path: str = "data/userdata.json"
    sst_steam_cache_path: str = "data/sst_cache.json"
    sst_steam_tag_cache_path: str = "data/steam_tags.json"
    sst_audit_report_dir: str = "report"
    steam_login_secure: Optional[str] = None
    steam_pics_bridge_url: str = "http://localhost:8080/v1/info/"
    steam_pics_bridge_api_key: Optional[str] = None
    steam_web_api_key: Optional[str] = None
    user_language: str = "ja"
    steam_tag_cache_refresh_days: int = _unit_field(30, "Steam tag cache refresh interval", "days", "日")
    log_level: str = "INFO"

    # Steam / Store API Timeout & Retry Controls
    steam_api_timeout: float = _unit_field(15.0, "Steam Store API request timeout", "seconds", "秒")
    steam_userdata_timeout: float = _unit_field(10.0, "Steam userdata request timeout", "seconds", "秒")
    steam_pics_timeout: float = _unit_field(30.0, "Steam PICS request timeout", "seconds", "秒")
    steam_api_max_retries: int = _unit_field(3, "Maximum Steam API retries", "attempts", "回")
    steam_api_retry_delay: float = _unit_field(2.0, "Initial Steam API retry delay", "seconds", "秒", ge=0)
    steam_api_retry_backoff: float = _unit_field(2.0, "Steam API retry backoff multiplier", "ratio", "倍率", ge=1.0)
    steam_throttle_delay: float = _unit_field(2.0, "Base delay between Store API requests", "seconds", "秒")

    # LLM Settings
    llm_backend: str = "GEMINI"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: Optional[str] = None
    llm_model: str = "gemini-1.5-pro"
    llm_draft_model: Optional[str] = None
    llm_limit_rpm: int = _unit_field(15, "Cloud request rate limit", "requests/minute", "分あたり")
    llm_limit_tpm: int = _unit_field(10000000, "Cloud token rate limit", "tokens/minute", "分あたり")
    llm_limit_rpd: int = _unit_field(1500, "Cloud daily request limit", "requests/day", "日あたり")
    llm_cloud_max_tokens: int = _unit_field(8192, "Maximum cloud response tokens", "tokens", "トークン")
    llm_ollama_num_ctx: int = _unit_field(32768, "Ollama context token limit", "tokens", "トークン")
    llm_ollama_num_predict: int = _unit_field(8192, "Ollama output token limit", "tokens", "トークン")
    llm_ollama_think: bool = False
    llm_health_check_timeout: float = _unit_field(10.0, "LLM health-check timeout", "seconds", "秒")
    llm_preflight_timeout: float = _unit_field(120.0, "LLM preflight warm-up timeout", "seconds", "秒")
    llm_retry_delay: float = _unit_field(5.0, "Initial LLM retry delay", "seconds", "秒")
    llm_retry_backoff: float = _unit_field(1.5, "LLM retry backoff multiplier", "ratio", "倍率")

    # Ollama's llama-server defaults to four concurrent sequence slots in the
    # production service. Keep the client-side album pool no larger than that
    # unless the service is explicitly configured with a different -np value.
    llm_ollama_parallel_slots: int = _unit_field(4, "Ollama effective sequence slots", "slots", "slot")
    llm_vram_scheduling_enabled: bool = True
    llm_request_parallelism_enabled: bool = True
    llm_request_parallelism_max_workers: int = _unit_field(4, "Maximum parallel LLM request workers", "workers", "worker")
    llm_request_timeout: int = _unit_field(3600, "Maximum duration for one LLM request", "seconds", "秒")
    
    # Token Stingy Tier Profiles
    llm_album_tier_small_max_tracks: int = _unit_field(50, "Small-tier album track boundary", "tracks", "曲")
    llm_album_tier_medium_max_tracks: int = _unit_field(100, "Medium-tier album track boundary", "tracks", "曲")
    llm_ollama_num_ctx_small: Optional[int] = _unit_field(8192, "Small-tier context token limit", "tokens", "トークン")
    llm_ollama_num_ctx_medium: Optional[int] = _unit_field(16384, "Medium-tier context token limit", "tokens", "トークン")
    llm_ollama_num_ctx_large: Optional[int] = _unit_field(32768, "Large-tier context token limit", "tokens", "トークン")
    llm_request_parallelism_max_workers_small: Optional[int] = _unit_field(3, "Small-tier request worker limit", "workers", "worker")
    llm_request_parallelism_max_workers_medium: Optional[int] = _unit_field(2, "Medium-tier request worker limit", "workers", "worker")
    llm_request_parallelism_max_workers_large: Optional[int] = _unit_field(1, "Large-tier request worker limit", "workers", "worker")
    llm_force_coherence_large: bool = True
    llm_max_retries: int = _unit_field(3, "Maximum LLM retries", "attempts", "回")
    llm_output_budget_safety_ratio: float = _unit_field(0.25, "LLM output budget safety margin", "ratio", "比率")
    llm_adaptive_degraded_prompt_enabled: bool = True
    llm_chunk_size_virtual: int = _unit_field(20, "Virtual-track chunk size", "tracks", "トラック")
    llm_chunk_size_metadata_ollama: int = _unit_field(10, "Ollama metadata chunk size", "tracks", "トラック")
    llm_chunk_size_metadata_cloud: int = _unit_field(30, "Cloud metadata chunk size", "tracks", "トラック")
    llm_chunk_adaptive: bool = True
    llm_chunk_output_tokens_per_track: int = _unit_field(180, "Output token budget per track", "tokens/track", "トークン")
    llm_chunk_output_safety_ratio: float = _unit_field(0.75, "Chunk output budget safety ratio", "ratio", "比率")

    max_parallel_albums: int = _unit_field(2, "Maximum concurrent album processing", "albums", "並列アルバム")
    max_encoding_tasks: int = _unit_field(4, "Maximum concurrent encoding tasks", "tasks", "タスク")
    fingerprint_all: bool = Field(
        default=True,
        validation_alias=AliasChoices("SST_FINGERPRINT_ALL", "FINGERPRINT_ALL"),
    )
    auto_audit_enabled: bool = True

    # LLM結果キャッシュ
    sst_llm_cache_enabled: bool = True
    sst_llm_cache_ttl_seconds: int = _unit_field(86400, "LLM result cache time-to-live", "seconds", "秒")
    sst_llm_cache_path: str = "data/llm_cache.json"
    sst_deferred_copy_delay_seconds: int = _unit_field(600, "Deferred copy retry delay", "seconds", "秒", ge=0)
    
    # Audio, Packaging & Performance
    zip_compression_strategy: str = "auto"  # auto | stored | deflate
    zip_deflate_level: int = _unit_field(1, "ZIP DEFLATE compression level", "level", "圧縮レベル")
    ffprobe_timeout: float = _unit_field(10.0, "ffprobe subprocess timeout", "seconds", "秒")
    ffmpeg_timeout: float = _unit_field(600.0, "ffmpeg conversion timeout", "seconds", "秒")
    image_download_timeout: float = _unit_field(15.0, "Artwork download timeout", "seconds", "秒")
    image_download_max_bytes: int = _unit_field(25 * 1024 * 1024, "Maximum artwork download size", "bytes", "bytes")
    sst_fingerprint_sample_size: int = _unit_field(3, "Representative fingerprint scan size", "tracks", "トラック")

    # Security
    security_block_private_ips: bool = True
    security_mask_secrets_in_logs: bool = True

    # MusicBrainz Scoring Settings
    score_mbz_direct_steam_link: int = 500
    score_mbz_parent_steam_link: int = 300
    score_mbz_direct_steamdb_link: int = 500
    score_mbz_direct_steam_link: int = _unit_field(500, "Score for a direct Steam link", "score points", "点")
    score_mbz_parent_steam_link: int = _unit_field(300, "Score for a parent Steam link", "score points", "点")
    score_mbz_direct_steamdb_link: int = _unit_field(500, "Score for a direct SteamDB link", "score points", "点")
    score_mbz_parent_steamdb_link: int = _unit_field(300, "Score for a parent SteamDB link", "score points", "点")
    score_mbz_bandcamp_link: int = _unit_field(100, "Score for a Bandcamp link", "score points", "点")
    score_mbz_title_similarity_max: int = _unit_field(100, "Maximum title similarity score", "score points", "点")
    score_mbz_track_count_match: int = _unit_field(50, "Score for matching track counts", "score points", "点")
    score_mbz_track_count_penalty_per_track: int = _unit_field(20, "Track-count mismatch penalty per track", "score points/track", "点")
    score_mbz_track_count_penalty_max: int = _unit_field(300, "Maximum track-count mismatch penalty", "score points", "点")
    score_mbz_digital_format: int = _unit_field(30, "Score for digital release format", "score points", "点")
    score_mbz_date_match: int = _unit_field(20, "Score for matching release date", "score points", "点")
    score_mbz_date_penalty_per_year: int = _unit_field(20, "Release-date mismatch penalty per year", "score points/year", "点")
    score_mbz_date_penalty_max: int = _unit_field(100, "Maximum release-date mismatch penalty", "score points", "点")
    score_mbz_fingerprint_match: int = _unit_field(200, "Score for fingerprint match", "score points", "点")
    score_mbz_direct_recording_match: int = _unit_field(1000, "Score for direct recording match", "score points", "点")
    score_mbz_acoustid_release_match: int = _unit_field(1000, "Score for AcoustID release match", "score points", "点")
    score_mbz_publisher_label_match: int = _unit_field(100, "Score for publisher or label match", "score points", "点")
    min_mbz_search_score_threshold: int = _unit_field(250, "Minimum MusicBrainz search score", "score points", "点")
    mbz_app_name: str = "SST-Scout"
    mbz_app_version: str = "1.0.0"
    mbz_contact: str = "contact@example.lan"
    mbz_rate_limit_delay: float = _unit_field(1.0, "Delay between MusicBrainz requests", "seconds", "秒")
    mbz_search_limit: int = _unit_field(20, "Maximum MusicBrainz search candidates", "candidates", "候補")
    acoustid_api_key: Optional[str] = None
    acoustid_timeout: float = _unit_field(10.0, "AcoustID API request timeout", "seconds", "秒")
    acoustid_rate_limit_wait_min: float = _unit_field(1.5, "Minimum AcoustID rate-limit wait", "seconds", "秒")
    acoustid_rate_limit_wait_max: float = _unit_field(2.0, "Maximum AcoustID rate-limit wait", "seconds", "秒")

    # Compatibility settings retained during the migration away from the old spec.
    metadata_source_priority: Optional[str] = None
    metadata_field_fallback_priority: Optional[str] = None

    # Notifications
    notify_enabled: bool = False
    notify_cooldown: int = _unit_field(60, "Notification cooldown interval", "seconds", "秒")
    notify_request_timeout: float = _unit_field(10.0, "Webhook HTTP request timeout", "seconds", "秒", gt=0)
    notify_max_retries: int = _unit_field(3, "Maximum webhook attempts including initial request", "attempts", "回", ge=1)
    notify_retry_delay: float = _unit_field(2.0, "Initial webhook retry delay", "seconds", "秒", ge=0)
    notify_retry_backoff: float = _unit_field(1.5, "Webhook retry backoff multiplier", "ratio", "倍率", ge=1.0)
    discord_webhook_critical: Optional[str] = None
    discord_webhook_warning: Optional[str] = None
    discord_webhook_info: Optional[str] = None
    discord_webhook_completion: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        legacy_value = (self.metadata_source_priority or "").strip()
        if not legacy_value:
            return

        preferred_value = (self.metadata_field_fallback_priority or "").strip()
        if preferred_value:
            logger.warning(
                "旧設定 METADATA_SOURCE_PRIORITY は非推奨で、"
                "METADATA_FIELD_FALLBACK_PRIORITY が設定されているため無視されます。"
                "旧設定を直ちに削除してください。"
            )
        else:
            logger.warning(
                "旧設定 METADATA_SOURCE_PRIORITY は非推奨です。"
                "値を METADATA_FIELD_FALLBACK_PRIORITY へ直ちに移し、旧設定を削除してください。"
            )

    def load_env_overrides(self):
        check_env_security()
        return self

    @property
    def resolved_metadata_source_priority(self) -> str:
        legacy_value = (self.metadata_source_priority or "").strip()
        preferred_value = (self.metadata_field_fallback_priority or "").strip()
        return preferred_value or legacy_value or DEFAULT_METADATA_SOURCE_PRIORITY

    def build_mbz_scoring_config(self) -> dict[str, int]:
        return {
            "direct_steam_link": self.score_mbz_direct_steam_link,
            "parent_steam_link": self.score_mbz_parent_steam_link,
            "direct_steamdb_link": self.score_mbz_direct_steamdb_link,
            "parent_steamdb_link": self.score_mbz_parent_steamdb_link,
            "bandcamp_link": self.score_mbz_bandcamp_link,
            "title_similarity_max": self.score_mbz_title_similarity_max,
            "track_count_match": self.score_mbz_track_count_match,
            "track_count_penalty_per_track": self.score_mbz_track_count_penalty_per_track,
            "track_count_penalty_max": self.score_mbz_track_count_penalty_max,
            "digital_format": self.score_mbz_digital_format,
            "date_match": self.score_mbz_date_match,
            "date_penalty_per_year": self.score_mbz_date_penalty_per_year,
            "date_penalty_max": self.score_mbz_date_penalty_max,
            "fingerprint_match": self.score_mbz_fingerprint_match,
            "direct_recording_match": self.score_mbz_direct_recording_match,
            "acoustid_release_match": self.score_mbz_acoustid_release_match,
            "publisher_label_match": self.score_mbz_publisher_label_match,
        }

    def build_llm_organizer_kwargs(self) -> dict[str, Any]:
        return {
            "api_key": self.llm_api_key,
            "base_url": self.llm_base_url,
            "model": self.llm_model,
            "rpm": self.llm_limit_rpm,
            "tpm": self.llm_limit_tpm,
            "rpd": self.llm_limit_rpd,
            "user_language": self.user_language,
            "llm_backend": self.llm_backend,
            "draft_model": self.llm_draft_model,
            "llm_cloud_max_tokens": self.llm_cloud_max_tokens,
            "ollama_num_ctx": self.llm_ollama_num_ctx,
            "ollama_num_predict": self.llm_ollama_num_predict,
            "ollama_think": self.llm_ollama_think,
            "llm_vram_scheduling_enabled": self.llm_vram_scheduling_enabled,
            "llm_request_parallelism_enabled": self.llm_request_parallelism_enabled,
            "llm_request_parallelism_max_workers": self.llm_request_parallelism_max_workers,
            "request_timeout": self.llm_request_timeout,
            "chunk_size_virtual": self.llm_chunk_size_virtual,
            "chunk_size_metadata_ollama": self.llm_chunk_size_metadata_ollama,
            "chunk_size_metadata_cloud": self.llm_chunk_size_metadata_cloud,
            "chunk_adaptive": self.llm_chunk_adaptive,
            "chunk_output_tokens_per_track": self.llm_chunk_output_tokens_per_track,
            "chunk_output_safety_ratio": self.llm_chunk_output_safety_ratio,
            "max_retries": self.llm_max_retries,
            "output_budget_safety_ratio": self.llm_output_budget_safety_ratio,
            "adaptive_degraded_prompt_enabled": self.llm_adaptive_degraded_prompt_enabled,
            "metadata_source_priority": self.resolved_metadata_source_priority,
            "llm_cache_enabled": self.sst_llm_cache_enabled,
            "llm_cache_ttl_seconds": self.sst_llm_cache_ttl_seconds,
            "llm_cache_path": self.sst_llm_cache_path,
            "retry_delay": self.llm_retry_delay,
            "retry_backoff": self.llm_retry_backoff,
            "health_check_timeout": self.llm_health_check_timeout,
        }

    def resolve_llm_num_ctx_cap(self, tier_name: str) -> int:
        tier_value = getattr(self, f"llm_ollama_num_ctx_{tier_name.lower()}", None)
        if tier_value is not None:
            return tier_value
        return self.llm_ollama_num_ctx

    def resolve_llm_parallel_workers(self, tier_name: str) -> int:
        tier_value = getattr(self, f"llm_request_parallelism_max_workers_{tier_name.lower()}", None)
        if tier_value is not None:
            return tier_value
        return self.llm_request_parallelism_max_workers

    @property
    def steam_language_full(self) -> str:
        return {"ja": "japanese", "en": "english"}.get(self.user_language, "english")

    @property
    def user_language_639_2(self) -> str:
        return {"ja": "jpn", "en": "eng"}.get(self.user_language, "eng")

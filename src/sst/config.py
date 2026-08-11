from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any, Optional
import os

DEFAULT_TITLE_CLEANING_TRUSTED_SOURCES = "MBZ,FINGERPRINT"
DEFAULT_METADATA_SOURCE_PRIORITY = "STEAM,ACOUSTID,MBZ_RELEASE,MBZ_SEARCH,EMBED,LOCAL"


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True, case_sensitive=False, env_prefix="")
    steam_install_path: str
    steam_library_path: Optional[str] = None
    sst_working_dir: str = "/tmp/sst-work"
    sst_db_path: str = "data/sst_local_state.db"
    sst_output_dir: str = "output"
    steam_login_secure: Optional[str] = None
    steam_pics_bridge_url: str = "http://localhost:8080/v1/info/"
    steam_pics_bridge_api_key: Optional[str] = None
    steam_web_api_key: Optional[str] = None
    user_language: str = "ja"
    steam_tag_cache_refresh_days: int = 30
    log_level: str = "INFO"
    llm_backend: str = "GEMINI"
    llm_base_url: str = "http://localhost:11434"
    llm_api_key: Optional[str] = None
    llm_model: str = "gemini-1.5-pro"
    llm_draft_model: Optional[str] = None
    llm_limit_rpm: int = 15
    llm_limit_tpm: int = 10000000
    llm_limit_rpd: int = 1500
    llm_cloud_max_tokens: int = 8192
    llm_num_ctx: int = 32768
    llm_ollama_num_ctx: int = 32768
    llm_ollama_num_predict: int = 4096
    # Ollama's llama-server defaults to four concurrent sequence slots in the
    # production service. Keep the client-side album pool no larger than that
    # unless the service is explicitly configured with a different -np value.
    llm_ollama_parallel_slots: int = 4
    llm_vram_scheduling_enabled: bool = True
    llm_request_parallelism_enabled: bool = True
    llm_request_parallelism_max_workers: int = 4
    llm_request_timeout: int = 3600
    
    # Token Stingy Tier Profiles
    llm_album_tier_small_max_tracks: int = 50
    llm_album_tier_medium_max_tracks: int = 100
    llm_ollama_num_ctx_small: Optional[int] = 8192
    llm_ollama_num_ctx_medium: Optional[int] = 16384
    llm_ollama_num_ctx_large: Optional[int] = 32768
    llm_request_parallelism_max_workers_small: Optional[int] = 3
    llm_request_parallelism_max_workers_medium: Optional[int] = 2
    llm_request_parallelism_max_workers_large: Optional[int] = 1
    llm_force_coherence_large: bool = True
    llm_coherence_threshold: int = 75
    llm_chunk_size_virtual: int = 20
    llm_chunk_size_metadata_ollama: int = 10
    llm_chunk_size_metadata_cloud: int = 30
    llm_chunk_adaptive: bool = True
    llm_chunk_output_tokens_per_track: int = 180
    llm_chunk_output_safety_ratio: float = 0.75

    max_parallel_albums: int = 2
    max_encoding_tasks: int = 4
    fingerprint_all: bool = True
    auto_audit_enabled: bool = True
    
    # MusicBrainz Scoring Settings
    score_mbz_direct_steam_link: int = 500
    score_mbz_parent_steam_link: int = 300
    score_mbz_direct_steamdb_link: int = 500
    score_mbz_parent_steamdb_link: int = 300
    score_mbz_bandcamp_link: int = 100
    score_mbz_title_similarity_max: int = 100
    score_mbz_track_count_match: int = 50
    score_mbz_track_count_penalty_per_track: int = 300
    score_mbz_track_count_penalty_max: int = 2000
    score_mbz_digital_format: int = 30
    score_mbz_date_match: int = 20
    score_mbz_date_penalty_per_year: int = 20
    score_mbz_date_penalty_max: int = 100
    score_mbz_fingerprint_match: int = 200
    score_mbz_direct_recording_match: int = 1000
    score_mbz_acoustid_release_match: int = 1000
    score_mbz_publisher_label_match: int = 100
    min_mbz_search_score_threshold: int = 250

    # Compatibility settings retained during the migration away from the old spec.
    title_cleaning_trusted_sources: str = DEFAULT_TITLE_CLEANING_TRUSTED_SOURCES
    metadata_source_priority: Optional[str] = None
    metadata_field_fallback_priority: str = DEFAULT_METADATA_SOURCE_PRIORITY

    mbz_app_name: str = "SST-Scout"
    mbz_app_version: str = "1.0.0"
    mbz_contact: str = "contact@example.lan"
    acoustid_api_key: Optional[str] = None
    notify_enabled: bool = False
    notify_cooldown: int = 60
    discord_webhook_critical: Optional[str] = None
    discord_webhook_warning: Optional[str] = None
    discord_webhook_info: Optional[str] = None
    discord_webhook_completion: Optional[str] = None

    def load_env_overrides(self):
        def try_set(key, env_var):
            val = os.getenv(env_var)
            if val is not None:
                if isinstance(getattr(self, key), bool):
                    setattr(self, key, val.lower() == "true")
                elif isinstance(getattr(self, key), int):
                    setattr(self, key, int(val))
                else:
                    setattr(self, key, val)

        try_set("fingerprint_all", "SST_FINGERPRINT_ALL")
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
            "metadata_source_priority": self.resolved_metadata_source_priority,
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

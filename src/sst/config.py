from dataclasses import dataclass
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any, Optional

DEFAULT_TITLE_CLEANING_TRUSTED_SOURCES = "MBZ,PICS_API"
DEFAULT_METADATA_SOURCE_PRIORITY = "MBZ,PICS_API,STEAM_STORE,STEAM_TAGS,EMBEDDED"
DEFAULT_PRIORITY_TIT2 = "MBZ,PICS_API,FILE,EMBED,VDF"
DEFAULT_PRIORITY_TPE1 = "MBZ,PICS_API,EMBED"
DEFAULT_PRIORITY_TRCK = "PICS_API,MBZ,FILE,EMBED"
DEFAULT_PRIORITY_TPOS = "PICS_API,EMBED,MBZ"
DEFAULT_PRIORITY_TYER = "MBZ,EMBED,WEB_API"
DEFAULT_PRIORITY_TPUB = "MBZ,PICS_API"
DEFAULT_PRIORITY_APIC = "MBZ,PICS_API,WEB_API,EMBED"


@dataclass(frozen=True)
class PriorityConfig:
    tit2: str
    tpe1: str
    trck: str
    tpos: str
    tyer: str
    tpub: str
    trusted_title_sources: str

    def to_builder_dict(self) -> dict[str, str]:
        return {
            "TIT2": self.tit2,
            "TPE1": self.tpe1,
            "TRCK": self.trck,
            "TPOS": self.tpos,
            "TYER": self.tyer,
            "TPUB": self.tpub,
            "TRUSTED_TITLE_SOURCES": self.trusted_title_sources,
        }

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
    log_level: str = "INFO"
    llm_backend: str = "GEMINI"
    llm_base_url: str = "https://generativelanguage.googleapis.com"
    llm_api_key: Optional[str] = None
    llm_model: str = "gemini-1.5-pro"
    llm_draft_model: Optional[str] = None
    llm_limit_rpm: int = 15
    llm_limit_tpm: int = 10000000
    llm_limit_rpd: int = 1500
    llm_cloud_max_tokens: int = 8192
    llm_ollama_num_ctx: int = 32768
    llm_ollama_num_predict: int = 4096
    llm_coherence_threshold: int = 75
    llm_chunk_size_virtual: int = 20
    llm_chunk_size_metadata_ollama: int = 10
    llm_chunk_size_metadata_cloud: int = 30
    llm_chunk_adaptive: bool = True
    llm_chunk_output_tokens_per_track: int = 180
    llm_chunk_output_safety_ratio: float = 0.75

    max_parallel_albums: int = 2
    max_encoding_tasks: int = 4
    fingerprint_all: bool = False
    

    
    # MusicBrainz Scoring Settings
    score_mbz_direct_steam_link: int = 500
    score_mbz_parent_steam_link: int = 300
    score_mbz_direct_steamdb_link: int = 500
    score_mbz_parent_steamdb_link: int = 300
    score_mbz_bandcamp_link: int = 100
    score_mbz_title_similarity_max: int = 100
    score_mbz_track_count_match: int = 50
    score_mbz_track_count_penalty_per_track: int = 20
    score_mbz_track_count_penalty_max: int = 300
    score_mbz_digital_format: int = 30
    score_mbz_date_match: int = 20
    score_mbz_date_penalty_per_year: int = 20
    score_mbz_date_penalty_max: int = 100
    score_mbz_fingerprint_match: int = 200
    score_mbz_direct_recording_match: int = 1000
    score_mbz_acoustid_release_match: int = 1000
    score_mbz_publisher_label_match: int = 100
    min_mbz_search_score_threshold: int = 250

    # Metadata Cleaning Settings
    title_cleaning_trusted_sources: str = DEFAULT_TITLE_CLEANING_TRUSTED_SOURCES

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
    metadata_source_priority: str = DEFAULT_METADATA_SOURCE_PRIORITY
    
    # Tag-specific metadata priorities
    priority_tit2: str = DEFAULT_PRIORITY_TIT2
    priority_tpe1: str = DEFAULT_PRIORITY_TPE1
    priority_trck: str = DEFAULT_PRIORITY_TRCK
    priority_tpos: str = DEFAULT_PRIORITY_TPOS
    priority_tyer: str = DEFAULT_PRIORITY_TYER
    priority_tpub: str = DEFAULT_PRIORITY_TPUB
    priority_apic: str = DEFAULT_PRIORITY_APIC

    def build_priority_config(self) -> PriorityConfig:
        return PriorityConfig(
            tit2=self.priority_tit2,
            tpe1=self.priority_tpe1,
            trck=self.priority_trck,
            tpos=self.priority_tpos,
            tyer=self.priority_tyer,
            tpub=self.priority_tpub,
            trusted_title_sources=self.title_cleaning_trusted_sources,
        )

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
            "coherence_threshold": self.llm_coherence_threshold,
            "chunk_size_virtual": self.llm_chunk_size_virtual,
            "chunk_size_metadata_ollama": self.llm_chunk_size_metadata_ollama,
            "chunk_size_metadata_cloud": self.llm_chunk_size_metadata_cloud,
            "chunk_adaptive": self.llm_chunk_adaptive,
            "chunk_output_tokens_per_track": self.llm_chunk_output_tokens_per_track,
            "chunk_output_safety_ratio": self.llm_chunk_output_safety_ratio,
            "metadata_source_priority": self.metadata_source_priority,
            "priority_tit2": self.priority_tit2,
            "priority_tpe1": self.priority_tpe1,
            "priority_trck": self.priority_trck,
            "priority_tpos": self.priority_tpos,
            "priority_tyer": self.priority_tyer,
            "priority_tpub": self.priority_tpub,
            "priority_apic": self.priority_apic,
        }

    @property
    def steam_language_full(self) -> str:
        return {"ja": "japanese", "en": "english"}.get(self.user_language, "english")

    @property
    def user_language_639_2(self) -> str:
        return {"ja": "jpn", "en": "eng"}.get(self.user_language, "eng")


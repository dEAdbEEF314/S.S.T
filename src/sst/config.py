from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True, case_sensitive=False, env_prefix="")
    steam_install_path: str
    steam_library_path: Optional[str] = None
    sst_working_dir: str = "/tmp/sst-work"
    sst_db_path: str = "data/sst_local_state.db"
    sst_output_dir: str = "output"
    steam_login_secure: Optional[str] = None
    steam_pics_bridge_url: str = "http://localhost:8080/v1/info/"
    steam_web_api_key: Optional[str] = None
    user_language: str = "ja"
    log_level: str = "INFO"
    llm_backend: str = "GEMINI"
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    llm_api_key: Optional[str] = None
    llm_model: str = "gemini-1.5-pro"
    llm_limit_rpm: int = 15
    llm_limit_tpm: int = 10000000
    llm_limit_rpd: int = 1500
    llm_draft_model: Optional[str] = None
    max_parallel_albums: int = 2
    max_parallel_small: int = 4
    max_parallel_medium: int = 2
    max_parallel_large: int = 1
    max_encoding_tasks: int = 4
    fingerprint_all: bool = False
    
    # Adaptive LLM Router Settings
    llm_model_small: str = "qwen2.5:7b"
    llm_model_medium: str = "qwen3.5:9b"
    llm_model_large: str = "phi4:14b"  # 16GB VRAMでの大型用想定
    
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
    title_cleaning_trusted_sources: str = "MBZ,PICS_API"

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
    metadata_source_priority: str = "MBZ,PICS_API,STEAM_STORE,STEAM_TAGS,EMBEDDED"
    
    # Tag-specific metadata priorities
    priority_tit2: str = "MBZ,PICS_API,FILE,EMBED,VDF"
    priority_tpe1: str = "MBZ,PICS_API,EMBED"
    priority_trck: str = "PICS_API,MBZ,FILE,EMBED"
    priority_tpos: str = "PICS_API,EMBED,MBZ"
    priority_tyer: str = "MBZ,EMBED,WEB_API"
    priority_tpub: str = "MBZ,PICS_API"
    priority_apic: str = "MBZ,PICS_API,WEB_API,EMBED"

    @property
    def steam_language_full(self) -> str:
        return {"ja": "japanese", "en": "english"}.get(self.user_language, "english")

    @property
    def user_language_639_2(self) -> str:
        return {"ja": "jpn", "en": "eng"}.get(self.user_language, "eng")


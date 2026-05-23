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
    steam_language_full: str = "japanese"
    user_language_639_2: str = "jpn"
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
    max_encoding_tasks: int = 4
    
    # Adaptive LLM Router Settings
    llm_model_small: str = "qwen2.5:7b-sst"
    llm_model_medium: str = "qwen3.5-9b-sst"
    llm_model_large: str = "phi-4:14b"  # 16GB VRAMでの大型用想定
    
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

    mbz_app_name: str = "SST-Scout"
    mbz_app_version: str = "1.0.0"
    mbz_contact: str = "contact@example.lan"
    acoustid_api_key: Optional[str] = None
    discogs_api_token: Optional[str] = None
    notify_enabled: bool = False
    notify_cooldown: int = 60
    discord_webhook_critical: Optional[str] = None
    discord_webhook_warning: Optional[str] = None
    discord_webhook_info: Optional[str] = None
    discord_webhook_completion: Optional[str] = None
    metadata_source_priority: str = "VGMDB,MBZ,DISCOGS,STEAM_PICS,STEAM_STORE,STEAM_TAGS,EMBEDDED"
    
    # Tag-specific metadata priorities
    priority_tit2: str = "FILE,EMBED,VDF,VGMDB,MBZ,DISCOGS,PICS_API"
    priority_tpe1: str = "EMBED,VGMDB,MBZ,DISCOGS,PICS_API"
    priority_trck: str = "VGMDB,PICS_API,MBZ,DISCOGS,FILE,EMBED"
    priority_tpos: str = "VGMDB,PICS_API,EMBED,MBZ,DISCOGS"
    priority_tyer: str = "EMBED,VGMDB,MBZ,DISCOGS,WEB_API"
    priority_tpub: str = "VGMDB,MBZ,DISCOGS,PICS_API"
    priority_apic: str = "EMBED,MBZ,DISCOGS,PICS_API,WEB_API"


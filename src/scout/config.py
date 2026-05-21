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
    
    mbz_app_name: str = "SST-Scout"
    mbz_app_version: str = "1.0.0"
    mbz_contact: str = "contact@example.lan"
    notify_enabled: bool = False
    notify_cooldown: int = 60
    discord_webhook_critical: Optional[str] = None
    discord_webhook_warning: Optional[str] = None
    discord_webhook_info: Optional[str] = None
    discord_webhook_completion: Optional[str] = None
    metadata_source_priority: str = "STEAM_PICS,STEAM_STORE,MBZ,STEAM_TAGS,EMBEDDED"

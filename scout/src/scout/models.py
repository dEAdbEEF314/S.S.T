from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime

class ScoutResult(BaseModel):
    app_id: int
    name: str
    install_dir: str
    developer: Optional[str] = None
    publisher: Optional[str] = None
    tags: List[str] = []
    genre: Optional[str] = None
    url: Optional[str] = None
    storage_location: str = "local"
    track_count: int
    files_by_ext: Dict[str, int]
    acf_key: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    dry_run: bool = False

class WorkerInput(BaseModel):
    app_id: int
    files: List[str]
    steam: ScoutResult

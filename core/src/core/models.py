from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

class ScoutResult(BaseModel):
    app_id: int
    name: str
    install_dir: str
    developer: Optional[str] = None
    publisher: Optional[str] = None
    url: Optional[str] = None
    track_count: int
    files_by_ext: Dict[str, int]
    uploaded_at: datetime

class JobState(BaseModel):
    app_id: int
    status: str = "pending" # pending, processing, completed, review, failed
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    worker_output: Optional[Dict] = None
    error: Optional[str] = None

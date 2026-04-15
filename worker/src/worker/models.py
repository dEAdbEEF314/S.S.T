from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class SteamMetadata(BaseModel):
    app_id: int
    name: str
    developer: Optional[str] = None
    publisher: Optional[str] = None
    tags: List[str] = []
    genre: Optional[str] = None
    url: Optional[str] = None

class WorkerInput(BaseModel):
    app_id: int
    files: List[str]  # S3 keys: ingest/{app_id}/...
    steam: Optional[SteamMetadata] = None

class ResolvedMetadata(BaseModel):
    resolved: bool
    source: Optional[str] = None
    album: Optional[str] = None
    artist: Optional[str] = None
    album_artist: Optional[str] = None
    genre: Optional[str] = None
    grouping: Optional[str] = None
    comment: Optional[str] = None
    year: Optional[str] = None
    mbid: Optional[str] = None
    vgmdb_url: Optional[str] = None
    track_results: List[Dict[str, Any]] = [] # Per-track metadata
    confidence: float = 0.0

class WorkerOutput(BaseModel):
    app_id: int
    status: str  # success, review, failed
    file_refs: List[str] = []
    resolved: Optional[ResolvedMetadata] = None
    error: Optional[str] = None

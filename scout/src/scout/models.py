from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime

class SteamMetadata(BaseModel):
    app_id: int
    name: str
    developer: Optional[str] = None
    publisher: Optional[str] = None
    tags: List[str] = []
    genre: Optional[str] = None
    url: Optional[str] = None
    release_date: Optional[str] = None
    parent_app_id: Optional[int] = None
    parent_tags: List[str] = []
    parent_genre: Optional[str] = None

class TrackMetadata(BaseModel):
    title: str
    artist: Optional[str] = None
    album: Optional[str] = None
    track_number: Optional[int] = None
    disc_number: Optional[int] = None
    duration_sec: Optional[float] = None
    file_format: str
    source: str # e.g., "embedded_mp3", "musicbrainz"

class AlbumMetadataSet(BaseModel):
    source_name: str # e.g., "FLAC Tags", "Steam API", "MusicBrainz"
    tracks: List[TrackMetadata] = []
    album_artist: Optional[str] = None
    year: Optional[int] = None

class ProcessingContext(BaseModel):
    app_id: int
    steam: SteamMetadata
    sources: List[AlbumMetadataSet] = []
    final_metadata: Optional[Dict[str, Any]] = None # Result from LLM

class LocalProcessResult(BaseModel):
    app_id: int
    status: str # archive, review, skip
    message: str
    processed_at: datetime = Field(default_factory=datetime.utcnow)

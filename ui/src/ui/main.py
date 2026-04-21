from fastapi import FastAPI, Request, HTTPException, Body, APIRouter
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional, Dict, Any
from .s3_service import S3UIService
import os
import httpx
from pathlib import Path
from datetime import datetime, timedelta, timezone

class UIConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_name: str
    s3_filer_url: str
    prefect_api_url: Optional[str] = None
    prefect_flow_name: str = "SST-Production-Pipeline"
    tz: str = "Asia/Tokyo"

app = FastAPI(title="S.S.T Web Interface")
api_router = APIRouter(prefix="/api")

def get_s3():
    config = UIConfig()
    return S3UIService(
        filer_url=config.s3_filer_url,
        bucket_name=config.s3_bucket_name,
        access_key=config.s3_access_key,
        secret_key=config.s3_secret_key
    )

# --- API Router Endpoints ---

@api_router.get("/stats")
async def get_stats():
    s3 = get_s3()
    try:
        archive_count = len(s3.list_albums("archive"))
        review_count = len(s3.list_albums("review"))
        ingest_count = len(s3.list_albums("ingest"))
        return {
            "scanned": archive_count + review_count + ingest_count,
            "processing": 0,
            "archive": archive_count,
            "review": review_count
        }
    except Exception:
        return {"scanned": 0, "processing": 0, "archive": 0, "review": 0}

@api_router.get("/pipeline")
async def get_pipeline():
    return []

@api_router.get("/albums")
async def get_albums(status: str):
    s3 = get_s3()
    if status not in ["archive", "review", "ingest"]:
        raise HTTPException(status_code=400)
    return s3.list_albums(status)

@api_router.post("/albums/reprocess")
async def reprocess_album(status: str = Body(...), app_id: str = Body(...)):
    s3 = get_s3()
    try:
        try:
            s3.delete_album("ingest", app_id)
        except: pass
        s3.move_album(app_id, status, "ingest")
        return {"message": f"Album {app_id} moved back to ingest"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/albums")
async def delete_albums(status: str, app_ids: List[str]):
    s3 = get_s3()
    try:
        for app_id in app_ids:
            s3.delete_album(status, app_id)
        return {"message": f"Deleted {len(app_ids)} albums"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/llm-logs")
@api_router.get("/llmlogs") # Handle both variants
async def get_llm_logs():
    s3 = get_s3()
    logs = []
    try:
        albums = s3.list_albums("archive")
        for album in albums:
            app_id = album["app_id"]
            log_data = s3.download_json(f"archive/{app_id}/llm_log.json")
            if log_data:
                logs.append({
                    "id": f"llm_{app_id}",
                    "app_id": app_id,
                    "album_name": album["name"],
                    "timestamp": album.get("processed_at", ""),
                    "content": log_data
                })
        return logs
    except Exception:
        return []

# Include Router
app.include_router(api_router)

# --- Legacy & Downloads ---

@app.get("/download/{status}/{app_id}")
async def download_album(status: str, app_id: str):
    s3 = get_s3()
    zip_stream = s3.create_zip_stream(status, app_id)
    details = s3._get_album_details(status, app_id)
    name = details["name"] if details else f"Album_{app_id}"
    safe_name = "".join([c if c.isalnum() or c in ".-_" else "_" for c in name])
    filename = f"{safe_name}_{status.capitalize()}.zip"
    return StreamingResponse(
        zip_stream,
        media_type="application/x-zip-compressed",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# --- Static Files & SPA Support (LAST) ---

frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    # Ensure we don't accidentally match API paths here
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404)
    
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>SST UI: Frontend dist not found.</h1>")

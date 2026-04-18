from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic_settings import BaseSettings, SettingsConfigDict
from .s3_service import S3UIService
import os
from pathlib import Path

class UIConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_name: str
    prefect_api_url: str = "http://sst-prefect-server:4200/api"
    prefect_flow_name: str = "SST-Production-Pipeline"

app = FastAPI(title="S.S.T Web Interface")

# Mount static files (React build artifacts)
# Note: In Docker, this will be /app/frontend/dist
frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

templates = Jinja2Templates(directory="src/ui/templates")

def get_s3():
    config = UIConfig()
    return S3UIService(
        endpoint_url=config.s3_endpoint_url,
        access_key=config.s3_access_key,
        secret_key=config.s3_secret_key,
        bucket_name=config.s3_bucket_name
    )

# --- Legacy Endpoints (Optional, kept for safety) ---
@app.get("/legacy", response_class=HTMLResponse)
async def legacy_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/download/{status}/{app_id}")
async def download_album(status: str, app_id: str):
    if status not in ["archive", "review"]:
        raise HTTPException(status_code=400)
    
    s3 = get_s3()
    details = s3._get_album_details(status, app_id)
    if not details or not details["is_ready"]:
        raise HTTPException(status_code=404, detail="Album not ready or not found")

    zip_stream = s3.create_zip_stream(status, app_id)
    filename = f"{details['name'].replace(' ', '_')}_{status.capitalize()}.zip"
    
    return StreamingResponse(
        zip_stream,
        media_type="application/x-zip-compressed",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# --- New API Endpoints for React Frontend ---

@app.get("/api/stats")
async def get_stats():
    """Returns aggregated system statistics."""
    s3 = get_s3()
    config = UIConfig()
    import requests
    
    # 1. Scanned (ingest/)
    scanned = 0
    try:
        resp = s3.s3_client.list_objects_v2(Bucket=s3.bucket_name, Prefix="ingest/", Delimiter="/")
        scanned = len(resp.get("CommonPrefixes", []))
    except: pass
    
    # 2. Archive & Review
    archive = 0
    review = 0
    try:
        resp_a = s3.s3_client.list_objects_v2(Bucket=s3.bucket_name, Prefix="archive/", Delimiter="/")
        archive = len(resp_a.get("CommonPrefixes", []))
        resp_r = s3.s3_client.list_objects_v2(Bucket=s3.bucket_name, Prefix="review/", Delimiter="/")
        review = len(resp_r.get("CommonPrefixes", []))
    except: pass
    
    # 3. Processing (from Prefect)
    processing = 0
    try:
        resp = requests.post(
            f"{config.prefect_api_url}/flow_runs/filter",
            json={"flow_runs": {"state": {"type": {"any_": ["RUNNING"]}}}},
            timeout=5
        )
        if resp.status_code == 200:
            processing = len(resp.json())
    except: pass

    return {
        "scanned": scanned,
        "processing": processing,
        "archive": archive,
        "review": review
    }

@app.get("/api/pipeline")
async def get_pipeline():
    """Proxy for Prefect flow runs."""
    config = UIConfig()
    import requests
    try:
        resp = requests.post(
            f"{config.prefect_api_url}/flow_runs/filter",
            json={
                "limit": 20,
                "sort": "START_TIME_DESC"
            },
            timeout=5
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/llm-logs")
async def list_llm_logs():
    """List LLM interaction log files from S3."""
    s3 = get_s3()
    try:
        resp = s3.s3_client.list_objects_v2(Bucket=s3.bucket_name, Prefix="logs/llm/")
        if "Contents" not in resp:
            return []
        
        logs = []
        for obj in resp["Contents"]:
            key = obj["Key"]
            parts = key.split("/")
            if len(parts) >= 4:
                logs.append({
                    "id": key,
                    "app_id": parts[2],
                    "filename": parts[3],
                    "last_modified": obj["LastModified"].isoformat()
                })
        return sorted(logs, key=lambda x: x["last_modified"], reverse=True)
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/llm-logs/detail")
async def get_llm_log_detail(key: str):
    """Fetch the content of a specific LLM log."""
    s3 = get_s3()
    import json
    try:
        obj = s3.s3_client.get_object(Bucket=s3.bucket_name, Key=key)
        data = json.loads(obj["Body"].read().decode("utf-8"))
        return data
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

# --- Single Page Application (SPA) Support ---

@app.get("/{full_path:path}")
async def serve_react_app(full_path: str):
    """Serves the React app for any path not matched by other routes."""
    # Special handling for static assets
    if full_path.startswith("assets/"):
        asset_path = frontend_dist / full_path
        if asset_path.exists():
            return FileResponse(asset_path)
    
    # API or Download paths that reached here are 404s
    if full_path.startswith("api/") or full_path.startswith("download/"):
        raise HTTPException(status_code=404)
    
    # Everything else serves index.html (Client-side routing)
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    
    return HTMLResponse("<h1>SST UI: React frontend not found. Please build it.</h1>")

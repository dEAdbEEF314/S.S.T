from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic_settings import BaseSettings, SettingsConfigDict
from .s3_service import S3UIService
import os

class UIConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_name: str

app = FastAPI(title="S.S.T Web Interface")
templates = Jinja2Templates(directory="src/ui/templates")

def get_s3():
    config = UIConfig()
    return S3UIService(
        endpoint_url=config.s3_endpoint_url,
        access_key=config.s3_access_key,
        secret_key=config.s3_secret_key,
        bucket_name=config.s3_bucket_name
    )

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/archive", response_class=HTMLResponse)
async def archive_page(request: Request):
    s3 = get_s3()
    albums = s3.list_albums("archive")
    return templates.TemplateResponse("list.html", {
        "request": request, 
        "title": "Archive (Success)", 
        "albums": albums,
        "status": "archive"
    })

@app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request):
    s3 = get_s3()
    albums = s3.list_albums("review")
    return templates.TemplateResponse("list.html", {
        "request": request, 
        "title": "Review (Pending)", 
        "albums": albums,
        "status": "review"
    })

@app.get("/download/{status}/{app_id}")
async def download_album(status: str, app_id: str):
    if status not in ["archive", "review"]:
        raise HTTPException(status_code=400)
    
    s3 = get_s3()
    # Simple check for ready status again
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

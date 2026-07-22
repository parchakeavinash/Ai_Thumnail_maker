import os
import logging
import asyncio
import json 

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlmodel import Session
from uuid import uuid4
from datetime import datetime, timezone

from app.database import get_sessoin
from app.models import Job, Thumbnail

from app.services.generator import process_job,STYLE_ORDER
from app.services.imagekit_services import upload_file, get_variants

from pydantic import BaseModel
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# request response schemas

class CreateJobRequest(BaseModel):
    prompt:str
    num_thumbnails:int
    headshot_url: str

class CreateJobResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime

class ThumbnailResponse(BaseModel):
    id: int
    style_name: str
    status: str
    imagekit_url: str | None = None
    error_message: str  | None = None
    variants: dict[str, str] | None = None

class JobResponse(BaseModel):
    id: int
    prompt: str
    num_thumbnails: int
    status: str
    headshot_url: str
    thumbnails: List[ThumbnailResponse]

    # model_config = ConfigDict(from_attributes = True)  - need to understand

@router.post('/upload-file')
async def upload_file(file:UploadFile=File(...),session:Session = Depends(get_sessoin)):
    contents = await file.read()
    url = await upload_file(
        file_bytes = contents,
        file_name = file.filename or "headshot.jpg",
        folder = "uploads",
        content_type = file.content_type or "image/png"
    )
    return {"url": url}


@router.post('/jobs', response_model = CreateJobResponse, status_code = 201)
async def create_job(request:CreateJobRequest,session:Session = Depends(get_sessoin)):
    if request.num_thumbnails < 1 or request.num_thumbnails > 3:
        raise HTTPException(status_code = 400, detail="num_thumbnails must be between 1 and 3")

    job = Job(
        prompt= request.prompt,
        num_thumbnails = request.num_thumbnails,
        headshot_url = request.headshot_url,
        # status = "pending"
    )
    session.add(job)

    styles = STYLE_ORDER[:request.num_thumbnails]

    for style_name in styles:
        thumb = Thumbnail(
            job_id = job.id,
            style_name = style_name
        )
        session.add(thumb)
    
    session.commit()
    session.refresh(job)
    asyncio.create_task(process_job(job.id))

    return CreateJobResponse(job_id=job.id)


@router.get('/job/{job_id}', response_model = JobResponse)
def get_job(job_id: str,session:Session = Depends(get_sessoin)):
    job = session.get(Job,job_id)
    if not job:
        raise HTTPException(status_code = 404, detail="Job not found")

    thumbnails = session.exec(Select(Thumbnail).where(Thumbnail.job_id == job_id)).all()

    thumb_response = []

    for thumb in thumbnails:
        if thumb.imagekit_url:
            variants = get_variants(thumb.imagekit_url)
        else:
            variants = None
        thumb_response.append(
            ThumbnailResponse(
                id = thumb.id,
                style_name = thumb.style_name,
                status = thumb.status,
                imagekit_url = thumb.imagekit_url,
                error_message = thumb.error_message,
                variants = variants
            )
        )

    return JobResponse(
        id = job.id,
        prompt = job.prompt,
        num_thumbnails = job.num_thumbnails,
        status = job.status,
        headshot_url = job.headshot_url,
        thumbnails = thumb_response
    )
    return job

@router.get('/jobs/{job_id}/stream')
async def stream_job(job_id: str):
    async def event_generator():
        from database import engine
        sent_thumbnails = set()

        while True:
            with Session(engine) as session:
                job = session.get(Job,job_id)
                if not job:
                    yield f"event: error\ndata: {json.dumps({'error': 'job not found'})}\n\n"
                    return

                thumbnails = session.exec(
                    Select(Thumbnail).where(Thumbnail.job_id == job_id)
                ).all()

                for t in thumbnails:
                    if t.id not in sent_thumbnails:
                        continue
                    if t.status == "uploaded":
                        variants = get_variants(t.imagekit_url)
                        data = json.dumps({
                            "thumbnail_id": t.id,
                            "style_name": t.style_name,
                            "imagekit_url": t.imagekit_url,
                            "variants": variants
                        })
                        yield f"event: thumbnail_ready\ndata: {data}\n\n"
                        sent_thumbnails.add(t.id)
                    elif t.status == "failed":
                        data = json.dumps({
                            "thumbnail_id": t.id,
                            "style_name": t.style_name,
                            "error_message": t.error_message
                        })
                        yield f"event: thumbnail_error\ndata: {data}\n\n"
                        sent_thumbnails.add(t.id)
                    
                all_done = all(t.status in ("uploaded","failed")) for t in thumbnails
                if all_done and len(sent_thumbnails) == len(thumbnails):
                    yield f"event: job_completed\ndata: {json.dumps({'job_id':job.id})}\\n\n"
                    return

            await asyncio.sleep(1)    

    return StreamingResponse(
        event_generator(),
        media_type = "text/event-stream",
        headers = {
            'Cache-Control':'no-cache',
            'Connection':'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )

async def process_events():
    
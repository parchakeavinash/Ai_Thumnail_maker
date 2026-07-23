import logging
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from datetime import datetime

from app.database import get_session, engine
from app.models import Job, Thumbnail

from app.services.generator import process_job, STYLE_ORDER
from app.services.imagekit_services import upload_to_imagekit, get_variants

from typing import List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

api = APIRouter()


# ── Request / Response schemas ────────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    prompt: str
    num_thumbnails: int
    headshot_url: str


class CreateJobResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime


class ThumbnailResponse(BaseModel):
    id: str
    style_name: str
    status: str
    imagekit_url: Optional[str] = None
    error_message: Optional[str] = None
    variants: Optional[dict] = None


class JobResponse(BaseModel):
    id: str
    prompt: str
    num_thumbnails: int
    status: str
    headshot_url: str
    thumbnails: List[ThumbnailResponse]

    model_config = {"from_attributes": True}


# ── Routes ────────────────────────────────────────────────────────────────────

@api.post("/upload-headshot")
async def upload_headshot(file: UploadFile = File(...)):
    contents = await file.read()
    url = await upload_to_imagekit(
        file_bytes=contents,
        file_name=file.filename or "headshot.jpg",
        folder="uploads",
    )
    return {"url": url}



@api.post("/jobs", response_model=CreateJobResponse, status_code=201)
async def create_job(
    request: CreateJobRequest,
    session: Session = Depends(get_session),
):
    if request.num_thumbnails < 1 or request.num_thumbnails > 3:
        raise HTTPException(
            status_code=400, detail="num_thumbnails must be between 1 and 3"
        )

    job = Job(
        prompt=request.prompt,
        num_thumbnails=request.num_thumbnails,
        headshot_url=request.headshot_url,
    )
    session.add(job)

    styles = STYLE_ORDER[: request.num_thumbnails]
    for style_name in styles:
        thumb = Thumbnail(job_id=job.id, style_name=style_name)
        session.add(thumb)

    session.commit()
    session.refresh(job)

    # Fire-and-forget background task
    asyncio.create_task(process_job(job.id))

    return CreateJobResponse(
        job_id=job.id,
        status=job.status,
        created_at=job.created_at,
    )


@api.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    thumbnails = session.exec(
        select(Thumbnail).where(Thumbnail.job_id == job_id)
    ).all()

    thumb_responses = []
    for thumb in thumbnails:
        variants = get_variants(thumb.imagekit_url) if thumb.imagekit_url else None
        thumb_responses.append(
            ThumbnailResponse(
                id=thumb.id,
                style_name=thumb.style_name,
                status=thumb.status,
                imagekit_url=thumb.imagekit_url,
                error_message=thumb.error_message,
                variants=variants,
            )
        )

    return JobResponse(
        id=job.id,
        prompt=job.prompt,
        num_thumbnails=job.num_thumbnails,
        status=job.status,
        headshot_url=job.headshot_url,
        thumbnails=thumb_responses,
    )


@api.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    async def event_generator():
        sent_thumbnails: set = set()

        while True:
            with Session(engine) as session:
                job = session.get(Job, job_id)
                if not job:
                    yield f"event: error\ndata: {json.dumps({'error': 'job not found'})}\n\n"
                    return

                thumbnails = session.exec(
                    select(Thumbnail).where(Thumbnail.job_id == job_id)
                ).all()

                for t in thumbnails:
                    # Only process thumbnails we haven't reported yet
                    if t.id in sent_thumbnails:
                        continue

                    if t.status == "uploaded":
                        variants = get_variants(t.imagekit_url)
                        data = json.dumps(
                            {
                                "thumbnail_id": t.id,
                                "style_name": t.style_name,
                                "imagekit_url": t.imagekit_url,
                                "variants": variants,
                            }
                        )
                        yield f"event: thumbnail_ready\ndata: {data}\n\n"
                        sent_thumbnails.add(t.id)

                    elif t.status == "error":
                        data = json.dumps(
                            {
                                "thumbnail_id": t.id,
                                "style_name": t.style_name,
                                "error_message": t.error_message,
                            }
                        )
                        yield f"event: thumbnail_error\ndata: {data}\n\n"
                        sent_thumbnails.add(t.id)

                all_done = all(t.status in ("uploaded", "error") for t in thumbnails)
                if all_done and thumbnails and len(sent_thumbnails) == len(thumbnails):
                    yield f"event: job_completed\ndata: {json.dumps({'job_id': job.id})}\n\n"
                    return

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
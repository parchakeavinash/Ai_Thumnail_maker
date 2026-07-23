import asyncio
import logging

from sqlmodel import Session, select
from app.database import engine
from app.models import Job, Thumbnail
from app.services.nanobanana_service import generate_thumbnail
from app.services.imagekit_services import upload_to_imagekit

logger = logging.getLogger(__name__)

STYLES = {
    "bold_dramatic": (
        "Create a bold, dramatic YouTube thumbnail with high contrast, "
        "cinematic lighting, dark moody background, and powerful composition. "
        "The person's face should be prominent with a dramatic expression."
    ),
    "clean_minimal": (
        "Create a clean, minimal YouTube thumbnail with bright lighting, "
        "white/light background, modern professional aesthetic, plenty of "
        "whitespace, and sharp clean composition. The person should look "
        "approachable and professional."
    ),
    "vibrant_energetic": (
        "Create a vibrant, energetic YouTube thumbnail with colorful gradients, "
        "dynamic angles, eye-catching pop-art style colors, and energetic "
        "composition. The person should have an excited or engaging expression."
    ),
}

STYLE_ORDER = ["bold_dramatic", "clean_minimal", "vibrant_energetic"]


async def generate_single_thumbnail(thumbnail_id: str, prompt: str, headshot_url: str):
    # ── Mark as generating ───────────────────────────────────────────────────
    with Session(engine) as session:
        thumb = session.get(Thumbnail, thumbnail_id)
        if not thumb:
            logger.warning(f"Thumbnail not found: {thumbnail_id}")
            return
        thumb.status = "generating"
        style_name = thumb.style_name
        session.add(thumb)
        session.commit()

    style_prompt = STYLES[style_name]

    # ── Generate + upload ────────────────────────────────────────────────────
    try:
        image_bytes = await generate_thumbnail(prompt, style_prompt, headshot_url)

        # Get job_id before closing the session
        with Session(engine) as session:
            thumb = session.get(Thumbnail, thumbnail_id)
            job_id = thumb.job_id if thumb else None

        url = await upload_to_imagekit(
            file_bytes=image_bytes,
            file_name=f"thumbnail_{thumbnail_id}.png",
            folder=f"jobs/{job_id}",
        )
        if not url:
            raise ValueError("Failed to upload thumbnail — no URL returned")

        # ── Save URL, mark as uploaded ───────────────────────────────────────
        with Session(engine) as session:
            thumb = session.get(Thumbnail, thumbnail_id)
            if not thumb:
                logger.warning(f"Thumbnail not found after upload: {thumbnail_id}")
                return
            thumb.imagekit_url = url
            thumb.status = "uploaded"
            session.add(thumb)
            session.commit()

        logger.info(f"Thumbnail {thumbnail_id} uploaded successfully to ImageKit")

    except Exception as e:
        logger.error(f"Error generating thumbnail {thumbnail_id}: {e}")
        with Session(engine) as session:
            thumb = session.get(Thumbnail, thumbnail_id)
            if not thumb:
                logger.warning(f"Thumbnail not found on error: {thumbnail_id}")
                return
            thumb.status = "error"
            thumb.error_message = str(e)[:500]
            session.add(thumb)
            session.commit()


async def process_job(job_id: str):
    # ── Mark job as processing ───────────────────────────────────────────────
    thumbnail_ids: list[str] = []

    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            logger.warning(f"Job not found: {job_id}")
            return
        job.status = "processing"
        prompt = job.prompt
        headshot_url = job.headshot_url
        session.add(job)
        session.commit()

        thumbnails = session.exec(
            select(Thumbnail).where(Thumbnail.job_id == job_id)
        ).all()
        thumbnail_ids = [t.id for t in thumbnails]

    # ── Run all thumbnail tasks concurrently ─────────────────────────────────
    tasks = [
        generate_single_thumbnail(t_id, prompt, headshot_url)
        for t_id in thumbnail_ids
    ]
    await asyncio.gather(*tasks, return_exceptions=True)

    # ── Mark job completed / failed ──────────────────────────────────────────
    with Session(engine) as session:
        thumbnails = session.exec(
            select(Thumbnail).where(Thumbnail.job_id == job_id)
        ).all()
        failed = any(t.status == "error" for t in thumbnails)

        job = session.get(Job, job_id)
        if job:
            job.status = "failed" if failed else "completed"
            session.add(job)
            session.commit()

    logger.info(f"Job {job_id} finished — status: {'failed' if failed else 'completed'}")
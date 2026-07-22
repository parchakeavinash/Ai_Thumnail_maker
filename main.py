import logging

from app.database import init_db
from app.queue import setup_background_queue
from app.routes import api
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
import asyncio

logger = logging.getLogger(__name__xtlib import asynccontextmanager
import asy)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
        yield
    finally:
        pass


app = FastAPI(title= "AI Thumbnail Generator API",lifespan=lifespan)
app.include_router(api,prefix="/api",tags=["api"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="[IP_ADDRESS]", port=8000, reload=True)
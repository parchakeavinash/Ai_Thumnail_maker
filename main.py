import logging

from app.database import init_db
from app.routes import api
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
import asyncio

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
        yield
    finally:
        pass


app = FastAPI(title="AI Thumbnail Generator API", lifespan=lifespan)
app.include_router(api, prefix="/api", tags=["api"])


@app.get("/", tags=["health"])
def root():
    return {"message": "AI Thumbnail Generator API is running 🚀", "docs": "/docs"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
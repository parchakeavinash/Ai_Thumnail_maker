import base64
import httpx
import asyncio

from app.config import (
    IMAGEKIT_PRIVATE_KEY,
    IMAGEKIT_PUBLIC_KEY,
    IMAGEKIT_URL_ENDPOINT,
)

# ImageKit upload endpoint (different from the API domain)
IMAGEKIT_UPLOAD_URL = "https://upload.imagekit.io/api/v1/files/upload"


def _basic_auth_header() -> str:
    """Build HTTP Basic Auth header using private key as username, empty password."""
    credentials = f"{IMAGEKIT_PRIVATE_KEY}:"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"


async def upload_to_imagekit(
    file_bytes: bytes,
    file_name: str,
    folder: str,
) -> str:
    """Upload raw bytes to ImageKit and return the public CDN URL."""
    headers = {"Authorization": _basic_auth_header()}

    data = {
        "fileName": file_name,
        "folder": folder,
        "isPrivateFile": "false",
        "useUniqueFileName": "false",
    }

    files = {"file": (file_name, file_bytes, "image/png")}

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            IMAGEKIT_UPLOAD_URL,
            headers=headers,
            data=data,
            files=files,
        )
        response.raise_for_status()
        result = response.json()
        return result["url"]


def get_variants(base_url: str) -> dict:
    """Return 3 platform-size variant URLs using ImageKit URL transformations."""
    return {
        "youtube":  f"{base_url}?tr=w-1280,h-720,c-maintain_ratio,fo-auto",
        "twitter":  f"{base_url}?tr=w-600,h-338,c-maintain_ratio,fo-auto",
        "linkedin": f"{base_url}?tr=w-800,h-450,c-maintain_ratio,fo-auto",
    }
from imagekitio import ImageKit

from app.config import IMAGEKIT_PRIVATE_KEY,IMAGEKIT_PUBLIC_KEY,IMAGEKIT_BASE_URL

imagekit = ImageKit(
    public_key = IMAGEKIT_PUBLIC_KEY,
    private_key = IMAGEKIT_PRIVATE_KEY,
    url_endpoint = IMAGEKIT_BASE_URL
)

#upload files
async def upload_file(file_bytes: bytes, file_name: str, folder: str, content_type: str = 'image/png/jpeg'):
    result =  await imagekit.files.upload(
                file=file_bytes,
                file_name = file_name,
                folder = folder,
                content_type = content_type,
                is_private_file = False,
                use_unique_file_name = False
    )
    return result.url

def get_variants(base_url: str) ->dict:
    """return 3 sizes variants urls using imagkit transformations"""

    return {
        "youtube": f"{base_url}?tr=w-1280,h-720,c-maintain_ratio,fo-auto",
        "twitter": f"{base_url}?tr=w-600,h-338,c-maintain_ratio,fo-auto",
        "linkedin": f"{base_url}?tr=w-800,h-450,c-maintain_ratio,fo-auto"
    }
    
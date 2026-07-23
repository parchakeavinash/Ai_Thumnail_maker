from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)


async def generate_thumbnail(
    user_prompt: str,
    style_prompt: str,
    headshot_url: str | None = None,
) -> bytes:

    full_prompt = (
        f"Style:\n{style_prompt}\n\n"
        f"User Prompt:\n{user_prompt}\n\n"
        "Important: The generated thumbnail MUST prominently feature the person "
        "shown in the provided reference headshot photo. Keep their likeness accurate."
    )

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part(
                    inline_data=types.Blob(
                        mime_type="image/jpeg",
                        data=await _fetch_image_bytes(headshot_url),
                    )
                ) if headshot_url else None,
                types.Part(text=full_prompt),
            ],
        )
    ]

    # Remove None parts (when no headshot provided)
    contents[0] = types.Content(
        role="user",
        parts=[p for p in contents[0].parts if p is not None],
    )

    response = client.models.generate_content(
        model="gemini-2.0-flash-preview-image-generation",
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )

    if not response.candidates:
        raise ValueError(
            "No candidates returned by image model (possibly blocked by safety filters)."
        )

    for part in response.candidates[0].content.parts:
        if part.inline_data:
            return part.inline_data.data

    raise ValueError("No image returned from Gemini.")


async def _fetch_image_bytes(url: str) -> bytes:
    """Download an image from a URL and return its raw bytes."""
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=30)
        response.raise_for_status()
        return response.content
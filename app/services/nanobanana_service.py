from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)


async def generate_thumbnail(
    user_prompt: str,
    style_prompt: str,
    headshot_url: str | None = None,
) -> bytes:

    full_prompt = f"""
        Style:
        {style_prompt}

        User Prompt:
        {user_prompt}
        "Important: The generated thumbnail MUST prominently feature the person
        "shown in the provided reference headshot photo. Keep their likeness accurate..
    """

    response = client.models.generate_content(
        model="gemini-2.0-flash-preview-image-generation",
        input = {
            "role": "user",
            "content": [
                {"type": "input_image", "url": headshot_url}
                {"type": "text", "text": full_prompt}
            ]
        },
        # config = types.GenerateContentConfig(
        #     response_modalities=["IMAGE"]
        # )
    )
    if not response.candidates:
        raise ValueError("No candidates returned by image model (possibly blocked by safety filters).")

    for part in response.candidates[0].content.parts:
        if part.inline_data:
            return part.inline_data.data

    raise ValueError("No image returned from Gemini.")
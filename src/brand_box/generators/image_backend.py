"""
Gemini-powered image generation backend.

Shared by logo, social, and video generators.  Supports both the Gemini
generate_content API (for Nano Banana models) and the generate_images
API (for Imagen 4 models).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

from brand_box.config import GEMINI_API_KEY, GEMINI_IMAGE_MODEL

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """Lazy-init a google.genai Client."""
    global _client
    if _client is not None:
        return _client

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set.  Get a free key at https://aistudio.google.com/apikey "
            "and add it to your .env file."
        )

    from google import genai
    _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def generate_image(
    prompt: str,
    output_path: str,
    model: str | None = None,
    cache_dir: Path | None = None,
) -> str:
    """
    Generate a single image from *prompt* and save to *output_path*.

    Uses the Gemini generate_content API for flash-image models (Nano Banana)
    or the generate_images API for Imagen models.

    Returns the absolute path to the saved image.
    """
    model = model or GEMINI_IMAGE_MODEL

    # Check cache
    if cache_dir:
        cached = _cache_lookup(prompt, model, cache_dir)
        if cached:
            import shutil
            shutil.copy2(str(cached), output_path)
            logger.info("Cache hit — copied to %s", output_path)
            return str(Path(output_path).resolve())

    client = _get_client()
    image_bytes: bytes | None = None

    if "imagen" in model:
        image_bytes = _generate_with_imagen(client, model, prompt)
    else:
        image_bytes = _generate_with_gemini(client, model, prompt)

    if image_bytes is None:
        raise RuntimeError(f"No image returned by model {model}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(image_bytes)
    logger.info("Image saved to %s", output_path)

    # Store in cache
    if cache_dir:
        _cache_store(prompt, model, output_path, cache_dir)

    return str(Path(output_path).resolve())


def _generate_with_gemini(client, model: str, prompt: str) -> bytes | None:
    """Use generate_content with response_modalities=['IMAGE', 'TEXT']."""
    from google.genai import types

    response = client.models.generate_content(
        model=model,
        contents=f"Generate an image: {prompt}",
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )

    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            return part.inline_data.data
    return None


def _generate_with_imagen(client, model: str, prompt: str) -> bytes | None:
    """Use generate_images API for Imagen models."""
    from google.genai import types

    response = client.models.generate_images(
        model=model,
        prompt=prompt,
        config=types.GenerateImagesConfig(number_of_images=1),
    )

    if response.generated_images:
        return response.generated_images[0].image.image_bytes
    return None


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def _cache_key(prompt: str, model: str) -> str:
    md5 = hashlib.md5(f"{model}|{prompt}".encode()).hexdigest()
    return f"{md5}.png"


def _cache_lookup(prompt: str, model: str, cache_dir: Path) -> Optional[Path]:
    path = cache_dir / _cache_key(prompt, model)
    return path if path.is_file() else None


def _cache_store(prompt: str, model: str, src_path: str, cache_dir: Path) -> None:
    import shutil
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / _cache_key(prompt, model)
    if not dest.exists():
        shutil.copy2(src_path, dest)

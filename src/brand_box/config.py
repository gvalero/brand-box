"""
Configuration for brand-box.

Loads API keys and settings from environment / .env files.
Searches for .env in: CWD, project root, brand-box package root.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Try loading .env from CWD first, then package root
_cwd_env = Path.cwd() / ".env"
_pkg_env = Path(__file__).resolve().parent.parent.parent / ".env"

if _cwd_env.is_file():
    load_dotenv(_cwd_env)
elif _pkg_env.is_file():
    load_dotenv(_pkg_env)


# ---------------------------------------------------------------------------
# Google Gemini (primary image + text generation)
# ---------------------------------------------------------------------------
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")

# ---------------------------------------------------------------------------
# Azure OpenAI (optional — for GPT-4o scriptwriting)
# ---------------------------------------------------------------------------
AZURE_OPENAI_ENDPOINT: str = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY: str = os.environ.get("AZURE_OPENAI_KEY", "")
AZURE_OPENAI_DEPLOYMENT_GPT: str = os.environ.get("AZURE_OPENAI_DEPLOYMENT_GPT", "gpt-4o")

# ---------------------------------------------------------------------------
# Manus AI (primary video generation — agent-based)
# ---------------------------------------------------------------------------
MANUS_API_KEY: str = os.environ.get("MANUS_API_KEY", "")
MANUS_API_BASE: str = os.environ.get("MANUS_API_BASE", "https://api.manus.ai")

# ---------------------------------------------------------------------------
# ElevenLabs (primary TTS — high-quality voice)
# ---------------------------------------------------------------------------
ELEVENLABS_API_KEY: str = os.environ.get("ELEVENLABS_API_KEY", "")

# ---------------------------------------------------------------------------
# Azure Speech (fallback TTS — for video narration)
# ---------------------------------------------------------------------------
AZURE_SPEECH_KEY: str = os.environ.get("AZURE_SPEECH_KEY", "")
AZURE_SPEECH_REGION: str = os.environ.get("AZURE_SPEECH_REGION", "westeurope")

# ---------------------------------------------------------------------------
# Image generation settings
# ---------------------------------------------------------------------------
# Preferred Gemini model for image generation. Options:
#   gemini-2.5-flash-image         (Nano Banana — fast, good quality)
#   gemini-3-pro-image-preview     (Nano Banana Pro — best quality)
#   gemini-3.1-flash-image-preview (Nano Banana 2 — newest, fast)
#   imagen-4.0-generate-001        (Imagen 4 — via generate_images API)
#   imagen-4.0-fast-generate-001   (Imagen 4 Fast)
GEMINI_IMAGE_MODEL: str = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_VIDEO_WIDTH = 1080
DEFAULT_VIDEO_HEIGHT = 1920
DEFAULT_VIDEO_FPS = 30

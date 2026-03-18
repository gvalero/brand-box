"""
Manus AI video generation backend.

Submits video generation tasks to the Manus API, polls for completion,
and downloads the resulting video file. This produces far superior video
compared to our local MoviePy pipeline.

API docs: https://open.manus.ai/docs
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen, urlretrieve
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

MANUS_AGENT_PROFILE = "manus-1.6-max"
POLL_INTERVAL = 15  # seconds
MAX_POLL_TIME = 600  # 10 minutes max wait


class ManusVideoGenerator:
    """Generate videos via the Manus AI agent API."""

    def __init__(self, api_key: str | None = None, api_base: str | None = None) -> None:
        from brand_box.config import MANUS_API_KEY, MANUS_API_BASE
        self.api_key = api_key or MANUS_API_KEY
        self.api_base = (api_base or MANUS_API_BASE).rstrip("/")
        if not self.api_key:
            raise RuntimeError("MANUS_API_KEY not set. Add it to your .env file.")

    def generate_video(
        self,
        brand_name: str,
        concept: str,
        format_id: str = "teaser",
        identity_context: str = "",
        output_path: str | None = None,
        logo_path: str | None = None,
    ) -> str:
        """Submit a video task to Manus and download the result.

        Returns: path to the downloaded MP4 file.
        """
        prompt = self._build_prompt(brand_name, concept, format_id, identity_context)

        logger.info("Submitting video task to Manus…")
        task = self._create_task(prompt, logo_path)
        task_id = task.get("task_id") or task.get("id")
        if not task_id:
            raise RuntimeError(f"Manus task creation failed: {task}")

        task_url = task.get("task_url", f"{self.api_base}/app/{task_id}")
        logger.info("Task created: %s (ID: %s)", task_url, task_id)

        # Poll for completion
        result = self._poll_task(task_id)

        # Download the video
        if not output_path:
            output_path = str(Path.cwd() / "output" / "videos" / f"video_{format_id}.mp4")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        video_url = self._extract_video_url(result)
        if video_url:
            self._download_file(video_url, output_path)
            logger.info("Video downloaded → %s", output_path)
            return output_path

        raise RuntimeError("Could not find video file in Manus task output.")

    def _build_prompt(
        self,
        brand_name: str,
        concept: str,
        format_id: str,
        identity_context: str,
    ) -> str:
        format_descriptions = {
            "teaser": "a 15-25 second teaser/promo video for social media (TikTok/Instagram Reels). Fast-paced, exciting, with dynamic transitions and background music.",
            "explainer": "a 30-45 second explainer video showing how the product works. Clear, friendly, with step-by-step visuals and background music.",
            "testimonial": "a 20-40 second testimonial-style video with an emotional parent/user reaction. Warm, authentic tone with background music.",
            "fact": "a 15-30 second 'Did You Know?' video with a surprising fact hook. Informative with background music.",
            "founder": "a 30-60 second founder story video. Personal, inspiring, with background music.",
        }
        format_desc = format_descriptions.get(format_id, format_descriptions["teaser"])

        return f"""Create {format_desc}

Brand: {brand_name}
Product: {concept}
{f"Brand identity: {identity_context}" if identity_context else ""}

Requirements:
- Vertical format (9:16) optimized for TikTok/Instagram Reels
- Professional quality with smooth transitions
- Include background music that matches the brand tone
- Use high-quality visuals (animated/illustrated, not stock photos)
- Include the brand name "{brand_name}" in the intro and outro
- Add captions/text overlays for key points
- End with a clear call-to-action (follow, link in bio, etc.)
- Export as MP4 video file

The video should feel polished, engaging, and scroll-stopping."""

    def _create_task(self, prompt: str, logo_path: str | None = None) -> dict:
        """POST /v1/tasks — create a new Manus task."""
        body = {
            "prompt": prompt,
            "agentProfile": MANUS_AGENT_PROFILE,
            "taskMode": "agent",
            "createShareableLink": True,
        }
        return self._api_post("/v1/tasks", body)

    def _poll_task(self, task_id: str) -> dict:
        """Poll GET /v1/tasks/{id} until the task completes."""
        start = time.time()
        while time.time() - start < MAX_POLL_TIME:
            result = self._api_get(f"/v1/tasks/{task_id}")
            status = result.get("status", "").lower()

            if status in ("completed", "done", "finished", "succeeded"):
                logger.info("Manus task completed ✓")
                return result
            elif status in ("failed", "error", "cancelled"):
                raise RuntimeError(f"Manus task failed: {result.get('error', status)}")

            elapsed = int(time.time() - start)
            logger.info("Task status: %s (%ds elapsed)…", status, elapsed)
            time.sleep(POLL_INTERVAL)

        raise RuntimeError(f"Manus task timed out after {MAX_POLL_TIME}s")

    def _extract_video_url(self, task_result: dict) -> str | None:
        """Extract the video download URL from a completed task result."""
        # Check common response patterns
        for key in ("output", "result", "outputs", "artifacts", "files"):
            data = task_result.get(key)
            if not data:
                continue

            # Could be a list of files
            if isinstance(data, list):
                for item in data:
                    url = self._find_video_in_item(item)
                    if url:
                        return url
            # Could be a dict with file info
            elif isinstance(data, dict):
                url = self._find_video_in_item(data)
                if url:
                    return url
            # Could be a direct URL string
            elif isinstance(data, str) and (".mp4" in data or "video" in data):
                return data

        # Check for share_url as fallback
        share_url = task_result.get("share_url")
        if share_url:
            logger.info("No direct video URL found, share URL: %s", share_url)

        return None

    @staticmethod
    def _find_video_in_item(item) -> str | None:
        """Look for a video URL in a result item."""
        if isinstance(item, str):
            if ".mp4" in item or "video" in item:
                return item
            return None
        if isinstance(item, dict):
            for url_key in ("url", "download_url", "file_url", "link", "src"):
                url = item.get(url_key, "")
                if url and (".mp4" in url or "video" in url.lower()):
                    return url
            # Check mime type
            if "video" in item.get("type", "") or "video" in item.get("mime_type", ""):
                return item.get("url") or item.get("download_url")
        return None

    def _download_file(self, url: str, output_path: str) -> None:
        """Download a file from URL to local path."""
        logger.info("Downloading video from %s …", url[:80])
        req = Request(url)
        req.add_header("API_KEY", self.api_key)
        try:
            with urlopen(req, timeout=120) as response:
                Path(output_path).write_bytes(response.read())
        except (HTTPError, URLError):
            # Try without auth header (might be a public/share URL)
            urlretrieve(url, output_path)

    # --- HTTP helpers ---

    def _api_post(self, path: str, body: dict) -> dict:
        """Make an authenticated POST request."""
        url = f"{self.api_base}{path}"
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, method="POST")
        req.add_header("API_KEY", self.api_key)
        req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"Manus API error {e.code}: {body_text}") from e

    def _api_get(self, path: str) -> dict:
        """Make an authenticated GET request."""
        url = f"{self.api_base}{path}"
        req = Request(url)
        req.add_header("API_KEY", self.api_key)

        try:
            with urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"Manus API error {e.code}: {body_text}") from e

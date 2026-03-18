"""
Social media asset generator.

Generates profile pictures, banners, bio text, and post templates
for various social platforms.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
import numpy as np

from brand_box.project import BrandProject, BrandIdentity

logger = logging.getLogger(__name__)

# Platform-specific asset sizes
PLATFORM_SPECS = {
    "tiktok": {
        "profile_pic": (200, 200),
        "banner": None,
        "bio_max_chars": 80,
    },
    "instagram": {
        "profile_pic": (320, 320),
        "banner": None,
        "bio_max_chars": 150,
    },
    "youtube": {
        "profile_pic": (800, 800),
        "banner": (2560, 1440),
        "bio_max_chars": 1000,
    },
    "twitter": {
        "profile_pic": (400, 400),
        "banner": (1500, 500),
        "bio_max_chars": 160,
    },
    "linkedin": {
        "profile_pic": (400, 400),
        "banner": (1584, 396),
        "bio_max_chars": 2000,
    },
}


class SocialGenerator:
    """Generate social media profile assets for a brand."""

    def __init__(self) -> None:
        self._openai_client = None
        self._gemini_client = None
        self._init_clients()

    def _init_clients(self) -> None:
        from brand_box.config import (
            AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY,
            AZURE_OPENAI_DEPLOYMENT_GPT, GEMINI_API_KEY,
        )

        if AZURE_OPENAI_KEY and AZURE_OPENAI_ENDPOINT:
            try:
                from openai import AzureOpenAI
                self._openai_client = AzureOpenAI(
                    api_key=AZURE_OPENAI_KEY,
                    azure_endpoint=AZURE_OPENAI_ENDPOINT,
                    api_version="2024-12-01-preview",
                )
                self._openai_deployment = AZURE_OPENAI_DEPLOYMENT_GPT
                return
            except Exception as e:
                logger.warning("Azure OpenAI init failed: %s", e)

        if GEMINI_API_KEY:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=GEMINI_API_KEY)
                return
            except Exception as e:
                logger.warning("Gemini init failed: %s", e)

    def generate(
        self,
        project: BrandProject,
        platforms: list[str] | None = None,
        output_dir: str = "output/social",
    ) -> dict:
        """Generate social media assets for specified platforms.

        Returns: {
            "bios": {"tiktok": "...", "instagram": "..."},
            "profile_pics": {"tiktok": "path", ...},
            "banners": {"youtube": "path", ...},
        }
        """
        platforms = platforms or ["tiktok", "instagram", "youtube"]
        platforms = [p.lower() for p in platforms if p.lower() in PLATFORM_SPECS]

        if not platforms:
            raise ValueError(f"No valid platforms. Choose from: {list(PLATFORM_SPECS.keys())}")

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        result: dict = {"bios": {}, "profile_pics": {}, "banners": {}}

        # 1. Generate bios
        bios = self._generate_bios(project, platforms)
        result["bios"] = bios

        # 2. Generate profile pictures
        for platform in platforms:
            spec = PLATFORM_SPECS[platform]
            pic_path = str(out / f"{platform}_profile.png")

            try:
                self._generate_profile_pic_ai(project, spec["profile_pic"], pic_path)
            except Exception as e:
                logger.warning("AI profile pic failed for %s: %s — using template", platform, e)
                self._generate_profile_pic_template(project, spec["profile_pic"], pic_path)

            result["profile_pics"][platform] = pic_path

        # 3. Generate banners (for platforms that have them)
        for platform in platforms:
            spec = PLATFORM_SPECS[platform]
            if spec["banner"]:
                banner_path = str(out / f"{platform}_banner.png")

                try:
                    self._generate_banner_ai(project, spec["banner"], banner_path)
                except Exception as e:
                    logger.warning("AI banner failed for %s: %s — using template", platform, e)
                    self._generate_banner_template(project, spec["banner"], banner_path)

                result["banners"][platform] = banner_path

        return result

    def _generate_bios(self, project: BrandProject, platforms: list[str]) -> dict[str, str]:
        """Use LLM to generate platform-specific bio text."""
        name = project.name or "Our Brand"
        identity = project.identity

        platform_specs_str = "\n".join(
            f"- {p}: max {PLATFORM_SPECS[p]['bio_max_chars']} characters"
            for p in platforms
        )

        prompt = f"""Write social media bios for the brand "{name}".
Product: {project.concept}
Tagline: {identity.tagline if identity else ''}
Tone: {identity.tone if identity else 'professional, friendly'}

Platforms:
{platform_specs_str}

Return a JSON object mapping platform name to bio text:
{{"tiktok": "bio text...", "instagram": "bio text..."}}

Guidelines:
- Each bio must fit the platform's character limit
- Include relevant emojis
- Include a call-to-action where appropriate
- TikTok/Instagram: punchy, emoji-heavy
- YouTube: descriptive, keyword-rich
- Twitter/LinkedIn: professional but approachable

Return ONLY valid JSON."""

        try:
            if self._openai_client:
                text = self._call_openai(prompt)
            elif self._gemini_client:
                text = self._call_gemini(prompt)
            else:
                return {p: f"{name} — {identity.tagline if identity else project.concept}" for p in platforms}

            return self._parse_bios(text, platforms, name, project.concept)
        except Exception as e:
            logger.warning("Bio generation failed: %s", e)
            return {p: f"{name} — {identity.tagline if identity else project.concept}" for p in platforms}

    def _generate_profile_pic_ai(self, project: BrandProject, size: tuple[int, int], output_path: str) -> None:
        """Create profile pic from the chosen logo, resized for the platform."""
        # Use the chosen logo if available — profile pics should be consistent
        logo_path = self._get_logo_path(project)
        if logo_path:
            img = Image.open(logo_path).convert("RGBA")
            # Fit logo into a square canvas with brand background color
            bg_color = self._hex_to_rgb(
                project.identity.background_color if project.identity and project.identity.background_color else "#FFFFFF"
            )
            canvas = Image.new("RGBA", (max(img.size), max(img.size)), (*bg_color, 255))
            # Center the logo
            x = (canvas.width - img.width) // 2
            y = (canvas.height - img.height) // 2
            canvas.paste(img, (x, y), img if img.mode == "RGBA" else None)
            canvas = canvas.resize(size, Image.LANCZOS)
            canvas.save(output_path, "PNG")
            return

        # Fallback to template if no logo exists
        self._generate_profile_pic_template(project, size, output_path)

    def _generate_profile_pic_template(
        self, project: BrandProject, size: tuple[int, int], output_path: str
    ) -> None:
        """Pillow fallback profile pic: brand initial on colored circle."""
        identity = project.identity
        primary = identity.primary_color if identity and identity.primary_color else "#5b4fc7"
        accent = identity.accent_color if identity and identity.accent_color else "#f6a623"
        name = project.name or "B"

        w, h = max(size[0], 200), max(size[1], 200)
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Circle background
        draw.ellipse([4, 4, w - 4, h - 4], fill=self._hex_to_rgb(primary))

        # Initial
        initial = name[0].upper()
        font_size = int(w * 0.45)
        font = self._get_font(font_size, bold=True)

        bbox = draw.textbbox((0, 0), initial, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (w - tw) // 2
        y = (h - th) // 2 - int(h * 0.03)
        draw.text((x, y), initial, fill=self._hex_to_rgb(accent), font=font)

        img = img.resize(size, Image.LANCZOS)
        img.save(output_path, "PNG")

    def _generate_banner_ai(
        self, project: BrandProject, size: tuple[int, int], output_path: str
    ) -> None:
        """Generate banner via Gemini."""
        from brand_box.generators.image_backend import generate_image

        identity = project.identity
        name = project.name or "Brand"
        color_hint = f"Use colors: {identity.primary_color}, {identity.secondary_color}, {identity.accent_color}." if identity and identity.primary_color else ""

        prompt = (
            f"Design a social media banner/cover image for '{name}'. "
            f"Product: {project.concept}. "
            f"Style: clean, modern, wide landscape format. "
            f"{color_hint} "
            f"Include the brand name '{name}' prominently. "
            f"Professional, eye-catching, suitable for a YouTube channel banner."
        )

        generate_image(prompt, output_path)

        # Resize to target
        img = Image.open(output_path)
        img = img.resize(size, Image.LANCZOS)
        img.save(output_path, "PNG")

    def _generate_banner_template(
        self, project: BrandProject, size: tuple[int, int], output_path: str
    ) -> None:
        """Pillow fallback banner: brand name + tagline on gradient."""
        identity = project.identity
        primary = identity.primary_color if identity and identity.primary_color else "#5b4fc7"
        accent = identity.accent_color if identity and identity.accent_color else "#f6a623"
        name = project.name or "Brand"
        tagline = identity.tagline if identity and identity.tagline else ""

        w, h = size
        img = Image.new("RGB", (w, h))

        # Gradient
        c1 = self._hex_to_rgb(primary)
        c2_hex = identity.secondary_color if identity and identity.secondary_color else primary
        c2 = self._hex_to_rgb(c2_hex)

        for x in range(w):
            r = int(c1[0] + (c2[0] - c1[0]) * x / w)
            g = int(c1[1] + (c2[1] - c1[1]) * x / w)
            b = int(c1[2] + (c2[2] - c1[2]) * x / w)
            for y in range(h):
                img.putpixel((x, y), (r, g, b))

        draw = ImageDraw.Draw(img)

        # Brand name
        font_large = self._get_font(int(h * 0.25), bold=True)
        bbox = draw.textbbox((0, 0), name, font=font_large)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2
        y = h // 2 - int(h * 0.2)
        draw.text((x, y), name, fill=(255, 255, 255), font=font_large)

        # Tagline
        if tagline:
            font_small = self._get_font(int(h * 0.08))
            bbox2 = draw.textbbox((0, 0), tagline, font=font_small)
            tw2 = bbox2[2] - bbox2[0]
            x2 = (w - tw2) // 2
            draw.text((x2, y + int(h * 0.3)), tagline, fill=self._hex_to_rgb(accent), font=font_small)

        img.save(output_path, "PNG")

    def _call_openai(self, prompt: str) -> str:
        response = self._openai_client.chat.completions.create(
            model=self._openai_deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=800,
        )
        return response.choices[0].message.content

    def _call_gemini(self, prompt: str) -> str:
        response = self._gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text

    @staticmethod
    def _parse_bios(text: str, platforms: list[str], name: str, concept: str) -> dict[str, str]:
        text = text.strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                bios = json.loads(match.group())
                return {p: bios.get(p, f"{name} — {concept}") for p in platforms}
            except json.JSONDecodeError:
                pass
        return {p: f"{name} — {concept}" for p in platforms}

    @staticmethod
    def _get_logo_path(project: BrandProject) -> str | None:
        """Return the path to the chosen logo, if it exists on disk."""
        # Check metadata for explicit choice first
        chosen = project.metadata.get("chosen_logo", "")
        if chosen and Path(chosen).is_file():
            return chosen
        # Fall back to first logo in list
        for p in project.logo_paths:
            if Path(p).is_file():
                return p
        return None

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    @staticmethod
    def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        candidates = [
            r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for fp in candidates:
            try:
                return ImageFont.truetype(fp, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

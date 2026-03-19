"""
Logo generator.

Uses Gemini image generation to produce logo options for a brand.
Falls back to Pillow-based template logos if AI generation is unavailable.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from brand_box.models.artifacts import LogoConcept, StageReview
from brand_box.project import BrandIdentity

logger = logging.getLogger(__name__)

# Short rationale descriptions keyed by style keyword
_STYLE_RATIONALES: dict[str, str] = {
    "app icon": "Modern app icon style with gradient",
    "wordmark": "Clean wordmark with minimalist typography",
    "mascot": "Playful mascot character logo",
    "geometric": "Bold abstract geometric mark",
    "watercolor": "Organic hand-drawn watercolor style",
}


def _rationale_for(style: str) -> str:
    """Derive a short rationale string from the style description."""
    for keyword, rationale in _STYLE_RATIONALES.items():
        if keyword in style.lower():
            return rationale
    return f"Logo variant: {style[:60]}"


class LogoGenerator:
    """Generate logo images for a brand."""

    def __init__(self) -> None:
        self.last_concepts: list[LogoConcept] = []

    def generate(
        self,
        brand_name: str,
        concept: str,
        identity: Optional[BrandIdentity] = None,
        output_dir: str = "output/logos",
        count: int = 3,
    ) -> list[str]:
        """Generate *count* logo variants and return their file paths."""
        concepts = self.generate_rich(
            brand_name, concept, identity=identity,
            output_dir=output_dir, count=count,
        )
        return [p for c in concepts for p in c.asset_paths]

    def generate_rich(
        self,
        brand_name: str,
        concept: str,
        identity: Optional[BrandIdentity] = None,
        output_dir: str = "output/logos",
        count: int = 3,
    ) -> list[LogoConcept]:
        """Generate *count* logo variants wrapped in :class:`LogoConcept` objects."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        concepts: list[LogoConcept] = []
        styles = self._logo_styles()[:count]

        for i, style in enumerate(styles):
            path = str(out / f"logo_{i + 1}.png")
            prompt = self._build_prompt(brand_name, concept, identity, style)

            try:
                from brand_box.generators.image_backend import generate_image
                generate_image(prompt, path)
                logger.info("AI logo %d saved to %s", i + 1, path)
            except Exception as e:
                logger.warning("AI logo generation failed: %s — using template", e)
                self._generate_template(brand_name, identity, path, style)

            logo_concept = LogoConcept(
                id=f"logo-{uuid.uuid4().hex[:8]}",
                style=style,
                prompt=prompt,
                rationale=_rationale_for(style),
                asset_paths=[path],
            )
            concepts.append(logo_concept)

        self.last_concepts = concepts
        return concepts

    @staticmethod
    def _logo_styles() -> list[str]:
        """Return a list of logo style descriptions."""
        return [
            "modern app icon with rounded corners, flat design, centered symbol",
            "minimalist wordmark logo, clean typography, no background",
            "mascot-style logo with a friendly character, playful, colorful",
            "abstract geometric logo, bold shapes, professional",
            "hand-drawn/watercolor style logo, organic, warm",
        ]

    @staticmethod
    def _build_prompt(
        brand_name: str,
        concept: str,
        identity: Optional[BrandIdentity],
        style: str,
    ) -> str:
        color_hint = ""
        if identity and identity.primary_color:
            color_hint = (
                f" Use these brand colors: primary {identity.primary_color}, "
                f"secondary {identity.secondary_color}, accent {identity.accent_color}."
            )

        return (
            f"Design a professional logo for '{brand_name}', "
            f"a product described as: {concept}. "
            f"Style: {style}. "
            f"The logo should be on a clean, simple background (white or transparent).{color_hint} "
            f"High quality, vector-like, suitable for web and app icons. "
            f"Do NOT include any text or lettering in the image — only the graphic/symbol."
        )

    @staticmethod
    def _generate_template(
        brand_name: str,
        identity: Optional[BrandIdentity],
        output_path: str,
        style: str,
    ) -> None:
        """Pillow fallback: generate a simple text-based logo."""
        primary = identity.primary_color if identity and identity.primary_color else "#5b4fc7"
        accent = identity.accent_color if identity and identity.accent_color else "#f6a623"

        def hex_to_rgb(h: str) -> tuple:
            h = h.lstrip("#")
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

        size = 512
        img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)

        # Rounded rect background
        try:
            draw.rounded_rectangle(
                [20, 20, size - 20, size - 20],
                radius=60,
                fill=hex_to_rgb(primary),
            )
        except TypeError:
            draw.rectangle([20, 20, size - 20, size - 20], fill=hex_to_rgb(primary))

        # Brand initial
        initial = brand_name[0].upper() if brand_name else "B"
        font_candidates = [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
        ]
        font = ImageFont.load_default()
        for fp in font_candidates:
            try:
                font = ImageFont.truetype(fp, 200)
                break
            except (OSError, IOError):
                continue

        bbox = draw.textbbox((0, 0), initial, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (size - tw) // 2
        y = (size - th) // 2 - 20
        draw.text((x, y), initial, fill=hex_to_rgb(accent), font=font)

        img.save(output_path, "PNG")
        logger.info("Template logo saved to %s", output_path)

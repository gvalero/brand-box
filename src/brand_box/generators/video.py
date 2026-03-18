"""
Video assembler for social media content.

Composes images, captions, audio, and branding into vertical (9:16) MP4 videos
using MoviePy and Pillow.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class VideoAssembler:
    """Assemble vertical social media videos from script + images + audio."""

    def __init__(
        self,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        brand_colors: dict | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.colors = brand_colors or {
            "primary": "#5b4fc7",
            "secondary": "#f6a623",
            "accent": "#FFD700",
            "background": "#FFF8F0",
            "text": "#FFFFFF",
            "text_dark": "#333333",
        }

    def assemble_video(
        self,
        script: dict,
        audio_paths: dict,
        image_paths: dict | None = None,
        output_path: str | None = None,
        brand_name: str = "",
        tagline: str = "",
    ) -> str:
        """Main assembly: intro → segments → CTA → audio overlay → MP4.

        Args:
            script: Generated script dict with segments
            audio_paths: {"segments": {0: "path", ...}, "full": "full_path"}
            image_paths: {0: "img_path", 1: "img_path", ...} or None
            output_path: Destination MP4 path
            brand_name: Brand name for intro slide
            tagline: Tagline for intro slide

        Returns: Absolute path to output MP4
        """
        from moviepy import (
            ImageClip, AudioFileClip, CompositeVideoClip,
            concatenate_videoclips,
        )

        clips = []

        # 1. Intro slide
        if brand_name:
            intro_arr = self._render_intro(brand_name, tagline)
            intro_clip = ImageClip(intro_arr, duration=2.0)
            try:
                intro_clip = intro_clip.with_effects([
                    __import__("moviepy").video.fx.CrossFadeIn(0.8)
                ])
            except Exception:
                pass
            clips.append(intro_clip)

        # 2. Content segments
        seg_audio = audio_paths.get("segments", {})
        for seg in script.get("segments", []):
            idx = seg["index"]
            duration = seg.get("duration_seconds", 5)

            # Use actual audio duration if available
            if idx in seg_audio:
                try:
                    from brand_box.generators.audio import AudioGenerator
                    duration = AudioGenerator.get_audio_duration(seg_audio[idx])
                except Exception:
                    pass

            # Visual: AI image or text slide
            if image_paths and idx in image_paths and Path(image_paths[idx]).is_file():
                clip = self._create_image_clip(image_paths[idx], duration)
            else:
                text = seg.get("text", "")
                clip = self._create_text_slide(text, duration)

            # Caption overlay
            caption_text = seg.get("text", "")
            if caption_text:
                clip = self._add_caption(clip, caption_text)

            clips.append(clip)

        # 3. CTA slide
        cta_text = script.get("cta", "Link in bio!")
        cta_arr = self._render_cta(cta_text)
        cta_clip = ImageClip(cta_arr, duration=3.0)
        clips.append(cta_clip)

        # 4. Concatenate
        if not clips:
            raise RuntimeError("No clips to assemble")

        final_video = concatenate_videoclips(clips, method="compose")

        # 5. Add audio
        full_audio_path = audio_paths.get("full")
        if full_audio_path and Path(full_audio_path).is_file():
            audio_clip = AudioFileClip(full_audio_path)
            # Trim or pad to match video
            if audio_clip.duration > final_video.duration:
                audio_clip = audio_clip.subclipped(0, final_video.duration)
            final_video = final_video.with_audio(audio_clip)

        # 6. Export
        if not output_path:
            output_path = str(Path.cwd() / "output" / "video.mp4")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        final_video.write_videofile(
            output_path,
            fps=self.fps,
            codec="libx264",
            audio_codec="aac",
            bitrate="4000k",
            logger="bar",
        )

        # Cleanup
        for c in clips:
            try:
                c.close()
            except Exception:
                pass

        logger.info("Video exported → %s", output_path)
        return str(Path(output_path).resolve())

    def estimate_duration(self, script: dict) -> float:
        """Estimate total video duration from script."""
        seg_dur = sum(s.get("duration_seconds", 5) for s in script.get("segments", []))
        return 2.0 + seg_dur + 3.0  # intro + segments + CTA

    # ------------------------------------------------------------------
    # Slide renderers
    # ------------------------------------------------------------------

    def _render_intro(self, brand_name: str, tagline: str) -> np.ndarray:
        """Render branded intro slide as numpy array."""
        img = Image.new("RGB", (self.width, self.height), self._hex_to_rgb(self.colors["primary"]))
        draw = ImageDraw.Draw(img)

        # Brand name
        font_large = self._get_font(80, bold=True)
        bbox = draw.textbbox((0, 0), brand_name, font=font_large)
        tw = bbox[2] - bbox[0]
        x = (self.width - tw) // 2
        y = self.height // 2 - 80
        draw.text((x, y), brand_name, fill=self._hex_to_rgb(self.colors["text"]), font=font_large)

        # Tagline
        if tagline:
            font_small = self._get_font(36)
            bbox2 = draw.textbbox((0, 0), tagline, font=font_small)
            tw2 = bbox2[2] - bbox2[0]
            x2 = (self.width - tw2) // 2
            draw.text((x2, y + 120), tagline, fill=self._hex_to_rgb(self.colors["accent"]), font=font_small)

        return np.array(img)

    def _render_cta(self, cta_text: str) -> np.ndarray:
        """Render CTA end card."""
        img = Image.new("RGB", (self.width, self.height), self._hex_to_rgb(self.colors["primary"]))
        draw = ImageDraw.Draw(img)

        wrapped = self._wrap_text(cta_text, self.width - 160, 48)
        font = self._get_font(48, bold=True)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (self.width - tw) // 2
        y = (self.height - th) // 2
        draw.multiline_text(
            (x, y), wrapped,
            fill=self._hex_to_rgb(self.colors["accent"]),
            font=font,
            align="center",
        )
        return np.array(img)

    def _create_text_slide(self, text: str, duration: float):
        """Create a text-on-gradient slide as an ImageClip."""
        from moviepy import ImageClip

        img = self._render_gradient_bg()
        draw = ImageDraw.Draw(img)

        # Semi-transparent overlay
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 100))
        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        wrapped = self._wrap_text(text, self.width - 120, 44)
        font = self._get_font(44)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (self.width - tw) // 2
        y = (self.height - th) // 2
        draw.multiline_text(
            (x, y), wrapped,
            fill=(255, 255, 255),
            font=font,
            align="center",
        )
        return ImageClip(np.array(img), duration=duration)

    def _create_image_clip(self, image_path: str, duration: float):
        """Load image, crop to 9:16, optional Ken Burns effect."""
        from moviepy import ImageClip

        img = Image.open(image_path).convert("RGB")
        img = self._crop_to_aspect(img, self.width, self.height)
        img = img.resize((self.width, self.height), Image.LANCZOS)

        base_clip = ImageClip(np.array(img), duration=duration)

        # Ken Burns zoom: 1.0 → 1.08 over duration
        try:
            def make_frame(get_frame, t):
                frame = get_frame(t)
                progress = t / max(duration, 0.01)
                scale = 1.0 + 0.08 * progress
                h, w = frame.shape[:2]
                new_h, new_w = int(h * scale), int(w * scale)
                resized = np.array(
                    Image.fromarray(frame).resize((new_w, new_h), Image.LANCZOS)
                )
                # Center crop back to original size
                y_off = (new_h - h) // 2
                x_off = (new_w - w) // 2
                return resized[y_off:y_off + h, x_off:x_off + w]

            return base_clip.transform(make_frame)
        except Exception:
            return base_clip

    def _add_caption(self, clip, text: str, position: str = "bottom"):
        """Add semi-transparent caption bar to a clip."""
        from moviepy import ImageClip, CompositeVideoClip

        max_chars = 60
        if len(text) > max_chars:
            text = text[:max_chars - 3] + "…"

        bar_height = 140
        bar_img = Image.new("RGBA", (self.width, bar_height), (0, 0, 0, 160))
        draw = ImageDraw.Draw(bar_img)

        wrapped = self._wrap_text(text, self.width - 60, 28)
        font = self._get_font(28)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (self.width - tw) // 2
        y = (bar_height - th) // 2
        draw.multiline_text((x, y), wrapped, fill=(255, 255, 255), font=font, align="center")

        bar_arr = np.array(bar_img.convert("RGB"))
        bar_clip = ImageClip(bar_arr, duration=clip.duration)

        if position == "top":
            y_pos = int(self.height * 0.06)
        elif position == "center":
            y_pos = (self.height - bar_height) // 2
        else:
            y_pos = int(self.height * 0.85)

        bar_clip = bar_clip.with_position(("center", y_pos))
        return CompositeVideoClip([clip, bar_clip], size=(self.width, self.height))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _render_gradient_bg(self) -> Image.Image:
        """Create a vertical gradient background."""
        c1 = self._hex_to_rgb(self.colors["primary"])
        c2 = self._hex_to_rgb(self.colors.get("secondary", self.colors["primary"]))

        img = Image.new("RGB", (self.width, self.height))
        for y in range(self.height):
            r = int(c1[0] + (c2[0] - c1[0]) * y / self.height)
            g = int(c1[1] + (c2[1] - c1[1]) * y / self.height)
            b = int(c1[2] + (c2[2] - c1[2]) * y / self.height)
            for x in range(self.width):
                img.putpixel((x, y), (r, g, b))
        return img

    @staticmethod
    def _crop_to_aspect(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """Center-crop image to target aspect ratio."""
        w, h = img.size
        target_ratio = target_w / target_h
        current_ratio = w / h

        if current_ratio > target_ratio:
            new_w = int(h * target_ratio)
            left = (w - new_w) // 2
            img = img.crop((left, 0, left + new_w, h))
        elif current_ratio < target_ratio:
            new_h = int(w / target_ratio)
            top = (h - new_h) // 2
            img = img.crop((0, top, w, top + new_h))
        return img

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
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        for fp in candidates:
            try:
                return ImageFont.truetype(fp, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    @staticmethod
    def _wrap_text(text: str, max_width: int, font_size: int) -> str:
        """Word-wrap text to fit within max_width pixels."""
        avg_char_width = font_size * 0.55
        chars_per_line = max(1, int(max_width / avg_char_width))

        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if len(test) > chars_per_line and current:
                lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)
        return "\n".join(lines)

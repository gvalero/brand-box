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
from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)


RENDER_PROFILES: dict[str, dict[str, int | str]] = {
    "reel": {"width": 1080, "height": 1920, "label": "Vertical social"},
    "square": {"width": 1080, "height": 1080, "label": "Square social"},
    "web-hero": {"width": 1920, "height": 1080, "label": "Website hero"},
    "youtube": {"width": 1920, "height": 1080, "label": "YouTube landscape"},
}


class VideoAssembler:
    """Assemble vertical social media videos from script + images + audio."""

    def __init__(
        self,
        width: int | None = None,
        height: int | None = None,
        fps: int = 30,
        brand_colors: dict | None = None,
        profile: str = "reel",
    ) -> None:
        profile_data = RENDER_PROFILES.get(profile, RENDER_PROFILES["reel"])
        self.profile = profile
        self.width = width or int(profile_data["width"])
        self.height = height or int(profile_data["height"])
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
        storyboard: dict | None = None,
        background_music_path: str = "",
    ) -> str:
        """Main assembly: intro → segments → CTA → audio overlay → MP4.

        Args:
            script: Generated script dict with segments
            audio_paths: {"segments": {0: "path", ...}, "full": "full_path"}
            image_paths: {0: "img_path", 1: "img_path", ...} or None
            output_path: Destination MP4 path
            brand_name: Brand name for intro slide
            tagline: Tagline for intro slide
            storyboard: Optional structured storyboard metadata

        Returns: Absolute path to output MP4
        """
        from moviepy import (
            AudioFileClip,
            CompositeAudioClip,
            CompositeVideoClip,
            ImageClip,
            concatenate_audioclips,
            concatenate_videoclips,
        )
        import moviepy.audio.fx as afx

        clips = []
        audio_resources = []
        try:
            vfx = __import__("moviepy").video.fx
        except Exception:
            vfx = None

        # 1. Intro slide
        if brand_name:
            intro_arr = self._render_intro(brand_name, tagline)
            intro_clip = ImageClip(intro_arr, duration=2.0)
            if vfx:
                try:
                    intro_clip = intro_clip.with_effects([vfx.FadeIn(0.3), vfx.FadeOut(0.25)])
                except Exception:
                    pass
            clips.append(intro_clip)

        # 2. Content segments
        seg_audio = audio_paths.get("segments", {})
        segments = script.get("segments", [])
        for scene_number, seg in enumerate(segments, start=1):
            idx = seg["index"]
            duration = seg.get("duration_seconds", 5)
            scene = None
            if storyboard:
                scenes = storyboard.get("scenes", [])
                scene = next((item for item in scenes if item.get("index", -1) == idx), None)

            # Use actual audio duration if available
            if idx in seg_audio:
                try:
                    from brand_box.generators.audio import AudioGenerator
                    duration = AudioGenerator.get_audio_duration(seg_audio[idx])
                except Exception:
                    pass

            # Visual: AI image or text slide
            asset_value = image_paths[idx] if image_paths and idx in image_paths else None
            asset_list = self._normalize_scene_assets(asset_value)
            if asset_list:
                clip = self._create_scene_sequence_clip(
                    image_paths=asset_list,
                    text=seg.get("text", ""),
                    duration=duration,
                    scene=scene or seg,
                    scene_number=scene_number,
                    scene_count=len(segments),
                )
            else:
                clip = self._create_text_scene(
                    text=seg.get("text", ""),
                    duration=duration,
                    scene=scene or seg,
                    scene_number=scene_number,
                    scene_count=len(segments),
                )

            if vfx:
                try:
                    clip = clip.with_effects([vfx.FadeIn(0.18), vfx.FadeOut(0.18)])
                except Exception:
                    pass

            clips.append(clip)

        # 3. CTA slide
        cta_text = script.get("cta", "Link in bio!")
        cta_arr = self._render_cta(cta_text)
        cta_clip = ImageClip(cta_arr, duration=3.0)
        clips.append(cta_clip)

        # 4. Concatenate
        if not clips:
            raise RuntimeError("No clips to assemble")

        try:
            final_video = concatenate_videoclips(clips, method="compose", padding=-0.12)
        except TypeError:
            final_video = concatenate_videoclips(clips, method="compose")

        # 5. Add audio
        audio_layers = []
        full_audio_path = audio_paths.get("full")
        if full_audio_path and Path(full_audio_path).is_file():
            voice_clip = AudioFileClip(full_audio_path)
            if voice_clip.duration > final_video.duration:
                voice_clip = voice_clip.subclipped(0, final_video.duration)
            audio_layers.append(voice_clip)
            audio_resources.append(voice_clip)

        music_clip = None
        if background_music_path and Path(background_music_path).is_file():
            try:
                source_music_clip = AudioFileClip(background_music_path)
                audio_resources.append(source_music_clip)
                looped = self._loop_audio_to_duration(source_music_clip, final_video.duration, concatenate_audioclips)
                audio_resources.append(looped)
                trimmed = looped.subclipped(0, final_video.duration)
                audio_resources.append(trimmed)
                faded = trimmed.with_effects([
                    afx.AudioFadeIn(min(0.8, final_video.duration / 6)),
                    afx.AudioFadeOut(min(1.0, final_video.duration / 5)),
                ])
                audio_resources.append(faded)
                if audio_layers:
                    music_clip = faded.with_volume_scaled(0.14)
                else:
                    music_clip = faded.with_volume_scaled(0.22)
                audio_layers.insert(0, music_clip)
                audio_resources.append(music_clip)
            except Exception:
                music_clip = None

        if audio_layers:
            if len(audio_layers) == 1:
                final_audio = audio_layers[0]
            else:
                final_audio = CompositeAudioClip(audio_layers)
                audio_resources.append(final_audio)
            final_video = final_video.with_audio(final_audio)

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
        try:
            final_video.close()
        except Exception:
            pass
        for audio_clip in audio_resources:
            try:
                audio_clip.close()
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
        img = self._render_gradient_bg()
        draw = ImageDraw.Draw(img)
        is_landscape = self.width > self.height
        is_square = self.width == self.height

        accent = self._hex_to_rgb(self.colors["accent"])
        secondary = self._hex_to_rgb(self.colors.get("secondary", self.colors["primary"]))
        bubble = self._scale(280)
        draw.ellipse([self._scale(80), self._scale(140, axis="h"), self._scale(80) + bubble, self._scale(140, axis="h") + bubble], fill=(*accent, 90))
        draw.ellipse([self.width - self._scale(420), self.height - self._scale(520, axis="h"), self.width - self._scale(80), self.height - self._scale(180, axis="h")], fill=(*secondary, 80))

        glass_height = int(self.height * (0.28 if not is_landscape else 0.36))
        glass = Image.new("RGBA", (self.width - self._scale(120), glass_height), (255, 255, 255, 32))
        mask = Image.new("L", glass.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, glass.width - 1, glass.height - 1], radius=self._scale(40), fill=255)
        img = img.convert("RGBA")
        img.paste(glass, (self._scale(60), self.height // 2 - glass_height // 2), mask)
        draw = ImageDraw.Draw(img)

        # Brand name
        font_large = self._get_font(self._scale(110 if not is_landscape else 92), bold=True)
        bbox = draw.textbbox((0, 0), brand_name, font=font_large)
        tw = bbox[2] - bbox[0]
        x = (self.width - tw) // 2
        y = self.height // 2 - self._scale(90, axis="h")
        draw.text((x, y), brand_name, fill=self._hex_to_rgb(self.colors["text"]), font=font_large)

        # Tagline
        if tagline:
            font_small = self._get_font(self._scale(40 if not is_square else 34))
            bbox2 = draw.textbbox((0, 0), tagline, font=font_small)
            tw2 = bbox2[2] - bbox2[0]
            x2 = (self.width - tw2) // 2
            draw.text((x2, y + self._scale(140, axis="h")), tagline, fill=self._hex_to_rgb(self.colors["accent"]), font=font_small)

        kicker = "Short-form brand story"
        font_kicker = self._get_font(self._scale(28), bold=True)
        kicker_bbox = draw.textbbox((0, 0), kicker, font=font_kicker)
        kw = kicker_bbox[2] - kicker_bbox[0]
        kx = (self.width - kw) // 2
        draw.text((kx, y - self._scale(82, axis="h")), kicker, fill=(255, 255, 255), font=font_kicker)

        return np.array(img.convert("RGB"))

    def _render_cta(self, cta_text: str) -> np.ndarray:
        """Render CTA end card."""
        img = self._render_gradient_bg()
        draw = ImageDraw.Draw(img)

        overlay = Image.new("RGBA", (self.width, self.height), (10, 10, 10, 60))
        img = img.convert("RGBA")
        img.alpha_composite(overlay)
        draw = ImageDraw.Draw(img)

        wrapped = self._wrap_text(cta_text, self.width - self._scale(160), self._scale(48))
        font = self._get_font(self._scale(48), bold=True)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (self.width - tw) // 2
        y = (self.height - th) // 2

        panel = Image.new("RGBA", (self.width - self._scale(120), th + self._scale(180, axis="h")), (255, 255, 255, 26))
        panel_mask = Image.new("L", panel.size, 0)
        panel_draw = ImageDraw.Draw(panel_mask)
        panel_draw.rounded_rectangle([0, 0, panel.width - 1, panel.height - 1], radius=self._scale(36), fill=255)
        img.paste(panel, (self._scale(60), y - self._scale(80, axis="h")), panel_mask)
        draw = ImageDraw.Draw(img)

        draw.multiline_text(
            (x, y), wrapped,
            fill=self._hex_to_rgb(self.colors["accent"]),
            font=font,
            align="center",
        )
        small = "Link in bio"
        small_font = self._get_font(self._scale(30))
        sb = draw.textbbox((0, 0), small, font=small_font)
        draw.text(((self.width - (sb[2] - sb[0])) // 2, y + th + self._scale(48, axis="h")), small, fill=(255, 255, 255), font=small_font)
        return np.array(img.convert("RGB"))

    def _create_text_scene(self, text: str, duration: float, scene: dict, scene_number: int, scene_count: int):
        """Create a richer text-first scene when no image is available."""
        from moviepy import ImageClip

        img = self._render_gradient_bg().convert("RGBA")
        overlay = Image.new("RGBA", (self.width, self.height), (10, 10, 18, 110))
        img.alpha_composite(overlay)

        draw = ImageDraw.Draw(img)
        self._draw_scene_header(draw, scene=scene, scene_number=scene_number, scene_count=scene_count)

        card_h = int(self.height * (0.42 if self.width <= self.height else 0.5))
        card = Image.new("RGBA", (self.width - self._scale(120), card_h), (255, 255, 255, 30))
        mask = Image.new("L", card.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([0, 0, card.width - 1, card.height - 1], radius=self._scale(42), fill=255)
        img.paste(card, (self._scale(60), self.height // 2 - card_h // 2), mask)
        draw = ImageDraw.Draw(img)

        headline = scene.get("on_screen_text") or self._truncate_text(text, 50)
        subtitle = self._truncate_text(text, 130)

        font_head = self._get_font(self._scale(72 if self.width <= self.height else 54), bold=True)
        font_body = self._get_font(self._scale(34 if self.width <= self.height else 28))
        head_wrapped = self._wrap_text(headline, self.width - self._scale(220), self._scale(72 if self.width <= self.height else 54))
        sub_wrapped = self._wrap_text(subtitle, self.width - self._scale(220), self._scale(34 if self.width <= self.height else 28))

        hb = draw.multiline_textbbox((0, 0), head_wrapped, font=font_head, spacing=10)
        sb = draw.multiline_textbbox((0, 0), sub_wrapped, font=font_body, spacing=8)
        hx = self._scale(110)
        hy = self.height // 2 - int(card_h * 0.3)
        draw.multiline_text((hx, hy), head_wrapped, fill=(255, 255, 255), font=font_head, spacing=10)
        draw.multiline_text((hx, hy + (hb[3] - hb[1]) + self._scale(36, axis="h")), sub_wrapped, fill=(232, 232, 232), font=font_body, spacing=8)
        self._draw_progress(draw, scene_number, scene_count)
        return ImageClip(np.array(img.convert("RGB")), duration=duration)

    def _create_scene_clip(self, image_path: str, text: str, duration: float, scene: dict, scene_number: int, scene_count: int):
        """Create a layered, more editorial scene from one source image."""
        from moviepy import CompositeVideoClip, ImageClip

        source = Image.open(image_path).convert("RGB")
        background = self._build_scene_background(source)
        foreground = self._build_foreground_panel(source)
        overlay = self._build_scene_overlay(
            text=text,
            scene=scene,
            scene_number=scene_number,
            scene_count=scene_count,
        )

        bg_clip = self._animated_zoom_clip(background, duration=duration, zoom_strength=0.08)
        fg_clip = self._animated_zoom_clip(foreground, duration=duration, zoom_strength=0.04).with_position(("center", "center"))
        overlay_clip = ImageClip(np.array(overlay), duration=duration)
        return CompositeVideoClip([bg_clip, fg_clip, overlay_clip], size=(self.width, self.height))

    def _create_scene_sequence_clip(self, image_paths: list[str], text: str, duration: float, scene: dict, scene_number: int, scene_count: int):
        """Create a scene that can cut across multiple visual assets."""
        from moviepy import concatenate_videoclips

        valid_paths = [path for path in image_paths if Path(path).is_file()]
        if not valid_paths:
            return self._create_text_scene(text, duration, scene, scene_number, scene_count)
        if len(valid_paths) == 1:
            return self._create_scene_clip(valid_paths[0], text, duration, scene, scene_number, scene_count)

        asset_clips = []
        per_asset = max(0.6, duration / len(valid_paths))
        for asset_i, path in enumerate(valid_paths):
            beat_scene = dict(scene)
            beats = scene.get("visual_beats", []) if isinstance(scene.get("visual_beats", []), list) else []
            if asset_i > 0 and asset_i - 1 < len(beats):
                beat_scene["purpose"] = "cutaway"
                beat_scene["shot_type"] = beat_scene.get("shot_type") or "insert"
                beat_scene["on_screen_text"] = beat_scene.get("on_screen_text") or self._truncate_text(str(beats[asset_i - 1]), 36)
            asset_clip = self._create_scene_clip(
                image_path=path,
                text=text,
                duration=per_asset,
                scene=beat_scene,
                scene_number=scene_number,
                scene_count=scene_count,
            )
            asset_clips.append(asset_clip)

        try:
            combined = concatenate_videoclips(asset_clips, method="compose", padding=-0.08)
        except TypeError:
            combined = concatenate_videoclips(asset_clips, method="compose")
        # Close intermediate clips — the concatenated result holds the data
        for ac in asset_clips:
            try:
                ac.close()
            except Exception:
                pass
        return combined

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

    def _build_scene_background(self, source: Image.Image) -> Image.Image:
        """Create a blurred full-frame background from the source image."""
        bg = self._crop_to_aspect(source.copy(), self.width, self.height)
        bg = bg.resize((self.width, self.height), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(18))
        dark = Image.new("RGBA", (self.width, self.height), (8, 10, 18, 96))
        bg = bg.convert("RGBA")
        bg.alpha_composite(dark)
        return bg.convert("RGB")

    def _build_foreground_panel(self, source: Image.Image) -> Image.Image:
        """Place the source image inside a framed portrait panel."""
        if self.width > self.height:
            panel_width = int(self.width * 0.56)
            panel_height = int(self.height * 0.76)
        elif self.width == self.height:
            panel_width = int(self.width * 0.76)
            panel_height = int(self.height * 0.68)
        else:
            panel_width = int(self.width * 0.82)
            panel_height = int(self.height * 0.68)
        framed = Image.new("RGBA", (panel_width, panel_height), (0, 0, 0, 0))

        shadow = Image.new("RGBA", (panel_width, panel_height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle([20, 24, panel_width - 20, panel_height - 8], radius=42, fill=(0, 0, 0, 120))
        shadow = shadow.filter(ImageFilter.GaussianBlur(18))
        framed.alpha_composite(shadow)

        card = Image.new("RGBA", (panel_width - 36, panel_height - 36), (255, 255, 255, 255))
        card_mask = Image.new("L", card.size, 0)
        card_mask_draw = ImageDraw.Draw(card_mask)
        card_mask_draw.rounded_rectangle([0, 0, card.width - 1, card.height - 1], radius=34, fill=255)
        framed.paste(card, (18, 12), card_mask)

        art = self._crop_to_aspect(source.copy(), card.width - 24, card.height - 24)
        art = art.resize((card.width - 24, card.height - 24), Image.LANCZOS)
        art_rgba = art.convert("RGBA")
        art_mask = Image.new("L", art_rgba.size, 0)
        art_mask_draw = ImageDraw.Draw(art_mask)
        art_mask_draw.rounded_rectangle([0, 0, art_rgba.width - 1, art_rgba.height - 1], radius=26, fill=255)
        framed.paste(art_rgba, (30, 24), art_mask)

        return framed.convert("RGB")

    def _build_scene_overlay(self, text: str, scene: dict, scene_number: int, scene_count: int) -> Image.Image:
        """Render editorial overlay elements for one scene."""
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        self._draw_scene_header(draw, scene=scene, scene_number=scene_number, scene_count=scene_count)

        headline = scene.get("on_screen_text") or self._truncate_text(text, 42)
        subtitle = self._truncate_text(text, 90)
        if self.width > self.height:
            card_x = int(self.width * 0.58)
            card_y = int(self.height * 0.26)
            card_w = self.width - card_x - self._scale(70)
            card_h = int(self.height * 0.42)
        else:
            card_x = self._scale(72)
            card_y = self.height - self._scale(500, axis="h")
            card_w = self.width - self._scale(144)
            card_h = self._scale(270, axis="h")

        draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h], radius=self._scale(34), fill=(14, 16, 25, 182))
        draw.rounded_rectangle([card_x + self._scale(18), card_y + self._scale(18, axis="h"), card_x + self._scale(30), card_y + card_h - self._scale(18, axis="h")], radius=self._scale(6), fill=(*self._hex_to_rgb(self.colors["accent"]), 255))

        font_head = self._get_font(self._scale(56 if self.width <= self.height else 42), bold=True)
        font_body = self._get_font(self._scale(28 if self.width <= self.height else 24))
        head_wrapped = self._wrap_text(headline, card_w - self._scale(120), self._scale(56 if self.width <= self.height else 42))
        sub_wrapped = self._wrap_text(subtitle, card_w - self._scale(120), self._scale(28 if self.width <= self.height else 24))
        draw.multiline_text((card_x + self._scale(56), card_y + self._scale(34, axis="h")), head_wrapped, fill=(255, 255, 255), font=font_head, spacing=8)

        hb = draw.multiline_textbbox((card_x + self._scale(56), card_y + self._scale(34, axis="h")), head_wrapped, font=font_head, spacing=8)
        draw.multiline_text((card_x + self._scale(56), hb[3] + self._scale(18, axis="h")), sub_wrapped, fill=(225, 225, 225), font=font_body, spacing=6)
        self._draw_progress(draw, scene_number, scene_count)
        return overlay

    def _draw_scene_header(self, draw: ImageDraw.ImageDraw, scene: dict, scene_number: int, scene_count: int) -> None:
        """Draw a small scene chip and count."""
        label = str(scene.get("purpose") or scene.get("shot_type") or "scene").upper()
        label = label.replace("_", " ")
        chip_x = self._scale(72)
        chip_y = self._scale(86, axis="h")
        chip_w = max(self._scale(210), self._scale(52) + len(label) * self._scale(18))
        chip_h = self._scale(58, axis="h")
        draw.rounded_rectangle([chip_x, chip_y, chip_x + chip_w, chip_y + chip_h], radius=self._scale(28), fill=(18, 20, 28, 180))
        font = self._get_font(self._scale(24), bold=True)
        draw.text((chip_x + self._scale(22), chip_y + self._scale(15, axis="h")), label, fill=(255, 255, 255), font=font)

        count_text = f"{scene_number}/{max(scene_count, 1)}"
        count_font = self._get_font(self._scale(24), bold=True)
        bbox = draw.textbbox((0, 0), count_text, font=count_font)
        count_w = bbox[2] - bbox[0]
        cx = self.width - count_w - self._scale(74)
        draw.text((cx, chip_y + self._scale(15, axis="h")), count_text, fill=(255, 255, 255), font=count_font)

    def _draw_progress(self, draw: ImageDraw.ImageDraw, scene_number: int, scene_count: int) -> None:
        """Draw a simple progress indicator across scenes."""
        total = max(scene_count, 1)
        dot_size = self._scale(16)
        gap = self._scale(18)
        width = total * dot_size + (total - 1) * gap
        start_x = (self.width - width) // 2
        y = self.height - self._scale(110, axis="h")
        accent = self._hex_to_rgb(self.colors["accent"])
        for i in range(total):
            x = start_x + i * (dot_size + gap)
            fill = (*accent, 255) if i < scene_number else (255, 255, 255, 90)
            draw.ellipse([x, y, x + dot_size, y + dot_size], fill=fill)

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        """Truncate text cleanly for on-screen use."""
        text = " ".join(text.split())
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rsplit(" ", 1)[0] + "…"

    @staticmethod
    def _normalize_scene_assets(asset_value) -> list[str]:
        """Normalize single or multi-asset image inputs into a list of paths."""
        if isinstance(asset_value, str):
            return [asset_value]
        if isinstance(asset_value, list):
            return [str(item) for item in asset_value if str(item).strip()]
        return []

    def _animated_zoom_clip(self, image: Image.Image, duration: float, zoom_strength: float = 0.08):
        """Create a gentle zoom animation from a PIL image."""
        from moviepy import ImageClip

        base_clip = ImageClip(np.array(image), duration=duration)

        def make_frame(get_frame, t):
            frame = get_frame(t)
            progress = t / max(duration, 0.01)
            scale = 1.0 + zoom_strength * progress
            h, w = frame.shape[:2]
            new_h, new_w = int(h * scale), int(w * scale)
            resized = np.array(Image.fromarray(frame).resize((new_w, new_h), Image.LANCZOS))
            y_off = max(0, (new_h - h) // 2)
            x_off = max(0, (new_w - w) // 2)
            return resized[y_off:y_off + h, x_off:x_off + w]

        try:
            return base_clip.transform(make_frame)
        except Exception:
            return base_clip

    @staticmethod
    def _loop_audio_to_duration(audio_clip, duration: float, concatenate_audioclips):
        """Loop a music track until it covers the target duration."""
        if audio_clip.duration >= duration:
            return audio_clip
        loops = []
        partials = []
        remaining = duration
        while remaining > 0:
            if remaining >= audio_clip.duration:
                loops.append(audio_clip)
                remaining -= audio_clip.duration
            else:
                partial = audio_clip.subclipped(0, remaining)
                partials.append(partial)
                loops.append(partial)
                remaining = 0
        result = concatenate_audioclips(loops)
        for p in partials:
            try:
                p.close()
            except Exception:
                pass
        return result

    def _scale(self, value: int, axis: str = "min") -> int:
        """Scale a design value from the base 1080x1920 canvas."""
        if axis == "w":
            factor = self.width / 1080
        elif axis == "h":
            factor = self.height / 1920
        else:
            factor = min(self.width / 1080, self.height / 1920)
        return max(1, int(value * factor))

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

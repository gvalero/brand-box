"""
Video strategy and storyboard generation for social media content.

This module now treats a storyboard as the canonical intermediate artifact.
The legacy script dict is still produced so the current renderers can keep
working while the architecture evolves.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field

from brand_box.evaluators.creative import VideoEvaluator
from brand_box.models.artifacts import VideoStoryboard

logger = logging.getLogger(__name__)


@dataclass
class ContentFormat:
    """Definition of a video content format."""

    id: str
    name: str
    description: str
    script_prompt: str
    visual_style: str = "warm, engaging, professional"
    hook_angles: list[str] = field(
        default_factory=lambda: [
            "problem-first",
            "curiosity",
            "social-proof",
            "contrarian",
            "question",
            "stat-based",
        ]
    )
    max_duration_seconds: int = 45
    min_segments: int = 3
    max_segments: int = 6


BUILTIN_FORMATS: dict[str, ContentFormat] = {
    "teaser": ContentFormat(
        id="teaser",
        name="Product Teaser",
        description="Short, punchy intro to the product — builds curiosity",
        script_prompt=(
            "Create a 15-25 second teaser video script for social media.\n"
            "Structure: hook (3s) -> 2-3 quick benefit flashes -> CTA.\n"
            "Tone: exciting, fast-paced, visual-first."
        ),
        max_duration_seconds=25,
        min_segments=3,
        max_segments=4,
    ),
    "explainer": ContentFormat(
        id="explainer",
        name="How It Works",
        description="Step-by-step walkthrough of the product value proposition",
        script_prompt=(
            "Create a 30-45 second explainer video script.\n"
            "Structure: problem (5s) -> solution intro (5s) -> 3 key features (15-20s) -> CTA (5s).\n"
            "Tone: clear, friendly, educational."
        ),
        max_duration_seconds=45,
        min_segments=5,
        max_segments=6,
    ),
    "testimonial": ContentFormat(
        id="testimonial",
        name="Social Proof",
        description="Emotional parent/user reaction format",
        script_prompt=(
            "Create a 20-40 second testimonial-style video script.\n"
            "Structure: relatable moment -> discovery -> emotional payoff -> CTA.\n"
            "Tone: warm, authentic, emotional."
        ),
        max_duration_seconds=40,
        min_segments=4,
        max_segments=5,
    ),
    "fact": ContentFormat(
        id="fact",
        name="Did You Know?",
        description="Hook with surprising fact, tie to product benefit",
        script_prompt=(
            "Create a 15-30 second 'Did You Know?' video script.\n"
            "Structure: surprising stat/fact -> implication -> product tie-in -> CTA.\n"
            "Tone: informative, slightly surprising, authoritative."
        ),
        max_duration_seconds=30,
        min_segments=3,
        max_segments=5,
    ),
    "founder": ContentFormat(
        id="founder",
        name="Founder Story",
        description="Behind-the-scenes / why I built this",
        script_prompt=(
            "Create a 30-60 second founder story script.\n"
            "Structure: personal hook -> problem I noticed -> what I built -> vision -> CTA.\n"
            "Tone: personal, vulnerable, inspiring."
        ),
        max_duration_seconds=60,
        min_segments=4,
        max_segments=6,
    ),
}


class VideoStrategist:
    """Derive lightweight strategy inputs before storyboard generation."""

    def build_strategy(
        self,
        brand_name: str,
        concept: str,
        format_id: str,
        identity_context: str = "",
        hook_angle: str | None = None,
    ) -> dict:
        fmt = BUILTIN_FORMATS.get(format_id)
        if not fmt:
            raise ValueError(f"Unknown format: {format_id}. Available: {list(BUILTIN_FORMATS)}")

        if not hook_angle:
            import random

            hook_angle = random.choice(fmt.hook_angles)

        return {
            "format_id": format_id,
            "format_name": fmt.name,
            "format_description": fmt.description,
            "hook_angle": hook_angle,
            "platform": "tiktok/instagram reels",
            "brand_name": brand_name,
            "concept": concept,
            "identity_context": identity_context,
        }


class StoryboardGenerator:
    """Generate video storyboards from a brand concept using an LLM."""

    def __init__(self) -> None:
        self._openai_client = None
        self._gemini_client = None
        self._strategist = VideoStrategist()
        self._evaluator = VideoEvaluator()
        self._init_clients()

    def _init_clients(self) -> None:
        from brand_box.config import (
            AZURE_OPENAI_DEPLOYMENT_GPT,
            AZURE_OPENAI_ENDPOINT,
            AZURE_OPENAI_KEY,
            GEMINI_API_KEY,
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
                logger.info("Storyboard generator using Azure OpenAI")
                return
            except Exception as e:
                logger.warning("Azure OpenAI init failed: %s", e)

        if GEMINI_API_KEY:
            try:
                from google import genai

                self._gemini_client = genai.Client(api_key=GEMINI_API_KEY)
                logger.info("Storyboard generator using Gemini")
                return
            except Exception as e:
                logger.warning("Gemini init failed: %s", e)

        logger.warning("No LLM client available — storyboard generation will fail")

    def generate_storyboard(
        self,
        brand_name: str,
        concept: str,
        format_id: str = "teaser",
        hook_angle: str | None = None,
        identity_context: str = "",
        custom_prompt: str | None = None,
    ) -> VideoStoryboard:
        """Generate a typed storyboard artifact."""
        strategy = self._strategist.build_strategy(
            brand_name=brand_name,
            concept=concept,
            format_id=format_id,
            identity_context=identity_context,
            hook_angle=hook_angle,
        )
        fmt = BUILTIN_FORMATS[strategy["format_id"]]
        prompt = self._build_prompt(strategy, fmt, custom_prompt)

        if self._openai_client:
            text = self._call_openai(prompt)
        elif self._gemini_client:
            text = self._call_gemini(prompt)
        else:
            logger.warning("No LLM client configured — using fallback storyboard")
            return self._fallback_storyboard(
                brand_name=brand_name,
                platform=strategy["platform"],
                angle=strategy["hook_angle"],
                format_id=format_id,
                raw_text=f"{brand_name}: {concept}",
            )

        storyboard = self._parse_storyboard(
            text=text,
            brand_name=brand_name,
            platform=strategy["platform"],
            angle=strategy["hook_angle"],
            format_id=format_id,
        )
        return storyboard

    def generate_script(
        self,
        brand_name: str,
        concept: str,
        format_id: str = "teaser",
        hook_angle: str | None = None,
        identity_context: str = "",
        custom_prompt: str | None = None,
    ) -> dict:
        """Generate a legacy script dict from the canonical storyboard."""
        storyboard = self.generate_storyboard(
            brand_name=brand_name,
            concept=concept,
            format_id=format_id,
            hook_angle=hook_angle,
            identity_context=identity_context,
            custom_prompt=custom_prompt,
        )
        return self.storyboard_to_script(storyboard, format_id=format_id)

    def generate_variations(
        self,
        brand_name: str,
        concept: str,
        format_id: str = "teaser",
        count: int = 3,
        **kwargs,
    ) -> list[dict]:
        """Generate multiple legacy script variations with different hook angles."""
        storyboards = self.generate_storyboard_variants(
            brand_name=brand_name,
            concept=concept,
            format_id=format_id,
            count=count,
            **kwargs,
        )
        return [self.storyboard_to_script(storyboard, format_id=format_id) for storyboard in storyboards]

    def generate_storyboard_variants(
        self,
        brand_name: str,
        concept: str,
        format_id: str = "teaser",
        count: int = 3,
        **kwargs,
    ) -> list[VideoStoryboard]:
        """Generate and score multiple storyboards with different hook angles."""
        fmt = BUILTIN_FORMATS.get(format_id, BUILTIN_FORMATS["teaser"])
        angles = fmt.hook_angles[:count]
        while len(angles) < count:
            angles.append(angles[len(angles) % len(fmt.hook_angles)])

        storyboards = []
        for angle in angles:
            storyboard = self.generate_storyboard(
                brand_name=brand_name,
                concept=concept,
                format_id=format_id,
                hook_angle=angle,
                **kwargs,
            )
            storyboard.review = self._evaluator.evaluate(storyboard)
            storyboard.scores = dict(storyboard.review.subscores)
            storyboards.append(storyboard)
        return storyboards

    @staticmethod
    def select_best_storyboard(storyboards: list[VideoStoryboard]) -> VideoStoryboard:
        """Pick the highest-scoring storyboard."""
        if not storyboards:
            raise ValueError("No storyboards available")
        return max(storyboards, key=lambda storyboard: (storyboard.review.score, storyboard.hook))

    @staticmethod
    def list_formats() -> list[dict]:
        """Return available content formats."""
        return [
            {
                "id": f.id,
                "name": f.name,
                "description": f.description,
                "max_duration": f.max_duration_seconds,
            }
            for f in BUILTIN_FORMATS.values()
        ]

    def _build_prompt(
        self,
        strategy: dict,
        fmt: ContentFormat,
        custom_prompt: str | None,
    ) -> str:
        identity_part = (
            f"\nBrand identity: {strategy['identity_context']}"
            if strategy.get("identity_context")
            else ""
        )
        custom_part = f"\nAdditional instructions: {custom_prompt}" if custom_prompt else ""

        return f"""You are a social media video strategist and storyboard writer. Create a short-form video storyboard for:

Brand: {strategy['brand_name']}
Product: {strategy['concept']}{identity_part}

Format: {fmt.name} — {fmt.description}
{fmt.script_prompt}

Hook angle: {strategy['hook_angle']}
Platform: {strategy['platform']}
Duration: {fmt.max_duration_seconds} seconds max
Scenes: {fmt.min_segments}-{fmt.max_segments}{custom_part}

Return ONLY a JSON object with this exact structure:
{{
  "title": "Video title",
  "hook": "Opening hook text (first 3 seconds)",
  "voiceover": "Full narration text",
  "cta": "Call-to-action text",
  "hashtags": ["#hashtag1", "#hashtag2"],
  "total_duration_seconds": 30,
  "caption_plan": ["short caption 1", "short caption 2"],
  "scenes": [
    {{
      "scene_id": "s1",
      "index": 0,
      "purpose": "hook",
      "duration_seconds": 5,
      "shot_type": "close-up / product detail / illustration / kinetic text",
      "visual_description": "Detailed visual direction suitable for image generation",
      "visual_beats": [
        "Optional cutaway or insert description 1",
        "Optional cutaway or insert description 2"
      ],
      "motion_direction": "How the scene should feel or move",
      "on_screen_text": "Short on-screen text",
      "voiceover": "Narration for this scene"
    }}
  ]
}}

Important:
- Make the hook impossible to scroll past
- visual_description should be vivid and production-friendly
- visual_beats should describe alternate cutaways or inserts within the same scene
- motion_direction should help a renderer or editor understand pacing
- on_screen_text must be short and punchy
- CTA should drive action (follow, sign up, link in bio)"""

    def _call_openai(self, prompt: str) -> str:
        response = self._openai_client.chat.completions.create(
            model=self._openai_deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=1800,
        )
        return response.choices[0].message.content

    def _call_gemini(self, prompt: str) -> str:
        response = self._gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text

    @staticmethod
    def _parse_storyboard(
        text: str,
        brand_name: str,
        platform: str,
        angle: str,
        format_id: str,
    ) -> VideoStoryboard:
        """Parse the LLM response into a typed storyboard."""
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        data: dict | None = None
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse storyboard JSON: %s", e)

        if not isinstance(data, dict):
            return StoryboardGenerator._fallback_storyboard(
                brand_name=brand_name,
                platform=platform,
                angle=angle,
                format_id=format_id,
                raw_text=text,
            )

        scenes = []
        for i, scene in enumerate(data.get("scenes", [])):
            if not isinstance(scene, dict):
                continue
            scenes.append(
                {
                    "scene_id": scene.get("scene_id", f"s{i + 1}"),
                    "index": scene.get("index", i),
                    "purpose": scene.get("purpose", "segment"),
                    "duration_seconds": scene.get("duration_seconds", 5),
                    "shot_type": scene.get("shot_type", "illustration"),
                    "visual_description": scene.get("visual_description", "Abstract brand visual"),
                    "visual_beats": [
                        str(item) for item in scene.get("visual_beats", []) if str(item).strip()
                    ],
                    "motion_direction": scene.get("motion_direction", "gentle push-in"),
                    "on_screen_text": scene.get("on_screen_text", ""),
                    "voiceover": scene.get("voiceover", ""),
                }
            )

        voiceover = data.get("voiceover", " ".join(scene.get("voiceover", "") for scene in scenes))

        return VideoStoryboard(
            id=f"{format_id}-{uuid.uuid4().hex[:8]}",
            platform=platform,
            angle=angle,
            hook=data.get("hook", ""),
            scenes=scenes,
            voiceover=voiceover,
            caption_plan=[str(item) for item in data.get("caption_plan", []) if str(item).strip()],
            asset_refs={
                "title": data.get("title", "Generated Storyboard"),
                "cta": data.get("cta", "Link in bio!"),
                "hashtags": [str(tag) for tag in data.get("hashtags", [])],
                "format_id": format_id,
                "brand_name": brand_name,
                "total_duration_seconds": data.get(
                    "total_duration_seconds",
                    sum(scene.get("duration_seconds", 5) for scene in scenes),
                ),
            },
        )

    @staticmethod
    def _fallback_storyboard(
        brand_name: str,
        platform: str,
        angle: str,
        format_id: str,
        raw_text: str,
    ) -> VideoStoryboard:
        """Fallback storyboard used if the model returns malformed JSON."""
        scene_text = raw_text or f"Discover {brand_name}"
        return VideoStoryboard(
            id=f"{format_id}-{uuid.uuid4().hex[:8]}",
            platform=platform,
            angle=angle,
            hook=scene_text[:100],
            scenes=[
                {
                    "scene_id": "s1",
                    "index": 0,
                    "purpose": "hook",
                    "duration_seconds": 15,
                    "shot_type": "illustration",
                    "visual_description": "Abstract brand visual",
                    "visual_beats": [],
                    "motion_direction": "slow zoom in",
                    "on_screen_text": brand_name,
                    "voiceover": scene_text,
                }
            ],
            voiceover=scene_text,
            caption_plan=[brand_name],
            asset_refs={
                "title": "Generated Storyboard",
                "cta": "Link in bio!",
                "hashtags": [],
                "format_id": format_id,
                "brand_name": brand_name,
                "total_duration_seconds": 15,
            },
        )

    @staticmethod
    def storyboard_to_script(storyboard: VideoStoryboard, format_id: str | None = None) -> dict:
        """Convert a storyboard artifact into the legacy script shape."""
        segments = []
        for i, scene in enumerate(storyboard.scenes):
            segments.append(
                {
                    "index": scene.get("index", i),
                    "text": scene.get("voiceover", ""),
                    "visual_description": scene.get("visual_description", "Abstract brand visual"),
                    "visual_beats": scene.get("visual_beats", []),
                    "duration_seconds": scene.get("duration_seconds", 5),
                    "on_screen_text": scene.get("on_screen_text", ""),
                    "motion_direction": scene.get("motion_direction", ""),
                    "shot_type": scene.get("shot_type", ""),
                }
            )

        title = storyboard.asset_refs.get("title", "Generated Script")
        cta = storyboard.asset_refs.get("cta", "Link in bio!")
        hashtags = storyboard.asset_refs.get("hashtags", [])
        total_duration = storyboard.asset_refs.get(
            "total_duration_seconds",
            sum(segment.get("duration_seconds", 5) for segment in segments),
        )

        return {
            "title": title,
            "hook": storyboard.hook,
            "segments": segments,
            "cta": cta,
            "hashtags": hashtags,
            "total_duration_seconds": total_duration,
            "narration_text": storyboard.voiceover or " ".join(seg.get("text", "") for seg in segments),
            "format_id": format_id or storyboard.asset_refs.get("format_id", ""),
            "hook_angle": storyboard.angle,
        }


ScriptGenerator = StoryboardGenerator

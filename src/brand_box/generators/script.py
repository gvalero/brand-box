"""
Script generator for social media video content.

Uses Azure OpenAI GPT-4o or Gemini to generate structured video scripts
with segments, visual descriptions, and narration text.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ContentFormat:
    """Definition of a video content format."""
    id: str
    name: str
    description: str
    script_prompt: str
    visual_style: str = "warm, engaging, professional"
    hook_angles: list[str] = field(default_factory=lambda: [
        "problem-first", "curiosity", "social-proof", "contrarian", "question", "stat-based",
    ])
    max_duration_seconds: int = 45
    min_segments: int = 3
    max_segments: int = 6


# Built-in formats (users can add custom ones via brand.json)
BUILTIN_FORMATS: dict[str, ContentFormat] = {
    "teaser": ContentFormat(
        id="teaser",
        name="Product Teaser",
        description="Short, punchy intro to the product — builds curiosity",
        script_prompt=(
            "Create a 15-25 second teaser video script for social media.\n"
            "Structure: hook (3s) → 2-3 quick benefit flashes → CTA.\n"
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
            "Structure: problem (5s) → solution intro (5s) → 3 key features (15-20s) → CTA (5s).\n"
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
            "Structure: relatable moment → discovery → emotional payoff → CTA.\n"
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
            "Structure: surprising stat/fact → implication → product tie-in → CTA.\n"
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
            "Structure: personal hook → problem I noticed → what I built → vision → CTA.\n"
            "Tone: personal, vulnerable, inspiring."
        ),
        max_duration_seconds=60,
        min_segments=4,
        max_segments=6,
    ),
}


class ScriptGenerator:
    """Generate video scripts from a brand concept using LLM."""

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
                logger.info("Script generator using Azure OpenAI")
                return
            except Exception as e:
                logger.warning("Azure OpenAI init failed: %s", e)

        if GEMINI_API_KEY:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=GEMINI_API_KEY)
                logger.info("Script generator using Gemini")
                return
            except Exception as e:
                logger.warning("Gemini init failed: %s", e)

        logger.warning("No LLM client available — script generation will fail")

    def generate_script(
        self,
        brand_name: str,
        concept: str,
        format_id: str = "teaser",
        hook_angle: str | None = None,
        identity_context: str = "",
        custom_prompt: str | None = None,
    ) -> dict:
        """Generate a single video script.

        Returns a dict with:
            title, format_id, hook_angle, hook, segments, cta, hashtags,
            total_duration_seconds, narration_text
        """
        fmt = BUILTIN_FORMATS.get(format_id)
        if not fmt:
            raise ValueError(f"Unknown format: {format_id}. Available: {list(BUILTIN_FORMATS)}")

        if not hook_angle:
            import random
            hook_angle = random.choice(fmt.hook_angles)

        prompt = self._build_prompt(brand_name, concept, fmt, hook_angle, identity_context, custom_prompt)

        if self._openai_client:
            text = self._call_openai(prompt)
        elif self._gemini_client:
            text = self._call_gemini(prompt)
        else:
            raise RuntimeError("No LLM client configured.")

        script = self._parse_script(text)
        script["format_id"] = format_id
        script["hook_angle"] = hook_angle
        return script

    def generate_variations(
        self,
        brand_name: str,
        concept: str,
        format_id: str = "teaser",
        count: int = 3,
        **kwargs,
    ) -> list[dict]:
        """Generate multiple script variations with different hook angles."""
        fmt = BUILTIN_FORMATS.get(format_id, BUILTIN_FORMATS["teaser"])
        angles = fmt.hook_angles[:count]
        while len(angles) < count:
            angles.append(angles[len(angles) % len(fmt.hook_angles)])

        scripts = []
        for angle in angles:
            script = self.generate_script(
                brand_name=brand_name,
                concept=concept,
                format_id=format_id,
                hook_angle=angle,
                **kwargs,
            )
            scripts.append(script)
        return scripts

    @staticmethod
    def list_formats() -> list[dict]:
        """Return available content formats."""
        return [
            {"id": f.id, "name": f.name, "description": f.description, "max_duration": f.max_duration_seconds}
            for f in BUILTIN_FORMATS.values()
        ]

    def _build_prompt(
        self,
        brand_name: str,
        concept: str,
        fmt: ContentFormat,
        hook_angle: str,
        identity_context: str,
        custom_prompt: str | None,
    ) -> str:
        identity_part = f"\nBrand identity: {identity_context}" if identity_context else ""
        custom_part = f"\nAdditional instructions: {custom_prompt}" if custom_prompt else ""

        return f"""You are a social media video scriptwriter. Create a video script for:

Brand: {brand_name}
Product: {concept}{identity_part}

Format: {fmt.name} — {fmt.description}
{fmt.script_prompt}

Hook angle: {hook_angle}
Duration: {fmt.max_duration_seconds} seconds max
Segments: {fmt.min_segments}-{fmt.max_segments}{custom_part}

Return ONLY a JSON object with this exact structure:
{{
  "title": "Video title",
  "hook": "Opening hook text (first 3 seconds)",
  "segments": [
    {{
      "index": 0,
      "text": "Narration text for this segment",
      "visual_description": "Detailed visual description for AI image generation",
      "duration_seconds": 5
    }}
  ],
  "cta": "Call-to-action text",
  "hashtags": ["#hashtag1", "#hashtag2"],
  "total_duration_seconds": 30,
  "narration_text": "Full narration text (all segments combined)"
}}

Important:
- visual_description should be vivid, specific, and suitable for AI image generation
- Each segment's text is what the narrator says
- Make the hook impossible to scroll past
- CTA should drive action (follow, sign up, link in bio)"""

    def _call_openai(self, prompt: str) -> str:
        response = self._openai_client.chat.completions.create(
            model=self._openai_deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=1500,
        )
        return response.choices[0].message.content

    def _call_gemini(self, prompt: str) -> str:
        response = self._gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text

    @staticmethod
    def _parse_script(text: str) -> dict:
        """Parse LLM response into a script dict."""
        text = text.strip()
        # Strip markdown code fences
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                script = json.loads(match.group())
                # Ensure required fields
                script.setdefault("title", "Untitled")
                script.setdefault("hook", "")
                script.setdefault("segments", [])
                script.setdefault("cta", "Link in bio!")
                script.setdefault("hashtags", [])
                script.setdefault("total_duration_seconds", sum(
                    s.get("duration_seconds", 5) for s in script["segments"]
                ))
                script.setdefault("narration_text", " ".join(
                    s.get("text", "") for s in script["segments"]
                ))
                return script
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse script JSON: %s", e)

        # Fallback: return a minimal structure
        return {
            "title": "Generated Script",
            "hook": text[:100] if text else "",
            "segments": [{"index": 0, "text": text, "visual_description": "Abstract brand visual", "duration_seconds": 15}],
            "cta": "Link in bio!",
            "hashtags": [],
            "total_duration_seconds": 15,
            "narration_text": text,
        }

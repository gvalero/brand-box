"""
Brand identity generator.

Generates color palette, typography, tone of voice, and tagline from
a concept description and optional brand name.
"""

from __future__ import annotations

import json
import logging
import re

from brand_box.project import BrandIdentity

logger = logging.getLogger(__name__)


class IdentityGenerator:
    """Generate a complete brand identity using an LLM."""

    def __init__(self) -> None:
        self._openai_client = None
        self._gemini_client = None
        self._init_clients()

    def _init_clients(self) -> None:
        from brand_box.config import (
            AZURE_OPENAI_ENDPOINT,
            AZURE_OPENAI_KEY,
            AZURE_OPENAI_DEPLOYMENT_GPT,
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

    def generate(self, concept: str, name: str = "") -> BrandIdentity:
        """Generate a brand identity for the given concept."""
        prompt = self._build_prompt(concept, name)

        if self._openai_client:
            text = self._call_openai(prompt)
        elif self._gemini_client:
            text = self._call_gemini(prompt)
        else:
            raise RuntimeError("No LLM client configured.")

        return self._parse_response(text)

    def _build_prompt(self, concept: str, name: str) -> str:
        name_part = f' The brand name is "{name}".' if name else ""
        return f"""You are a brand identity designer. Create a complete brand identity for:

"{concept}"{name_part}

Return a JSON object with exactly these fields:
{{
  "primary_color": "#hex",
  "secondary_color": "#hex",
  "accent_color": "#hex",
  "background_color": "#hex",
  "text_color": "#hex",
  "font_heading": "Font Name",
  "font_body": "Font Name",
  "tone": "3-4 adjectives describing the brand voice",
  "tagline": "A short, memorable tagline"
}}

Guidelines:
- Colors should feel cohesive and appropriate for the product
- Prefer web-safe fonts or Google Fonts
- The tagline should be under 8 words
- Consider the target audience and emotional impact

Return ONLY the JSON object, no explanation."""

    def _call_openai(self, prompt: str) -> str:
        response = self._openai_client.chat.completions.create(
            model=self._openai_deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500,
        )
        return response.choices[0].message.content

    def _call_gemini(self, prompt: str) -> str:
        response = self._gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text

    @staticmethod
    def _parse_response(text: str) -> BrandIdentity:
        """Parse LLM response into a BrandIdentity."""
        text = text.strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return BrandIdentity(**{k: v for k, v in data.items() if hasattr(BrandIdentity, k)})
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Failed to parse identity JSON: %s", e)

        return BrandIdentity(tone="warm, professional, approachable")

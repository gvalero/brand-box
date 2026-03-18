"""
Brand name generator.

Uses Azure OpenAI GPT-4o (or Gemini) to brainstorm brand name candidates
from a concept description, then optionally validates availability.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class NameGenerator:
    """Generate brand name candidates from a concept."""

    def __init__(self) -> None:
        self._openai_client = None
        self._gemini_client = None
        self._init_clients()

    def _init_clients(self) -> None:
        """Try Azure OpenAI first (GPT-4o), then Gemini."""
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
                logger.info("Name generator using Azure OpenAI (GPT-4o)")
                return
            except Exception as e:
                logger.warning("Azure OpenAI init failed: %s", e)

        if GEMINI_API_KEY:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=GEMINI_API_KEY)
                logger.info("Name generator using Gemini")
                return
            except Exception as e:
                logger.warning("Gemini init failed: %s", e)

        logger.warning("No LLM client available — name generation will fail")

    def generate(self, concept: str, count: int = 10) -> list[str]:
        """Generate *count* name candidates for the given concept."""
        prompt = self._build_prompt(concept, count)

        if self._openai_client:
            return self._generate_openai(prompt)
        elif self._gemini_client:
            return self._generate_gemini(prompt)
        else:
            raise RuntimeError("No LLM client configured. Set AZURE_OPENAI_KEY or GEMINI_API_KEY.")

    def _build_prompt(self, concept: str, count: int) -> str:
        return f"""You are a branding expert. Generate {count} creative brand name candidates for the following concept:

"{concept}"

Requirements:
- Short (1-3 words max)
- Memorable and easy to spell
- Available as a .com domain (check plausibility)
- Unique — not an existing well-known brand
- Evocative of the product's purpose

Return ONLY a JSON array of strings. No explanation, no numbering.
Example: ["BrandOne", "BrandTwo", "BrandThree"]"""

    def _generate_openai(self, prompt: str) -> list[str]:
        response = self._openai_client.chat.completions.create(
            model=self._openai_deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=500,
        )
        return self._parse_response(response.choices[0].message.content)

    def _generate_gemini(self, prompt: str) -> list[str]:
        response = self._gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return self._parse_response(response.text)

    @staticmethod
    def _parse_response(text: str) -> list[str]:
        """Extract a JSON array of strings from the LLM response."""
        text = text.strip()
        # Find JSON array in response
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                names = json.loads(match.group())
                return [str(n).strip() for n in names if isinstance(n, str) and n.strip()]
            except json.JSONDecodeError:
                pass
        # Fallback: split by newlines, strip numbering
        lines = [re.sub(r"^\d+[\.\)]\s*", "", line).strip() for line in text.splitlines()]
        return [l for l in lines if l and not l.startswith("[")]

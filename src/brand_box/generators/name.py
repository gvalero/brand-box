"""
Brand name generator.

Uses Azure OpenAI GPT-4o (or Gemini) to brainstorm brand name candidates
from a concept description, then optionally validates availability.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from brand_box.models.artifacts import NameCandidate, StageReview

logger = logging.getLogger(__name__)


class NameGenerator:
    """Generate brand name candidates from a concept."""

    def __init__(self) -> None:
        self._openai_client = None
        self._gemini_client = None
        self._init_clients()

    # ------------------------------------------------------------------
    # Client initialisation
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, concept: str, count: int = 10) -> list[str]:
        """Return *count* name strings (backward-compatible wrapper)."""
        candidates = self.generate_rich(concept, count)
        return [c.name for c in candidates]

    def generate_rich(self, concept: str, count: int = 10) -> list[NameCandidate]:
        """Generate *count* structured :class:`NameCandidate` objects."""
        prompt = self._build_rich_prompt(concept, count)
        raw = self._call_llm(prompt)
        return self._parse_rich_response(raw)

    def generate_variants(
        self, concept: str, count: int = 10
    ) -> list[NameCandidate]:
        """Generate *count* candidates with scoring placeholders.

        Each candidate receives an empty :class:`StageReview` — an evaluator
        can be wired in later to populate the review and scores fields.
        """
        candidates = self.generate_rich(concept, count)
        for candidate in candidates:
            candidate.review = StageReview(stage="name")
        return candidates

    # ------------------------------------------------------------------
    # LLM dispatch
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str) -> str:
        """Route the prompt to whichever LLM backend is available."""
        if self._openai_client:
            return self._call_openai(prompt)
        elif self._gemini_client:
            return self._call_gemini(prompt)
        raise RuntimeError(
            "No LLM client configured. Set AZURE_OPENAI_KEY or GEMINI_API_KEY."
        )

    def _call_openai(self, prompt: str) -> str:
        response = self._openai_client.chat.completions.create(
            model=self._openai_deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=2000,
        )
        return response.choices[0].message.content

    def _call_gemini(self, prompt: str) -> str:
        response = self._gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_rich_prompt(self, concept: str, count: int) -> str:
        return (
            f"You are a branding expert. Generate {count} creative brand name "
            f"candidates for the following concept:\n\n"
            f'"{concept}"\n\n'
            "Requirements:\n"
            "- Short (1-3 words max)\n"
            "- Memorable and easy to spell\n"
            "- Available as a .com domain (check plausibility)\n"
            "- Unique — not an existing well-known brand\n"
            "- Evocative of the product's purpose\n\n"
            "Return ONLY a JSON array of objects. No explanation, no numbering.\n"
            "Each object must have these keys:\n"
            '  "name": string — the brand name\n'
            '  "rationale": string — one-sentence explanation of why this name works\n'
            '  "tone": list of strings — 2-4 adjectives describing the name\'s feel\n'
            '  "risks": list of strings — potential issues (trademark, spelling, etc.)\n'
            '  "domain_notes": string — plausible .com availability note\n\n'
            "Example:\n"
            "[{\n"
            '  "name": "Lumino",\n'
            '  "rationale": "Evokes light and clarity, fitting for a productivity tool.",\n'
            '  "tone": ["modern", "clean", "energetic"],\n'
            '  "risks": ["Similar to Luminos, a lighting brand"],\n'
            '  "domain_notes": "lumino.com likely taken; luminoapp.com plausible"\n'
            "}]"
        )

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_rich_response(self, text: str) -> list[NameCandidate]:
        """Parse structured or plain JSON into :class:`NameCandidate` objects."""
        text = text.strip()
        # Strip markdown code-fence wrappers
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                items: list[Any] = json.loads(match.group())
                return self._items_to_candidates(items)
            except json.JSONDecodeError:
                logger.warning("JSON decode failed; falling back to line parsing")

        # Fallback: split by newlines, strip numbering
        lines = [
            re.sub(r"^\d+[.\)]\s*", "", line).strip()
            for line in text.splitlines()
        ]
        names = [ln for ln in lines if ln and not ln.startswith("[")]
        return [NameCandidate(name=n) for n in names]

    @staticmethod
    def _items_to_candidates(items: list[Any]) -> list[NameCandidate]:
        """Convert a parsed JSON array to a list of :class:`NameCandidate`.

        Handles both structured objects and plain string entries.
        """
        candidates: list[NameCandidate] = []
        for item in items:
            if isinstance(item, dict):
                candidates.append(
                    NameCandidate(
                        name=str(item.get("name", "")).strip(),
                        rationale=str(item.get("rationale", "")).strip(),
                        tone=[str(t) for t in item.get("tone", []) if t],
                        risks=[str(r) for r in item.get("risks", []) if r],
                        domain_notes=str(item.get("domain_notes", "")).strip(),
                    )
                )
            elif isinstance(item, str) and item.strip():
                candidates.append(NameCandidate(name=item.strip()))
        return [c for c in candidates if c.name]

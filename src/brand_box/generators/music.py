"""
Music planning and track selection for video renders.

This is intentionally lightweight: it creates a structured music plan and can
optionally attach a user-supplied track or choose from a local folder.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from brand_box.models.artifacts import MusicPlan, StageReview


class MusicPlanner:
    """Plan or select background music for a video."""

    def plan(
        self,
        brand_name: str,
        concept: str,
        format_id: str,
        storyboard: dict | None = None,
        music_path: str | None = None,
        music_dir: str | None = None,
        profile: str = "reel",
    ) -> MusicPlan:
        """Create a music plan, optionally attaching a real track path."""
        mood, tempo, instrumentation = self._derive_direction(concept, format_id)
        chosen_path = ""
        source = "planned"

        if music_path:
            candidate = Path(music_path).expanduser()
            if candidate.is_file():
                chosen_path = str(candidate.resolve())
                source = "user"
            else:
                candidate = (Path.cwd() / music_path).resolve()
                if candidate.is_file():
                    chosen_path = str(candidate)
                    source = "user"
        elif music_dir:
            chosen = self._pick_from_dir(music_dir)
            if chosen:
                chosen_path = chosen
                source = "library"

        score = 0.78 if chosen_path else 0.62
        issues = [] if chosen_path else ["No music track selected yet; using plan only."]

        return MusicPlan(
            id=f"music-{uuid.uuid4().hex[:8]}",
            platform=profile,
            format_id=format_id,
            mood=mood,
            tempo=tempo,
            instrumentation=instrumentation,
            prompt=self._build_prompt(brand_name, concept, mood, tempo, instrumentation, storyboard),
            track_path=chosen_path,
            source=source,
            scores={"fit": round(score, 2)},
            review=StageReview(
                stage="music",
                score=round(score, 2),
                subscores={"fit": round(score, 2)},
                issues=issues,
                recommendation="approve" if chosen_path else "revise",
            ),
        )

    @staticmethod
    def _derive_direction(concept: str, format_id: str) -> tuple[str, str, list[str]]:
        concept_l = concept.lower()
        if any(word in concept_l for word in ("story", "book", "child", "kids", "family")):
            mood = "magical, warm, uplifting"
            tempo = "mid-tempo"
            instrumentation = ["soft bells", "light strings", "gentle marimba", "subtle percussion"]
        elif format_id == "founder":
            mood = "emotional, intimate, hopeful"
            tempo = "slow"
            instrumentation = ["piano", "warm pads", "soft pulse"]
        elif format_id == "teaser":
            mood = "bright, energetic, modern"
            tempo = "upbeat"
            instrumentation = ["light synths", "clean percussion", "sub bass", "claps"]
        else:
            mood = "clear, optimistic, polished"
            tempo = "mid-tempo"
            instrumentation = ["soft synths", "perc", "pads"]
        return mood, tempo, instrumentation

    @staticmethod
    def _build_prompt(
        brand_name: str,
        concept: str,
        mood: str,
        tempo: str,
        instrumentation: list[str],
        storyboard: dict | None,
    ) -> str:
        hook = storyboard.get("hook", "") if storyboard else ""
        return (
            f"Create a royalty-safe background music cue for {brand_name}. "
            f"Concept: {concept}. Mood: {mood}. Tempo: {tempo}. "
            f"Instrumentation: {', '.join(instrumentation)}. "
            f"Support voiceover without overpowering it. Hook context: {hook}"
        )

    @staticmethod
    def _pick_from_dir(music_dir: str) -> str:
        root = Path(music_dir)
        if not root.is_dir():
            return ""
        for suffix in ("*.mp3", "*.wav", "*.m4a", "*.aac"):
            match = next(root.glob(suffix), None)
            if match and match.is_file():
                return str(match.resolve())
        return ""

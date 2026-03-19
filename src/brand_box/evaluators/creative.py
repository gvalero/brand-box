"""
Lightweight evaluators for creative artifacts.

These evaluators are intentionally heuristic-first so they work even when no
LLM provider is configured. They produce consistent scores and review metadata
that can later be replaced or augmented with model-based critics.
"""

from __future__ import annotations

from pathlib import Path

from brand_box.models.artifacts import (
    BrandDirection,
    LogoConcept,
    NameCandidate,
    StageReview,
    VideoStoryboard,
    WebsiteSpec,
)

_GENERIC_WORDS = frozenset(
    {"app", "hub", "tech", "pro", "digital", "smart", "cloud", "net", "web", "online"}
)


class NameEvaluator:
    """Score a NameCandidate for memorability, brand fit, and domain viability."""

    def evaluate(self, candidate: NameCandidate) -> StageReview:
        issues: list[str] = []
        name = candidate.name.strip()
        words = name.split()
        word_count = len(words)
        char_count = len(name)

        # --- memorability ---
        memorability = 0.3
        if 1 <= word_count <= 2 and char_count <= 12:
            memorability += 0.4
        elif word_count <= 2:
            memorability += 0.2
        if word_count > 3:
            memorability -= 0.1
            issues.append("Name has too many words.")
        if char_count > 20:
            memorability -= 0.1
            issues.append("Name is very long (>20 chars).")
        # Alliteration bonus
        lower_words = [w.lower() for w in words]
        if len(lower_words) >= 2 and lower_words[0][0] == lower_words[1][0]:
            memorability += 0.15
        # Rhyme bonus (simplistic: last 2 chars match)
        if (
            len(lower_words) >= 2
            and len(lower_words[0]) >= 2
            and len(lower_words[-1]) >= 2
            and lower_words[0][-2:] == lower_words[-1][-2:]
        ):
            memorability += 0.1
        memorability = max(0.0, min(1.0, memorability))

        # --- brand_fit ---
        brand_fit = 0.3
        if candidate.rationale:
            brand_fit += 0.25
        if candidate.tone:
            brand_fit += 0.2
        if candidate.risks:
            brand_fit -= 0.15
            issues.append("Risks flagged for this name.")
        brand_fit = max(0.0, min(1.0, brand_fit))

        # --- domain_viability ---
        if candidate.domain_notes:
            notes_lower = candidate.domain_notes.lower()
            if "available" in notes_lower:
                domain_viability = 0.9
            elif "taken" in notes_lower or "unavailable" in notes_lower:
                domain_viability = 0.2
                issues.append("Domain appears unavailable.")
            else:
                domain_viability = 0.5
        else:
            domain_viability = 0.5

        # --- distinctiveness ---
        distinctiveness = 0.8
        for w in lower_words:
            if w in _GENERIC_WORDS:
                distinctiveness -= 0.2
                issues.append(f"Name contains generic word '{w}'.")
        distinctiveness = max(0.0, min(1.0, distinctiveness))

        subscores = {
            "memorability": round(memorability, 2),
            "brand_fit": round(brand_fit, 2),
            "domain_viability": round(domain_viability, 2),
            "distinctiveness": round(distinctiveness, 2),
        }
        score = round(sum(subscores.values()) / len(subscores), 2)
        recommendation = "approve" if score >= 0.75 else "revise"

        return StageReview(
            stage="name",
            score=score,
            subscores=subscores,
            issues=issues,
            recommendation=recommendation,
        )


class IdentityEvaluator:
    """Score a BrandDirection for completeness and coherence."""

    _FIELDS = (
        "positioning",
        "audience",
        "personality",
        "messaging_pillars",
        "tagline_options",
        "palette",
        "typography",
        "imagery_keywords",
    )

    def evaluate(self, direction: BrandDirection) -> StageReview:
        issues: list[str] = []

        # --- completeness ---
        filled = sum(1 for f in self._FIELDS if getattr(direction, f, None))
        completeness = filled / len(self._FIELDS)
        if completeness < 0.5:
            issues.append("Brand direction is missing several fields.")

        # --- coherence ---
        coherence = 0.3
        if len(direction.personality) >= 3:
            coherence += 0.35
        elif direction.personality:
            coherence += 0.15
        else:
            issues.append("No personality traits defined.")
        if len(direction.messaging_pillars) >= 2:
            coherence += 0.3
        elif direction.messaging_pillars:
            coherence += 0.15
        else:
            issues.append("No messaging pillars defined.")
        coherence = min(1.0, coherence)

        # --- visual_system ---
        visual_system = 0.2
        palette = direction.palette
        if palette.get("primary"):
            visual_system += 0.2
        if palette.get("secondary"):
            visual_system += 0.15
        if palette.get("accent"):
            visual_system += 0.15
        if not palette:
            issues.append("No colour palette defined.")
        typo = direction.typography
        if typo.get("heading"):
            visual_system += 0.15
        if typo.get("body"):
            visual_system += 0.15
        if not typo:
            issues.append("No typography defined.")
        visual_system = min(1.0, visual_system)

        # --- brand_clarity ---
        brand_clarity = 0.2
        pos = direction.positioning.strip()
        if pos:
            brand_clarity += 0.2
            if len(pos) > 20:
                brand_clarity += 0.2
            else:
                issues.append("Positioning statement is too brief.")
        else:
            issues.append("Missing positioning statement.")
        aud = direction.audience.strip()
        if aud:
            brand_clarity += 0.15
            if aud.lower() not in {"everyone", "all", "general"}:
                brand_clarity += 0.15
            else:
                issues.append("Audience is too broad.")
        else:
            issues.append("Missing audience definition.")
        brand_clarity = min(1.0, brand_clarity)

        subscores = {
            "completeness": round(completeness, 2),
            "coherence": round(coherence, 2),
            "visual_system": round(visual_system, 2),
            "brand_clarity": round(brand_clarity, 2),
        }
        score = round(sum(subscores.values()) / len(subscores), 2)
        recommendation = "approve" if score >= 0.75 else "revise"

        return StageReview(
            stage="identity",
            score=score,
            subscores=subscores,
            issues=issues,
            recommendation=recommendation,
        )


class LogoEvaluator:
    """Score a LogoConcept for completeness and style diversity."""

    def evaluate(self, concept: LogoConcept) -> StageReview:
        issues: list[str] = []

        # --- concept_clarity ---
        concept_clarity = 0.2
        style = concept.style.strip()
        if style and len(style) > 10:
            concept_clarity += 0.35
        elif style:
            concept_clarity += 0.15
            issues.append("Style description is very short.")
        else:
            issues.append("Missing style description.")
        if concept.rationale:
            concept_clarity += 0.3
        else:
            issues.append("Missing design rationale.")
        concept_clarity = min(1.0, concept_clarity)

        # --- prompt_quality ---
        prompt = concept.prompt.strip()
        prompt_quality = 0.2
        if len(prompt) > 30:
            prompt_quality += 0.35
        elif prompt:
            prompt_quality += 0.15
            issues.append("Prompt is too short to guide generation well.")
        else:
            issues.append("Missing generation prompt.")
        if "no text" in prompt.lower():
            prompt_quality += 0.25
        prompt_quality = min(1.0, prompt_quality)

        # --- asset_completeness ---
        asset_completeness = 0.0
        if concept.asset_paths:
            existing = [p for p in concept.asset_paths if Path(p).is_file()]
            asset_completeness = len(existing) / len(concept.asset_paths)
            missing = len(concept.asset_paths) - len(existing)
            if missing:
                issues.append(f"{missing} asset(s) missing from disk.")
        else:
            issues.append("No asset paths defined.")

        # --- metadata ---
        metadata = 0.2
        if concept.id:
            metadata += 0.4
        else:
            issues.append("Logo concept has no id.")
        if concept.scores:
            metadata += 0.4
        metadata = min(1.0, metadata)

        subscores = {
            "concept_clarity": round(concept_clarity, 2),
            "prompt_quality": round(prompt_quality, 2),
            "asset_completeness": round(asset_completeness, 2),
            "metadata": round(metadata, 2),
        }
        score = round(sum(subscores.values()) / len(subscores), 2)
        recommendation = "approve" if score >= 0.75 else "revise"

        return StageReview(
            stage="logo",
            score=score,
            subscores=subscores,
            issues=issues,
            recommendation=recommendation,
        )


class WebsiteEvaluator:
    """Score a WebsiteSpec for clarity, conversion, and brand fit."""

    def evaluate(self, spec: WebsiteSpec) -> StageReview:
        copy = spec.copy or {}
        issues: list[str] = []

        hero = str(copy.get("hero_headline", "")).strip()
        subheadline = str(copy.get("hero_subheadline", "")).strip()
        features = copy.get("features", [])
        steps = copy.get("how_it_works", [])
        testimonials = copy.get("testimonials", [])

        clarity = 0.45
        if hero:
            clarity += 0.2
        else:
            issues.append("Missing hero headline.")
        if subheadline:
            clarity += 0.15
        else:
            issues.append("Missing hero subheadline.")
        if steps:
            clarity += 0.1
        else:
            issues.append("Missing process explanation.")
        clarity = min(1.0, clarity)

        conversion = 0.4
        if spec.conversion_goal:
            conversion += 0.2
        if copy.get("cta_headline"):
            conversion += 0.15
        else:
            issues.append("Missing CTA headline.")
        if copy.get("cta_button_text"):
            conversion += 0.1
        else:
            issues.append("Missing CTA button text.")
        if testimonials:
            conversion += 0.05
        conversion = min(1.0, conversion)

        brand_fit = 0.4
        if spec.visual_direction:
            brand_fit += 0.2
        if spec.audience:
            brand_fit += 0.1
        tone = str(spec.design_tokens.get("tone", "")).strip()
        if tone:
            brand_fit += 0.1
        if len(features) >= 3:
            brand_fit += 0.1
        else:
            issues.append("Feature set is thin.")
        if "generic" in hero.lower() or hero.lower().startswith("welcome to"):
            issues.append("Hero headline still feels generic.")
            brand_fit -= 0.1
        brand_fit = max(0.0, min(1.0, brand_fit))

        originality = 0.45
        if spec.visual_direction and ":" in spec.visual_direction:
            originality += 0.15
        if hero and len(hero.split()) <= 10:
            originality += 0.1
        if features and len({f.get("title", "") for f in features if isinstance(f, dict)}) >= 3:
            originality += 0.1
        if testimonials:
            originality -= 0.05
            issues.append("Testimonials are synthetic and should be treated carefully.")
        originality = max(0.0, min(1.0, originality))

        subscores = {
            "clarity": round(clarity, 2),
            "conversion": round(conversion, 2),
            "brand_fit": round(brand_fit, 2),
            "originality": round(originality, 2),
        }
        score = round(sum(subscores.values()) / len(subscores), 2)
        recommendation = "approve" if score >= 0.75 else "revise"

        return StageReview(
            stage="website",
            score=score,
            subscores=subscores,
            issues=issues,
            recommendation=recommendation,
        )


class VideoEvaluator:
    """Score a VideoStoryboard for hook strength, pacing, and production fit."""

    def evaluate(self, storyboard: VideoStoryboard) -> StageReview:
        issues: list[str] = []
        scenes = storyboard.scenes
        total_duration = storyboard.asset_refs.get(
            "total_duration_seconds",
            sum(scene.get("duration_seconds", 5) for scene in scenes),
        )

        hook_strength = 0.4
        if storyboard.hook:
            hook_strength += 0.25
            if len(storyboard.hook.split()) <= 14:
                hook_strength += 0.1
        else:
            issues.append("Missing explicit hook.")
        if storyboard.angle:
            hook_strength += 0.1
        hook_strength = min(1.0, hook_strength)

        pacing = 0.45
        if 15 <= total_duration <= 45:
            pacing += 0.2
        else:
            issues.append("Duration may not fit short-form norms.")
        if 3 <= len(scenes) <= 6:
            pacing += 0.2
        else:
            issues.append("Scene count is outside the usual short-form range.")
        if any(scene.get("motion_direction") for scene in scenes):
            pacing += 0.05
        pacing = min(1.0, pacing)

        visual_clarity = 0.4
        if all(scene.get("visual_description") for scene in scenes):
            visual_clarity += 0.25
        else:
            issues.append("Some scenes are missing visual direction.")
        if any(scene.get("shot_type") for scene in scenes):
            visual_clarity += 0.15
        if any(scene.get("on_screen_text") for scene in scenes):
            visual_clarity += 0.1
        visual_clarity = min(1.0, visual_clarity)

        brand_fit = 0.45
        if storyboard.asset_refs.get("brand_name"):
            brand_fit += 0.1
        if storyboard.voiceover:
            brand_fit += 0.15
        if storyboard.caption_plan:
            brand_fit += 0.1
        if not scenes:
            issues.append("Storyboard has no scenes.")
            brand_fit -= 0.2
        brand_fit = max(0.0, min(1.0, brand_fit))

        subscores = {
            "hook_strength": round(hook_strength, 2),
            "pacing": round(pacing, 2),
            "visual_clarity": round(visual_clarity, 2),
            "brand_fit": round(brand_fit, 2),
        }
        score = round(sum(subscores.values()) / len(subscores), 2)
        recommendation = "approve" if score >= 0.75 else "revise"

        return StageReview(
            stage="video",
            score=score,
            subscores=subscores,
            issues=issues,
            recommendation=recommendation,
        )

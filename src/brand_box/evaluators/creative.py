"""
Lightweight evaluators for creative artifacts.

These evaluators are intentionally heuristic-first so they work even when no
LLM provider is configured. They produce consistent scores and review metadata
that can later be replaced or augmented with model-based critics.
"""

from __future__ import annotations

from brand_box.models.artifacts import StageReview, VideoStoryboard, WebsiteSpec


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

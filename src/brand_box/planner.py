"""Content production planner.

Given a :class:`BrandProject`, generates a structured list of render jobs
that describe *what* video content to produce — formats, profiles, hook
angles, priorities — without actually rendering anything.
"""

from __future__ import annotations

import itertools
import json
from typing import Any

from brand_box.generators.script import BUILTIN_FORMATS
from brand_box.project import BrandProject

# Priority by format id — lower is higher priority.
_FORMAT_PRIORITY: dict[str, int] = {
    "teaser": 1,
    "explainer": 1,
    "testimonial": 2,
    "fact": 2,
    "founder": 3,
}

_DEFAULT_PRIORITY = 3


class ContentPlanner:
    """Plan video content production from a brand project."""

    def plan(
        self,
        project: BrandProject,
        count: int = 3,
        formats: list[str] | None = None,
        profiles: list[str] | None = None,
    ) -> list[dict]:
        """Generate a content plan.

        Returns a list of render jobs, each a dict with:
        - format_id: str (teaser, explainer, etc.)
        - profile: str (reel, square, web-hero, youtube)
        - hook_angle: str (problem-first, curiosity, etc.)
        - output_filename: str (suggested filename)
        - priority: int (1=high, 3=low)
        """
        formats = formats or ["teaser"]
        profiles = profiles or ["reel"]

        jobs: list[dict] = []

        # Build base combinations and pair each with a cycling hook-angle
        # iterator keyed by format so each format cycles independently.
        angle_iters: dict[str, itertools.cycle[str]] = {}
        for fmt_id in formats:
            fmt_def = BUILTIN_FORMATS.get(fmt_id)
            angles = fmt_def.hook_angles if fmt_def else ["problem-first"]
            angle_iters[fmt_id] = itertools.cycle(angles)

        # Phase 1 — one job per format × profile combination.
        for fmt_id, profile in itertools.product(formats, profiles):
            angle = next(angle_iters[fmt_id])
            jobs.append(self._make_job(fmt_id, profile, angle))

        # Phase 2 — fill remaining slots up to *count* by cycling through
        # the same combinations but advancing to the next hook angle.
        combo_cycle = itertools.cycle(list(itertools.product(formats, profiles)))
        while len(jobs) < count:
            fmt_id, profile = next(combo_cycle)
            angle = next(angle_iters[fmt_id])
            job = self._make_job(fmt_id, profile, angle)
            # Avoid exact duplicates (same format + profile + angle).
            if not any(
                j["format_id"] == job["format_id"]
                and j["profile"] == job["profile"]
                and j["hook_angle"] == job["hook_angle"]
                for j in jobs
            ):
                jobs.append(job)
            else:
                # All angles exhausted for this combo — still append to
                # guarantee we eventually reach *count*.
                jobs.append(job)

        return jobs[:count]

    # ------------------------------------------------------------------
    @staticmethod
    def _make_job(format_id: str, profile: str, hook_angle: str) -> dict:
        priority = _FORMAT_PRIORITY.get(format_id, _DEFAULT_PRIORITY)
        filename = f"video_{format_id}_{profile}_{hook_angle}.mp4"
        return {
            "format_id": format_id,
            "profile": profile,
            "hook_angle": hook_angle,
            "output_filename": filename,
            "priority": priority,
        }


# ------------------------------------------------------------------
# Utility helpers
# ------------------------------------------------------------------

def plan_to_json(plan: list[dict]) -> str:
    """Return the plan as a formatted JSON string."""
    return json.dumps(plan, indent=2, ensure_ascii=False)


def describe_brand(project: BrandProject) -> dict[str, Any]:
    """Extract a concise brand summary useful for agent context.

    Returns a dict with:
    - name, concept, tagline
    - primary_colors (list)
    - tone
    - logo_path
    - brand_direction_summary (if available)
    """
    identity = project.identity

    primary_colors = [
        c
        for c in [identity.primary_color, identity.secondary_color, identity.accent_color]
        if c
    ]

    summary: dict[str, Any] = {
        "name": project.active_name,
        "concept": project.concept,
        "tagline": identity.tagline,
        "primary_colors": primary_colors,
        "tone": identity.tone,
        "logo_path": project.active_logo_path,
    }

    direction = project.brand_direction
    if direction and direction.positioning:
        summary["brand_direction_summary"] = {
            "positioning": direction.positioning,
            "personality": direction.personality,
            "messaging_pillars": direction.messaging_pillars,
        }

    return summary

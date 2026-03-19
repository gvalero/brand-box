"""
Typed artifact models for the brand-box creative pipeline.

These dataclasses represent intermediate decisions that are richer than the
legacy flat ``brand.json`` shape. They let the repo move toward explicit
briefing, selection, evaluation, and production stages while remaining easy to
serialize.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StageReview:
    """Evaluator feedback attached to a stage artifact."""

    stage: str = ""
    score: float = 0.0
    subscores: dict[str, float] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class BrandBrief:
    """Normalized input brief used by strategist-style generators."""

    product: str = ""
    audience: list[str] = field(default_factory=list)
    problem: str = ""
    category: str = ""
    goals: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)


@dataclass
class NameCandidate:
    """A candidate brand name plus rationale and evaluation metadata."""

    name: str = ""
    rationale: str = ""
    tone: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    domain_notes: str = ""
    scores: dict[str, float] = field(default_factory=dict)
    review: StageReview = field(default_factory=StageReview)


@dataclass
class LogoConcept:
    """A logo direction or generated concept."""

    id: str = ""
    style: str = ""
    prompt: str = ""
    rationale: str = ""
    asset_paths: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    review: StageReview = field(default_factory=StageReview)


@dataclass
class BrandDirection:
    """Locked brand direction after naming/identity exploration."""

    positioning: str = ""
    audience: str = ""
    personality: list[str] = field(default_factory=list)
    messaging_pillars: list[str] = field(default_factory=list)
    tagline_options: list[str] = field(default_factory=list)
    palette: dict[str, str] = field(default_factory=dict)
    typography: dict[str, str] = field(default_factory=dict)
    imagery_keywords: list[str] = field(default_factory=list)
    selected_logo_id: str = ""
    review: StageReview = field(default_factory=StageReview)


@dataclass
class WebsiteSpec:
    """A structured website concept that a renderer can implement."""

    id: str = ""
    audience: str = ""
    conversion_goal: str = ""
    visual_direction: str = ""
    sections: list[dict[str, Any]] = field(default_factory=list)
    copy: dict[str, Any] = field(default_factory=dict)
    design_tokens: dict[str, Any] = field(default_factory=dict)
    asset_refs: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    review: StageReview = field(default_factory=StageReview)


@dataclass
class VideoStoryboard:
    """A structured storyboard for short-form video production."""

    id: str = ""
    platform: str = ""
    angle: str = ""
    hook: str = ""
    scenes: list[dict[str, Any]] = field(default_factory=list)
    voiceover: str = ""
    caption_plan: list[str] = field(default_factory=list)
    asset_refs: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    review: StageReview = field(default_factory=StageReview)


@dataclass
class MusicPlan:
    """A music direction or selected track for a video render."""

    id: str = ""
    platform: str = ""
    format_id: str = ""
    mood: str = ""
    tempo: str = ""
    instrumentation: list[str] = field(default_factory=list)
    prompt: str = ""
    track_path: str = ""
    source: str = ""
    scores: dict[str, float] = field(default_factory=dict)
    review: StageReview = field(default_factory=StageReview)

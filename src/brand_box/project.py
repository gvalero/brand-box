"""
Brand project state management.

A brand project is a directory containing:
  - brand.json   (project config + generated state)
  - output/      (generated assets)

This module handles creating, loading, saving, and querying project state.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Optional, TypeVar, get_args, get_origin

from brand_box.models.artifacts import (
    BrandBrief,
    BrandDirection,
    LogoConcept,
    MusicPlan,
    NameCandidate,
    StageReview,
    VideoStoryboard,
    WebsiteSpec,
)


@dataclass
class BrandIdentity:
    """Generated brand identity (colors, fonts, tone)."""
    primary_color: str = ""
    secondary_color: str = ""
    accent_color: str = ""
    background_color: str = ""
    text_color: str = ""
    font_heading: str = ""
    font_body: str = ""
    tone: str = ""           # e.g. "warm, playful, trustworthy"
    tagline: str = ""


@dataclass
class BrandProject:
    """Full brand project state."""
    concept: str = ""                         # original concept description
    name: str = ""                            # chosen brand name
    name_candidates: list[str] = field(default_factory=list)
    identity: BrandIdentity = field(default_factory=BrandIdentity)
    logo_paths: list[str] = field(default_factory=list)
    website_path: str = ""
    social_profiles: dict[str, Any] = field(default_factory=dict)
    video_paths: list[str] = field(default_factory=list)
    brief: BrandBrief = field(default_factory=BrandBrief)
    selected_name: str = ""
    naming_candidates: list[NameCandidate] = field(default_factory=list)
    logo_concepts: list[LogoConcept] = field(default_factory=list)
    selected_logo: str = ""
    brand_direction: BrandDirection = field(default_factory=BrandDirection)
    website_specs: list[WebsiteSpec] = field(default_factory=list)
    selected_website_spec: str = ""
    storyboards: list[VideoStoryboard] = field(default_factory=list)
    music_plans: list[MusicPlan] = field(default_factory=list)
    selected_music_plan: str = ""
    reviews: list[StageReview] = field(default_factory=list)
    run_history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # --- I/O ---

    def save(self, path: Path | str) -> None:
        """Write project state to brand.json."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the project using plain Python containers."""
        data = _serialize(self)
        if self.selected_name and not data.get("name"):
            data["name"] = self.selected_name
        if self.selected_logo and not data.get("logo_paths"):
            data["logo_paths"] = [self.selected_logo]
        return data

    @classmethod
    def load(cls, path: Path | str) -> BrandProject:
        """Load project state from brand.json."""
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrandProject:
        """Create a project from serialized data, including legacy shapes."""
        payload = dict(data)
        payload["identity"] = _coerce_dataclass(BrandIdentity, payload.get("identity"))
        payload["brief"] = _coerce_dataclass(BrandBrief, payload.get("brief"))
        payload["brand_direction"] = _coerce_dataclass(BrandDirection, payload.get("brand_direction"))
        payload["reviews"] = _coerce_list(StageReview, payload.get("reviews"))
        payload["run_history"] = payload.get("run_history") or []
        payload["social_profiles"] = payload.get("social_profiles") or {}
        payload["metadata"] = payload.get("metadata") or {}
        payload["video_paths"] = payload.get("video_paths") or []
        payload["logo_paths"] = payload.get("logo_paths") or []
        payload["website_specs"] = _coerce_list(WebsiteSpec, payload.get("website_specs"))
        payload["storyboards"] = _coerce_list(VideoStoryboard, payload.get("storyboards"))
        payload["music_plans"] = _coerce_list(MusicPlan, payload.get("music_plans"))
        payload["logo_concepts"] = _coerce_list(LogoConcept, payload.get("logo_concepts"))

        raw_name_candidates = payload.get("name_candidates") or []
        payload["naming_candidates"] = _coerce_name_candidates(
            payload.get("naming_candidates"),
            raw_name_candidates,
        )
        payload["name_candidates"] = _normalize_name_strings(
            raw_name_candidates,
            payload["naming_candidates"],
        )

        payload["selected_name"] = payload.get("selected_name") or payload.get("name", "")
        payload["selected_logo"] = payload.get("selected_logo") or payload.get("metadata", {}).get("chosen_logo", "")
        payload["selected_website_spec"] = payload.get("selected_website_spec", "")
        payload["selected_music_plan"] = payload.get("selected_music_plan", "")

        known_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in payload.items() if k in known_fields}
        return cls(**filtered)

    @classmethod
    def find(cls, start_dir: Path | str | None = None) -> Optional[BrandProject]:
        """Walk up from *start_dir* looking for brand.json."""
        d = Path(start_dir) if start_dir else Path.cwd()
        while True:
            candidate = d / "brand.json"
            if candidate.is_file():
                return cls.load(candidate)
            parent = d.parent
            if parent == d:
                break
            d = parent
        return None

    # --- Helpers ---

    @property
    def output_dir(self) -> Path:
        """Standard output directory (sibling of brand.json)."""
        return Path.cwd() / "output"

    def ensure_output_dirs(self) -> dict[str, Path]:
        """Create and return the standard output subdirectories."""
        dirs = {}
        for name in ("names", "logos", "identity", "website", "social", "videos"):
            d = self.output_dir / name
            d.mkdir(parents=True, exist_ok=True)
            dirs[name] = d
        return dirs

    @property
    def active_name(self) -> str:
        """Return the explicit selection if present, otherwise the legacy name."""
        return self.selected_name or self.name

    @property
    def active_logo_path(self) -> str:
        """Return the selected logo path — empty if nothing explicitly selected."""
        if self.selected_logo:
            return self.selected_logo
        if self.metadata.get("chosen_logo"):
            return str(self.metadata["chosen_logo"])
        return ""


T = TypeVar("T")


def _serialize(value: Any) -> Any:
    """Recursively convert dataclasses into JSON-safe containers."""
    if is_dataclass(value):
        return {f.name: _serialize(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    return value


def _coerce_dataclass(cls: type[T], data: Any) -> T:
    """Coerce dictionaries into a dataclass, ignoring unknown fields."""
    if isinstance(data, cls):
        return data
    if not isinstance(data, dict):
        return cls()

    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        value = data.get(f.name)
        if value is None:
            continue
        kwargs[f.name] = _coerce_value(f.type, value)
    return cls(**kwargs)


def _coerce_list(cls: type[T], data: Any) -> list[T]:
    """Coerce a list of dicts into dataclass instances."""
    if not isinstance(data, list):
        return []
    result: list[T] = []
    for item in data:
        if isinstance(item, cls):
            result.append(item)
        elif isinstance(item, dict):
            result.append(_coerce_dataclass(cls, item))
    return result


def _coerce_name_candidates(data: Any, legacy_names: list[Any]) -> list[NameCandidate]:
    """Load typed naming artifacts, or derive them from a legacy string list."""
    typed = _coerce_list(NameCandidate, data)
    if typed:
        return typed
    result: list[NameCandidate] = []
    for item in legacy_names:
        if isinstance(item, str) and item.strip():
            result.append(NameCandidate(name=item.strip()))
        elif isinstance(item, dict):
            result.append(_coerce_dataclass(NameCandidate, item))
    return result


def _normalize_name_strings(raw_names: list[Any], typed_names: list[NameCandidate]) -> list[str]:
    """Keep the legacy string field populated for current generators."""
    names = [item.strip() for item in raw_names if isinstance(item, str) and item.strip()]
    if names:
        return names
    return [candidate.name for candidate in typed_names if candidate.name]


def _coerce_value(type_hint: Any, value: Any) -> Any:
    """Recursively coerce nested dataclass/list values."""
    origin = get_origin(type_hint)
    if origin is list:
        args = get_args(type_hint)
        item_type = args[0] if args else Any
        if not isinstance(value, list):
            return []
        return [_coerce_value(item_type, item) for item in value]
    if origin is dict:
        if not isinstance(value, dict):
            return {}
        return value

    if isinstance(type_hint, type) and is_dataclass(type_hint):
        return _coerce_dataclass(type_hint, value)

    return value

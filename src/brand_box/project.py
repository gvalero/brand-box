"""
Brand project state management.

A brand project is a directory containing:
  - brand.json   (project config + generated state)
  - output/      (generated assets)

This module handles creating, loading, saving, and querying project state.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


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
    metadata: dict[str, Any] = field(default_factory=dict)

    # --- I/O ---

    def save(self, path: Path | str) -> None:
        """Write project state to brand.json."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path | str) -> BrandProject:
        """Load project state from brand.json."""
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        identity_data = data.pop("identity", {})
        identity = BrandIdentity(**identity_data)
        return cls(identity=identity, **data)

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

"""
CLI entry point for brand-box.

Usage (recommended order):
    brand-box init <concept>          — start a new brand project
    brand-box name [--count N]        — generate name candidates (STOPS here)
    brand-box select name "MyBrand"   — lock name choice  ← decision gate
    brand-box logo [--count N]        — generate logo options (STOPS here)
    brand-box select logo 2           — lock logo choice  ← decision gate
    brand-box identity                — generate colors, fonts, tone
    brand-box kit                     — generate brand guidelines
    brand-box website [--variants]    — generate a landing page
    brand-box social                  — generate social media assets
    brand-box video [--format]        — generate social media video
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from brand_box import __version__
from brand_box.models.artifacts import BrandBrief
from brand_box.project import BrandProject

try:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()
    HAS_RICH = True
except ImportError:
    console = None
    HAS_RICH = False


def _print(msg: str) -> None:
    if HAS_RICH and console:
        console.print(msg)
    else:
        print(msg)


def _error(msg: str) -> None:
    if HAS_RICH and console:
        console.print(f"[red]✗[/red] {msg}")
    else:
        print(f"ERROR: {msg}")


def _success(msg: str) -> None:
    if HAS_RICH and console:
        console.print(f"[green]✓[/green] {msg}")
    else:
        print(f"OK: {msg}")


def _require_gate(
    project: BrandProject,
    *,
    need_name: bool = False,
    need_logo: bool = False,
    json_mode: bool = False,
) -> None:
    """Enforce decision gates — exit if required selections haven't been made.

    When *json_mode* is True the error is emitted as a parseable JSON object
    so that an orchestrating agent can react programmatically.
    """
    missing: list[str] = []
    if need_name and not project.selected_name:
        missing.append("name")
    if need_logo and not project.selected_logo:
        missing.append("logo")
    if not missing:
        return

    if json_mode:
        import json as _json
        print(_json.dumps({
            "status": "gate_failed",
            "missing_selections": missing,
            "help": {s: f"brand-box select {s} <value>" for s in missing},
        }, indent=2))
    else:
        for stage in missing:
            if stage == "name":
                _error("No name selected. Run 'brand-box select name <name>' to lock your choice.")
                if project.name_candidates:
                    _print("  Available:")
                    for n in project.name_candidates:
                        _print(f"    • {n}")
                else:
                    _print("  Run 'brand-box name' first to generate candidates.")
            elif stage == "logo":
                _error("No logo selected. Run 'brand-box select logo <index>' to lock your choice.")
                if project.logo_paths:
                    _print("  Available:")
                    for i, p in enumerate(project.logo_paths, 1):
                        _print(f"    {i}. {p}")
                else:
                    _print("  Run 'brand-box logo' first to generate options.")
    sys.exit(1)


def _reset_identity_and_downstream(project: BrandProject) -> None:
    """Clear artifacts that depend on the selected brand name/logo."""
    project.identity = project.identity.__class__()
    project.brand_direction = project.brand_direction.__class__()
    project.website_path = ""
    project.website_specs = []
    project.selected_website_spec = ""
    project.social_profiles = {}
    project.video_paths = []
    project.storyboards = []
    project.music_plans = []
    project.selected_music_plan = ""
    project.reviews = [
        review for review in project.reviews if review.stage not in {"logo", "identity", "website", "video", "music", "social", "kit"}
    ]
    project.run_history = [
        entry
        for entry in project.run_history
        if entry.get("stage") not in {"logo", "identity", "website", "video", "music", "social", "kit"}
    ]
    project.metadata.pop("kit_path", None)


def _archive_downstream_state(
    project: BrandProject,
    *,
    reason: str,
    previous_name: str = "",
) -> None:
    """Archive the current downstream branch before clearing active state."""
    downstream_reviews = [
        review for review in project.reviews if review.stage in {"identity", "website", "video", "music", "social", "kit", "logo"}
    ]
    downstream_history = [
        entry
        for entry in project.run_history
        if entry.get("stage") in {"identity", "website", "video", "music", "social", "kit", "logo"}
    ]
    has_downstream_state = any(
        [
            project.selected_logo,
            project.logo_paths,
            project.logo_concepts,
            any(getattr(project.identity, field, "") for field in ("primary_color", "secondary_color", "accent_color", "tone", "tagline")),
            any(getattr(project.brand_direction, field, None) for field in ("positioning", "audience", "personality", "messaging_pillars", "tagline_options", "palette", "typography", "imagery_keywords")),
            project.website_path,
            project.website_specs,
            project.selected_website_spec,
            project.social_profiles,
            project.video_paths,
            project.storyboards,
            project.music_plans,
            project.selected_music_plan,
            downstream_reviews,
            downstream_history,
            project.metadata.get("kit_path"),
        ]
    )
    if not has_downstream_state:
        return

    serialized = project.to_dict()
    serialized_reviews = [
        review
        for review in serialized["reviews"]
        if review.get("stage") in {"identity", "website", "video", "music", "social", "kit", "logo"}
    ]
    snapshot = {
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "previous_name": previous_name or project.active_name,
        "selected_logo": project.selected_logo,
        "logo_paths": list(project.logo_paths),
        "logo_concepts": serialized["logo_concepts"],
        "identity": serialized["identity"],
        "brand_direction": serialized["brand_direction"],
        "website_path": project.website_path,
        "website_specs": serialized["website_specs"],
        "selected_website_spec": project.selected_website_spec,
        "social_profiles": project.social_profiles,
        "video_paths": list(project.video_paths),
        "storyboards": serialized["storyboards"],
        "music_plans": serialized["music_plans"],
        "selected_music_plan": project.selected_music_plan,
        "reviews": serialized_reviews,
        "run_history": downstream_history,
        "metadata": {"kit_path": project.metadata.get("kit_path", "")},
    }
    project.archived_artifacts.append(snapshot)


def _reset_logo_and_downstream(project: BrandProject) -> None:
    """Clear artifacts that depend on the selected logo."""
    project.selected_logo = ""
    project.logo_paths = []
    project.logo_concepts = []
    _reset_identity_and_downstream(project)


def _drop_first_matching_review(project: BrandProject, review_to_remove) -> None:
    """Remove a single matching persisted review, preserving others with equal scores."""
    if not review_to_remove:
        return

    remaining: list = []
    removed = False
    for item in project.reviews:
        matches = (
            not removed
            and item.stage == review_to_remove.stage
            and item.score == review_to_remove.score
            and item.subscores == review_to_remove.subscores
            and item.issues == review_to_remove.issues
            and item.recommendation == review_to_remove.recommendation
        )
        if matches:
            removed = True
            continue
        remaining.append(item)
    project.reviews = remaining


def _reset_name_and_downstream(project: BrandProject) -> None:
    """Clear artifacts that depend on the selected brand name."""
    project.selected_name = ""
    project.name = ""
    _reset_logo_and_downstream(project)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _parse_brief(concept: str) -> BrandBrief:
    """Derive a lightweight BrandBrief from a concept string (no LLM)."""
    import re

    text = concept.strip()
    first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]

    # --- audience ---
    audience: list[str] = []
    audience_patterns = [
        r"\bfor\s+([\w\s]+?)(?:\s+(?:who|that|to|,|\.)|$)",
        r"\btargeting\s+([\w\s]+?)(?:\s+(?:who|that|to|,|\.)|$)",
        r"\baimed\s+at\s+([\w\s]+?)(?:\s+(?:who|that|to|,|\.)|$)",
    ]
    for pat in audience_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            segment = m.group(1).strip()
            if segment and len(segment.split()) <= 6:
                audience.append(segment)

    # --- problem ---
    problem = ""
    problem_patterns = [
        r"\b(?:solves?|address(?:es)?|fix(?:es)?|helps?\s+with)\s+(.+?)(?:\.|$)",
        r"\b(?:struggle|pain\s*point|challenge|issue)\s+(?:of|with)\s+(.+?)(?:\.|$)",
    ]
    for pat in problem_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            problem = m.group(1).strip()
            break

    # --- category ---
    category = ""
    category_map: dict[str, str] = {
        "app": "software",
        "platform": "software",
        "saas": "software",
        "software": "software",
        "tool": "software",
        "api": "software",
        "website": "software",
        "book": "publishing",
        "magazine": "publishing",
        "newsletter": "publishing",
        "food": "consumer goods",
        "drink": "consumer goods",
        "beverage": "consumer goods",
        "snack": "consumer goods",
        "clothing": "fashion",
        "apparel": "fashion",
        "fashion": "fashion",
        "fitness": "health & wellness",
        "health": "health & wellness",
        "wellness": "health & wellness",
        "game": "entertainment",
        "music": "entertainment",
        "film": "entertainment",
        "podcast": "media",
        "blog": "media",
        "agency": "professional services",
        "consulting": "professional services",
        "studio": "creative services",
        "course": "education",
        "learning": "education",
        "education": "education",
    }
    lower = text.lower()
    for keyword, cat in category_map.items():
        if re.search(rf"\b{re.escape(keyword)}\b", lower):
            category = cat
            break

    return BrandBrief(
        product=first_sentence,
        audience=audience,
        problem=problem,
        category=category,
        goals=["Build brand awareness", "Validate demand"],
    )


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize a new brand project."""
    project_dir = Path(args.output or ".").resolve()
    brand_file = project_dir / "brand.json"

    if brand_file.exists() and not args.force:
        _error(f"brand.json already exists at {brand_file}. Use --force to overwrite.")
        sys.exit(1)

    project = BrandProject(concept=args.concept)
    project.brief = _parse_brief(args.concept)
    project_dir.mkdir(parents=True, exist_ok=True)
    project.save(brand_file)
    project.ensure_output_dirs()

    _success(f"Brand project initialized: {brand_file}")
    _print(f"  Concept: {args.concept}")
    _print(f"  Output:  {project_dir / 'output'}")
    _print("")
    _print("Next steps:")
    _print("  brand-box name                  — generate name candidates")
    _print("  brand-box select name \"X\"       — lock your name choice")
    _print("  brand-box logo                  — generate logo options")
    _print("  brand-box select logo N         — lock your logo choice")
    _print("  brand-box identity              — generate brand identity")
    _print("  brand-box kit                   — generate brand guidelines")


def cmd_name(args: argparse.Namespace) -> None:
    """Generate brand name candidates.

    This is a **decision gate** — it produces candidates and stops.
    The caller (human or agent) must run ``brand-box select name <name>``
    before downstream commands will proceed.
    """
    project = _load_project()
    if not project:
        return

    from brand_box.generators.name import NameGenerator
    gen = NameGenerator()
    count = args.count or 10

    _print(f"Generating {count} name candidates for: {project.concept}")
    candidates = gen.generate_rich(project.concept, count=count)
    names = [c.name for c in candidates]
    _archive_downstream_state(project, reason="regenerated_name_candidates", previous_name=project.active_name)
    _reset_name_and_downstream(project)
    project.name_candidates = names
    project.naming_candidates = candidates

    project.save(Path.cwd() / "brand.json")

    if args.json:
        import json
        from dataclasses import asdict
        print(json.dumps({
            "status": "awaiting_selection",
            "stage": "name",
            "candidates": [asdict(c) for c in candidates],
            "next_step": "brand-box select name <name>",
        }, indent=2))
    else:
        for c in candidates:
            line = f"  • {c.name}"
            if c.rationale:
                line += f" — {c.rationale}"
            _print(line)
        _print("")
        _success(f"{len(names)} candidates saved. Select one to continue:")
        _print("  brand-box select name \"<name>\"")


def cmd_logo(args: argparse.Namespace) -> None:
    """Generate logo options.

    This is a **decision gate** — it produces options and stops.
    The caller must run ``brand-box select logo <index>`` before
    downstream commands will proceed.
    """
    project = _load_project()
    if not project:
        return

    # --name flag bypasses the name-selection gate
    name = args.name or project.selected_name
    if not name:
        json_mode = getattr(args, "json", False)
        if json_mode:
            import json
            print(json.dumps({
                "status": "gate_failed",
                "missing_selections": ["name"],
                "help": {"name": "brand-box select name <value>"},
            }, indent=2))
        else:
            _error("No name selected. Run 'brand-box select name <name>' first, or pass --name.")
            if project.name_candidates:
                _print("  Available candidates:")
                for n in project.name_candidates:
                    _print(f"    • {n}")
        sys.exit(1)

    from brand_box.generators.logo import LogoGenerator
    gen = LogoGenerator()
    dirs = project.ensure_output_dirs()
    count = args.count or 3

    _print(f"Generating {count} logo options for: {name}")
    _archive_downstream_state(project, reason="regenerated_logo_options", previous_name=project.active_name)
    _reset_logo_and_downstream(project)
    paths = gen.generate(
        brand_name=name,
        concept=project.concept,
        identity=project.identity,
        output_dir=str(dirs["logos"]),
        count=count,
    )
    project.logo_paths = paths
    if gen.last_concepts:
        existing_ids = {c.id for c in gen.last_concepts}
        project.logo_concepts = [c for c in project.logo_concepts if c.id not in existing_ids]
        project.logo_concepts.extend(gen.last_concepts)

    project.save(Path.cwd() / "brand.json")

    if args.json:
        import json
        from dataclasses import asdict
        print(json.dumps({
            "status": "awaiting_selection",
            "stage": "logo",
            "options": [
                {"index": i + 1, "path": p, **(asdict(gen.last_concepts[i]) if gen.last_concepts and i < len(gen.last_concepts) else {})}
                for i, p in enumerate(paths)
            ],
            "next_step": "brand-box select logo <index>",
        }, indent=2))
    else:
        for i, p in enumerate(paths, 1):
            line = f"  {i}. {p}"
            if gen.last_concepts and i - 1 < len(gen.last_concepts):
                concept = gen.last_concepts[i - 1]
                if concept.style:
                    line += f" ({concept.style})"
            _print(line)
        _print("")
        _success(f"{len(paths)} logo(s) saved. Select one to continue:")
        _print("  brand-box select logo <number>")


def cmd_identity(args: argparse.Namespace) -> None:
    """Generate brand identity (colors, fonts, tone)."""
    project = _load_project()
    if not project:
        return

    _require_gate(project, need_name=True)

    from brand_box.generators.identity import IdentityGenerator
    gen = IdentityGenerator()

    name = project.selected_name
    _print(f"Generating brand identity for: {name}")

    identity, direction = gen.generate_rich(concept=project.concept, name=name)
    project.identity = identity
    project.brand_direction = direction
    project.save(Path.cwd() / "brand.json")

    _print(f"  Primary:    {identity.primary_color}")
    _print(f"  Secondary:  {identity.secondary_color}")
    _print(f"  Accent:     {identity.accent_color}")
    _print(f"  Background: {identity.background_color}")
    _print(f"  Heading:    {identity.font_heading}")
    _print(f"  Body:       {identity.font_body}")
    _print(f"  Tone:       {identity.tone}")
    _print(f"  Tagline:    {identity.tagline}")
    if direction.positioning:
        _print(f"  Positioning: {direction.positioning}")
    if direction.personality:
        _print(f"  Personality: {', '.join(direction.personality)}")
    if direction.messaging_pillars:
        _print(f"  Messaging:   {', '.join(direction.messaging_pillars)}")
    if direction.imagery_keywords:
        _print(f"  Imagery:     {', '.join(direction.imagery_keywords)}")
    _success("Brand identity saved to brand.json")


def cmd_website(args: argparse.Namespace) -> None:
    """Generate a landing page."""
    project = _load_project()
    if not project:
        return

    _require_gate(project, need_name=True, need_logo=True)

    from brand_box.generators.website import WebsiteGenerator
    gen = WebsiteGenerator()
    dirs = project.ensure_output_dirs()

    output_dir = args.output_dir if hasattr(args, "output_dir") and args.output_dir else str(dirs["website"])
    variants = hasattr(args, "variants") and args.variants
    filenames = None
    if hasattr(args, "filenames") and args.filenames:
        filenames = [f.strip() for f in args.filenames.split(",")]

    if variants:
        _print("Generating landing page variants…")
        paths = gen.generate_all(project=project, output_dir=output_dir, filenames=filenames)
        project.website_path = paths[-1]  # index.html is last
        if gen.last_specs:
            existing_ids = {spec.id for spec in gen.last_specs}
            project.website_specs = [spec for spec in project.website_specs if spec.id not in existing_ids]
            project.website_specs.extend(gen.last_specs)
        if gen.last_spec:
            project.selected_website_spec = gen.last_spec.id
        project.save(Path.cwd() / "brand.json")
        for i, (spec, path) in enumerate(zip(gen.last_specs, paths[:-1])):
            _print(f"  Variant {i + 1}: {spec.visual_direction} (score: {spec.review.score:.2f})")
        _success(f"{len(paths)} landing pages saved to {output_dir}")
    else:
        _print("Generating landing page…")
        path = gen.generate(project=project, output_dir=output_dir)
        project.website_path = path
        if gen.last_specs:
            existing_ids = {spec.id for spec in gen.last_specs}
            project.website_specs = [spec for spec in project.website_specs if spec.id not in existing_ids]
            project.website_specs.extend(gen.last_specs)
        if gen.last_spec:
            project.selected_website_spec = gen.last_spec.id
            _print(f"  Selected direction: {gen.last_spec.visual_direction}")
            _print(f"  Website score: {gen.last_spec.review.score:.2f}")
        project.save(Path.cwd() / "brand.json")
        _success(f"Landing page saved to {path}")


def cmd_social(args: argparse.Namespace) -> None:
    """Generate social media assets."""
    project = _load_project()
    if not project:
        return

    _require_gate(project, need_name=True, need_logo=True)

    from brand_box.generators.social import SocialGenerator
    gen = SocialGenerator()
    dirs = project.ensure_output_dirs()

    platforms = args.platforms.split(",") if args.platforms else ["tiktok", "instagram", "youtube"]
    _print(f"Generating social assets for: {', '.join(platforms)}")

    result = gen.generate(project=project, platforms=platforms, output_dir=str(dirs["social"]))
    project.social_profiles = result
    project.save(Path.cwd() / "brand.json")

    if result.get("bios"):
        for platform, bio in result["bios"].items():
            _print(f"  {platform}: {bio}")

    pics = result.get("profile_pics", {})
    banners = result.get("banners", {})
    _success(f"{len(pics)} profile pic(s) + {len(banners)} banner(s) saved to {dirs['social']}")


def cmd_kit(args: argparse.Namespace) -> None:
    """Generate a brand guidelines / brand kit page."""
    project = _load_project()
    if not project:
        return

    _require_gate(project, need_name=True, need_logo=True)

    from brand_box.generators.kit import KitGenerator
    gen = KitGenerator()
    dirs = project.ensure_output_dirs()

    _print("Generating brand guidelines…")
    path = gen.generate(project=project, output_dir=str(dirs["identity"]))
    project.metadata["kit_path"] = path
    project.save(Path.cwd() / "brand.json")
    _success(f"Brand guidelines saved to {path}")


def cmd_video(args: argparse.Namespace) -> None:
    """Generate social media video content."""
    project = _load_project()
    if not project:
        return

    _require_gate(
        project,
        need_name=True,
        need_logo=True,
        json_mode=getattr(args, "json", False),
    )

    name = project.selected_name
    dirs = project.ensure_output_dirs()
    fmt_id = args.format or "teaser"
    music_arg = args.music
    music_dir = args.music_dir

    from brand_box.generators.script import ScriptGenerator, BUILTIN_FORMATS

    identity_ctx = ""
    if project.identity and project.identity.tone:
        identity_ctx = (
            f"Tone: {project.identity.tone}. "
            f"Colors: {project.identity.primary_color}, {project.identity.secondary_color}, {project.identity.accent_color}. "
            f"Tagline: {project.identity.tagline}."
        )

    profile = args.profile or "reel"
    suffix = "" if profile == "reel" else f"_{profile}"
    output_path = str(dirs["videos"] / f"video_{fmt_id}{suffix}.mp4")

    if fmt_id not in BUILTIN_FORMATS:
        _error(f"Unknown format: {fmt_id}. Available: {list(BUILTIN_FORMATS.keys())}")
        sys.exit(1)

    _print(f"Generating storyboard options ({fmt_id} format)…")
    script_gen = ScriptGenerator()
    storyboard_variants = script_gen.generate_storyboard_variants(
        brand_name=name,
        concept=project.concept,
        format_id=fmt_id,
        identity_context=identity_ctx,
        count=3,
    )
    if not storyboard_variants:
        _error("No storyboard variants were generated. Check your model configuration or try again.")
        sys.exit(1)
    existing_ids = {sb.id for sb in storyboard_variants}
    project.storyboards = [sb for sb in project.storyboards if sb.id not in existing_ids]
    project.storyboards.extend(storyboard_variants)
    storyboard = script_gen.select_best_storyboard(storyboard_variants)
    script = script_gen.storyboard_to_script(storyboard, format_id=fmt_id)
    _print(f"  Selected hook angle: {storyboard.angle}")
    _print(f"  Storyboard score: {storyboard.review.score:.2f}")
    _print(f"  Scenes: {len(storyboard.scenes)}")

    from brand_box.generators.music import MusicPlanner
    music_planner = MusicPlanner()
    music_plan = music_planner.plan(
        brand_name=name,
        concept=project.concept,
        format_id=fmt_id,
        storyboard={
            "hook": storyboard.hook,
            "scenes": storyboard.scenes,
        },
        music_path=music_arg,
        music_dir=music_dir,
        profile=profile,
    )
    if music_plan.track_path:
        _print(f"  Music: {Path(music_plan.track_path).name}")
    else:
        _print(f"  Music plan: {music_plan.mood} / {music_plan.tempo}")
    project.music_plans = [mp for mp in project.music_plans if mp.id != music_plan.id]
    project.music_plans.append(music_plan)
    project.selected_music_plan = music_plan.id

    # --- Try Manus first (superior quality) ---
    if not args.local:
        try:
            from brand_box.generators.manus_video import ManusVideoGenerator
            from brand_box.config import MANUS_API_KEY
            if MANUS_API_KEY:
                _print("Generating video via Manus AI…")
                manus = ManusVideoGenerator()
                logo_path = project.selected_logo
                result_path = manus.generate_video(
                    brand_name=name,
                    concept=project.concept,
                    format_id=fmt_id,
                    identity_context=identity_ctx,
                    output_path=output_path,
                    logo_path=logo_path,
                    storyboard={
                        "hook": storyboard.hook,
                        "scenes": storyboard.scenes,
                        "voiceover": storyboard.voiceover,
                        "caption_plan": storyboard.caption_plan,
                    },
                    profile=profile,
                )
                project.video_paths.append(result_path)
                project.save(Path.cwd() / "brand.json")
                if args.json:
                    import json
                    print(json.dumps({
                        "video_path": result_path,
                        "format": fmt_id,
                        "profile": profile,
                        "storyboard_id": storyboard.id,
                        "storyboard_score": storyboard.review.score,
                        "music_plan_id": music_plan.id,
                    }, indent=2))
                else:
                    _success(f"Video saved to {result_path}")
                return
        except Exception as e:
            _print(f"  Manus failed: {e} — falling back to local pipeline")

    # --- Local pipeline fallback ---
    from brand_box.generators.video import VideoAssembler
    _print(f"  Title: {script.get('title', 'N/A')}")

    # Step 2: Images (unless --no-images)
    image_paths = {}
    img_dir = dirs["videos"] / f"images_{fmt_id}"
    img_dir.mkdir(parents=True, exist_ok=True)

    if not args.no_images:
        _print("Generating visuals…")
        from brand_box.generators.image_backend import generate_image

        for seg in script.get("segments", []):
            idx = seg["index"]
            descriptions = [seg.get("visual_description", "Abstract brand visual")]
            descriptions.extend(
                beat for beat in seg.get("visual_beats", [])
                if isinstance(beat, str) and beat.strip()
            )
            asset_paths: list[str] = []
            for asset_i, desc in enumerate(descriptions):
                prompt = (
                    f"Social media video illustration, NO TEXT, NO WORDS, NO LETTERS in the image. "
                    f"Brand: {name}. Style: warm, colorful, professional. "
                    f"Scene: {desc}"
                )
                suffix = "" if asset_i == 0 else f"_beat_{asset_i}"
                img_path = str(img_dir / f"img_{idx}{suffix}.png")
                try:
                    generate_image(prompt, img_path)
                    asset_paths.append(img_path)
                    if asset_i == 0:
                        _print(f"  Image {idx + 1} ✓")
                    else:
                        _print(f"  Cutaway {idx + 1}.{asset_i} ✓")
                except Exception as e:
                    label = f"Image {idx + 1}" if asset_i == 0 else f"Cutaway {idx + 1}.{asset_i}"
                    _print(f"  {label} failed: {e}")
            if asset_paths:
                image_paths[idx] = asset_paths[0] if len(asset_paths) == 1 else asset_paths
    else:
        # --no-images: reuse existing images from previous runs
        for seg in script.get("segments", []):
            idx = seg["index"]
            cached_assets = []
            primary_path = img_dir / f"img_{idx}.png"
            if primary_path.is_file():
                cached_assets.append(str(primary_path))
            beat_index = 1
            while True:
                beat_path = img_dir / f"img_{idx}_beat_{beat_index}.png"
                if not beat_path.is_file():
                    break
                cached_assets.append(str(beat_path))
                beat_index += 1
            if cached_assets:
                image_paths[idx] = cached_assets[0] if len(cached_assets) == 1 else cached_assets
        if image_paths:
            _print(f"Reusing {len(image_paths)} cached images")

    # Step 3: Audio (unless --no-audio)
    audio_paths: dict = {"segments": {}, "full": ""}
    audio_dir = dirs["videos"] / f"audio_{fmt_id}"
    if not args.no_audio:
        _print("Generating narration…")
        try:
            from brand_box.generators.audio import AudioGenerator
            audio_gen = AudioGenerator(cache_dir=str(dirs["videos"] / ".audio_cache"))
            audio_paths = audio_gen.generate_from_script(script, str(audio_dir))
            _print(f"  Audio segments: {len(audio_paths.get('segments', {}))}")
        except Exception as e:
            _print(f"  Audio skipped: {e}")
    else:
        # --no-audio: reuse existing audio from previous runs
        full_path = audio_dir / "full_narration.mp3"
        if full_path.is_file():
            audio_paths["full"] = str(full_path)
            for seg in script.get("segments", []):
                seg_path = audio_dir / f"seg_{seg['index']}.mp3"
                if seg_path.is_file():
                    audio_paths["segments"][seg["index"]] = str(seg_path)
            _print(f"Reusing cached audio ({len(audio_paths['segments'])} segments)")

    # Step 4: Assemble video
    _print("Assembling video…")
    colors = {}
    if project.identity:
        colors = {
            "primary": project.identity.primary_color or "#5b4fc7",
            "secondary": project.identity.secondary_color or "#7e74d2",
            "accent": project.identity.accent_color or "#f6a623",
            "background": project.identity.background_color or "#FFF8F0",
            "text": "#FFFFFF",
            "text_dark": project.identity.text_color or "#333333",
        }

    assembler = VideoAssembler(brand_colors=colors if colors else None, profile=profile)
    tagline = project.identity.tagline if project.identity else ""

    try:
        result_path = assembler.assemble_video(
            script=script,
            audio_paths=audio_paths,
            image_paths=image_paths,
            output_path=output_path,
            brand_name=name,
            tagline=tagline,
            storyboard={
                "hook": storyboard.hook,
                "scenes": storyboard.scenes,
                "voiceover": storyboard.voiceover,
                "caption_plan": storyboard.caption_plan,
            },
            background_music_path=music_plan.track_path,
        )
        project.video_paths.append(result_path)
        project.save(Path.cwd() / "brand.json")
        if args.json:
            import json
            print(json.dumps({
                "video_path": result_path,
                "format": fmt_id,
                "profile": profile,
                "storyboard_id": storyboard.id,
                "storyboard_score": storyboard.review.score,
                "music_plan_id": music_plan.id,
            }, indent=2))
        else:
            _success(f"Video saved to {result_path}")
    except Exception as e:
        _error(f"Video assembly failed: {e}")
        sys.exit(1)


def cmd_select(args: argparse.Namespace) -> None:
    """Lock a name or logo selection (decision gate).

    This is the mechanism that bridges generation and downstream stages.
    An orchestrating agent should call this after presenting options to
    the user and receiving a decision.
    """
    project = _load_project()
    if not project:
        return

    target = args.target
    value = args.value

    if target == "name":
        all_names = project.name_candidates or [c.name for c in project.naming_candidates]
        if all_names and value not in all_names:
            # Try case-insensitive match
            match = next((n for n in all_names if n.lower() == value.lower()), None)
            if match:
                value = match
            else:
                _error(f"'{value}' not found in candidates.")
                _print("  Available:")
                for n in all_names:
                    _print(f"    • {n}")
                _print("  Use exact name or generate more: brand-box name")
                sys.exit(1)

        if project.selected_name != value:
            _archive_downstream_state(project, reason="selected_new_name", previous_name=project.active_name)
            project.selected_name = value
            project.name = value  # keep legacy field in sync
            _reset_logo_and_downstream(project)
        else:
            project.name = value
        project.save(Path.cwd() / "brand.json")

        if args.json:
            import json
            print(json.dumps({
                "status": "selected",
                "stage": "name",
                "selected": value,
            }, indent=2))
        else:
            _success(f"Name locked: {value}")
            _print("  Next: brand-box logo")

    elif target == "logo":
        # Accept 1-based index or file path
        try:
            idx = int(value) - 1
            if not project.logo_paths:
                _error("No logos generated yet. Run 'brand-box logo' first.")
                sys.exit(1)
            if 0 <= idx < len(project.logo_paths):
                selected_path = project.logo_paths[idx]
            else:
                _error(f"Index {int(value)} out of range (1–{len(project.logo_paths)}).")
                for i, p in enumerate(project.logo_paths, 1):
                    _print(f"  {i}. {p}")
                sys.exit(1)
        except ValueError:
            # Treat as file path
            if Path(value).exists():
                selected_path = str(Path(value).resolve())
            else:
                _error(f"Path not found: {value}")
                sys.exit(1)

        if project.selected_logo != selected_path:
            _archive_downstream_state(project, reason="selected_new_logo", previous_name=project.active_name)
            project.selected_logo = selected_path
            _reset_identity_and_downstream(project)
            project.selected_logo = selected_path
        else:
            project.selected_logo = selected_path
        project.save(Path.cwd() / "brand.json")

        if args.json:
            import json
            print(json.dumps({
                "status": "selected",
                "stage": "logo",
                "selected": selected_path,
            }, indent=2))
        else:
            _success(f"Logo locked: {selected_path}")
            _print("  Next: brand-box identity")


def cmd_content_plan(args: argparse.Namespace) -> None:
    """Generate a content production plan."""
    import json
    from brand_box.planner import ContentPlanner

    project = _load_project()
    planner = ContentPlanner()

    formats = args.formats.split(",") if args.formats else None
    profiles = args.profiles.split(",") if args.profiles else None

    plan = planner.plan(
        project=project,
        count=args.count,
        formats=formats,
        profiles=profiles,
    )

    if args.json:
        from brand_box.planner import plan_to_json
        print(plan_to_json(plan))
    else:
        _print(f"Content plan: {len(plan)} video(s)")
        for i, job in enumerate(plan, 1):
            _print(f"  {i}. {job['format_id']}/{job['profile']} — angle: {job['hook_angle']}")


def cmd_render(args: argparse.Namespace) -> None:
    """Render a single video (agent-friendly wrapper around video pipeline)."""
    # Reuse cmd_video logic but with structured output
    args.local = True  # render always uses local pipeline
    if not hasattr(args, 'no_images'):
        args.no_images = False
    if not hasattr(args, 'no_audio'):
        args.no_audio = False
    cmd_video(args)


def cmd_evaluate(args: argparse.Namespace) -> None:
    """Evaluate the last produced video storyboard."""
    import json
    from brand_box.evaluators.creative import VideoEvaluator

    project = _load_project()
    if not project.storyboards:
        _error("No storyboards found. Run 'brand-box video' first.")
        sys.exit(1)

    evaluator = VideoEvaluator()
    storyboard = project.storyboards[-1]  # evaluate most recent
    previous_review = storyboard.review
    review = evaluator.evaluate(storyboard)
    storyboard.review = review
    storyboard.scores = dict(review.subscores)
    _drop_first_matching_review(project, previous_review)
    project.reviews.append(review)
    project.save(Path.cwd() / "brand.json")

    if args.json:
        print(json.dumps({
            "storyboard_id": storyboard.id,
            "score": review.score,
            "subscores": review.subscores,
            "issues": review.issues,
            "recommendation": review.recommendation,
        }, indent=2))
    else:
        _print(f"Storyboard: {storyboard.id}")
        _print(f"  Score: {review.score:.2f}")
        _print(f"  Recommendation: {review.recommendation}")
        for name, value in review.subscores.items():
            _print(f"  {name}: {value:.2f}")
        if review.issues:
            _print(f"  Issues:")
            for issue in review.issues:
                _print(f"    - {issue}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_project() -> BrandProject | None:
    """Load brand.json from CWD or parents."""
    project = BrandProject.find()
    if not project:
        _error("No brand.json found. Run 'brand-box init <concept>' first.")
        sys.exit(1)
    return project


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brand-box",
        description="CLI toolkit for generating complete brand identities",
    )
    parser.add_argument("--version", action="version", version=f"brand-box {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Initialize a new brand project")
    p_init.add_argument("concept", help="Project concept description")
    p_init.add_argument("-o", "--output", help="Output directory (default: CWD)")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing brand.json")

    # name
    p_name = sub.add_parser("name", help="Generate brand name candidates")
    p_name.add_argument("--count", type=int, default=10, help="Number of candidates")
    p_name.add_argument("--json", action="store_true", help="Output as JSON (includes awaiting_selection status)")

    # logo
    p_logo = sub.add_parser("logo", help="Generate logo options")
    p_logo.add_argument("--name", help="Brand name (override — bypasses name selection gate)")
    p_logo.add_argument("--count", type=int, default=3, help="Number of logo variants")
    p_logo.add_argument("--json", action="store_true", help="Output as JSON (includes awaiting_selection status)")

    # identity
    sub.add_parser("identity", help="Generate brand identity (colors, fonts, tone)")

    # kit (after locking name + identity + logo)
    sub.add_parser("kit", help="Generate brand guidelines / brand kit page")

    # select (decision gate)
    p_select = sub.add_parser("select", help="Lock a name or logo selection (decision gate)")
    p_select.add_argument("target", choices=["name", "logo"], help="What to select")
    p_select.add_argument("value", help="Name string or logo index (1-based) / file path")
    p_select.add_argument("--json", action="store_true", help="Output as JSON")

    # website
    p_website = sub.add_parser("website", help="Generate a landing page")
    p_website.add_argument("--variants", action="store_true", help="Render all variants to separate files (+ index.html as best)")
    p_website.add_argument("--filenames", help="Comma-separated filenames for variants (e.g. a.html,b.html,c.html)")
    p_website.add_argument("--output-dir", help="Override output directory")

    # social
    p_social = sub.add_parser("social", help="Generate social media profile assets")
    p_social.add_argument("--platforms", help="Comma-separated platforms (default: tiktok,instagram,youtube)")

    # video
    p_video = sub.add_parser("video", help="Generate social media video content")
    p_video.add_argument("--format", choices=["teaser", "explainer", "testimonial", "fact", "founder"], help="Content format")
    p_video.add_argument("--profile", choices=["reel", "square", "web-hero", "youtube"], default="reel", help="Output profile / aspect ratio")
    p_video.add_argument("--music", help="Optional background music track path")
    p_video.add_argument("--music-dir", help="Optional folder to auto-pick a background music track from")
    p_video.add_argument("--local", action="store_true", help="Force local pipeline (skip Manus)")
    p_video.add_argument("--no-images", action="store_true", help="Skip AI image generation (local pipeline only)")
    p_video.add_argument("--no-audio", action="store_true", help="Skip audio generation (local pipeline only)")
    p_video.add_argument("--json", action="store_true", help="Output as JSON")

    # content-plan
    p_plan = sub.add_parser("content-plan", help="Generate a content production plan")
    p_plan.add_argument("--count", type=int, default=3, help="Number of videos to plan")
    p_plan.add_argument("--formats", help="Comma-separated formats (teaser,explainer,...)")
    p_plan.add_argument("--profiles", help="Comma-separated profiles (reel,square,...)")
    p_plan.add_argument("--json", action="store_true", help="Output as JSON")
    p_plan.set_defaults(func=cmd_content_plan)

    # render
    p_render = sub.add_parser("render", help="Render a single video (agent-friendly)")
    p_render.add_argument("--format", choices=["teaser", "explainer", "testimonial", "fact", "founder"], default="teaser")
    p_render.add_argument("--profile", choices=["reel", "square", "web-hero", "youtube"], default="reel")
    p_render.add_argument("--music", help="Background music track path")
    p_render.add_argument("--music-dir", help="Folder to auto-pick music from")
    p_render.add_argument("--no-images", action="store_true", help="Reuse cached images")
    p_render.add_argument("--no-audio", action="store_true", help="Reuse cached audio")
    p_render.add_argument("--json", action="store_true", help="Output as JSON")
    p_render.set_defaults(func=cmd_render)

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Evaluate the last video storyboard")
    p_eval.add_argument("--json", action="store_true", help="Output as JSON")
    p_eval.set_defaults(func=cmd_evaluate)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "name": cmd_name,
        "select": cmd_select,
        "logo": cmd_logo,
        "identity": cmd_identity,
        "kit": cmd_kit,
        "website": cmd_website,
        "social": cmd_social,
        "video": cmd_video,
        "content-plan": cmd_content_plan,
        "render": cmd_render,
        "evaluate": cmd_evaluate,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()

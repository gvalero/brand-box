"""
CLI entry point for brand-box.

Usage (recommended order):
    brand-box init <concept>      — start a new brand project
    brand-box name [--count N]    — generate name candidates
    brand-box identity            — generate colors, fonts, tone
    brand-box logo [--name NAME]  — generate logo options
    brand-box kit                 — generate brand guidelines (after locking name + logo)
    brand-box website             — generate a landing page
    brand-box social              — generate social media assets
    brand-box video [--format]    — generate social media video
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from brand_box import __version__
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


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> None:
    """Initialize a new brand project."""
    project_dir = Path(args.output or ".").resolve()
    brand_file = project_dir / "brand.json"

    if brand_file.exists() and not args.force:
        _error(f"brand.json already exists at {brand_file}. Use --force to overwrite.")
        sys.exit(1)

    project = BrandProject(concept=args.concept)
    project_dir.mkdir(parents=True, exist_ok=True)
    project.save(brand_file)
    project.ensure_output_dirs()

    _success(f"Brand project initialized: {brand_file}")
    _print(f"  Concept: {args.concept}")
    _print(f"  Output:  {project_dir / 'output'}")
    _print("")
    _print("Next steps:")
    _print("  brand-box name     — generate name candidates")
    _print("  brand-box identity — generate brand identity")
    _print("  brand-box logo     — generate logo options")
    _print("  brand-box kit      — generate brand guidelines")


def cmd_name(args: argparse.Namespace) -> None:
    """Generate brand name candidates."""
    project = _load_project()
    if not project:
        return

    from brand_box.generators.name import NameGenerator
    gen = NameGenerator()
    count = args.count or 10

    _print(f"Generating {count} name candidates for: {project.concept}")
    names = gen.generate(project.concept, count=count)
    project.name_candidates = names

    for i, name in enumerate(names, 1):
        _print(f"  {i:2d}. {name}")

    project.save(Path.cwd() / "brand.json")
    _success(f"{len(names)} name candidates saved to brand.json")


def cmd_logo(args: argparse.Namespace) -> None:
    """Generate logo options."""
    project = _load_project()
    if not project:
        return

    name = args.name or project.name or (project.name_candidates[0] if project.name_candidates else None)
    if not name:
        _error("No brand name set. Run 'brand-box name' first or pass --name.")
        sys.exit(1)

    from brand_box.generators.logo import LogoGenerator
    gen = LogoGenerator()
    dirs = project.ensure_output_dirs()
    count = args.count or 3

    _print(f"Generating {count} logo options for: {name}")
    paths = gen.generate(
        brand_name=name,
        concept=project.concept,
        identity=project.identity,
        output_dir=str(dirs["logos"]),
        count=count,
    )
    project.logo_paths = paths
    project.save(Path.cwd() / "brand.json")
    _success(f"{len(paths)} logo(s) saved to {dirs['logos']}")


def cmd_identity(args: argparse.Namespace) -> None:
    """Generate brand identity (colors, fonts, tone)."""
    project = _load_project()
    if not project:
        return

    from brand_box.generators.identity import IdentityGenerator
    gen = IdentityGenerator()

    name = project.name or (project.name_candidates[0] if project.name_candidates else "")
    _print(f"Generating brand identity for: {name or project.concept}")

    identity = gen.generate(concept=project.concept, name=name)
    project.identity = identity
    project.save(Path.cwd() / "brand.json")

    _print(f"  Primary:    {identity.primary_color}")
    _print(f"  Secondary:  {identity.secondary_color}")
    _print(f"  Accent:     {identity.accent_color}")
    _print(f"  Background: {identity.background_color}")
    _print(f"  Heading:    {identity.font_heading}")
    _print(f"  Body:       {identity.font_body}")
    _print(f"  Tone:       {identity.tone}")
    _print(f"  Tagline:    {identity.tagline}")
    _success("Brand identity saved to brand.json")


def cmd_website(args: argparse.Namespace) -> None:
    """Generate a landing page."""
    project = _load_project()
    if not project:
        return

    from brand_box.generators.website import WebsiteGenerator
    gen = WebsiteGenerator()
    dirs = project.ensure_output_dirs()

    _print("Generating landing page…")
    path = gen.generate(project=project, output_dir=str(dirs["website"]))
    project.website_path = path
    project.save(Path.cwd() / "brand.json")
    _success(f"Landing page saved to {path}")


def cmd_social(args: argparse.Namespace) -> None:
    """Generate social media assets."""
    project = _load_project()
    if not project:
        return

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

    name = project.name or (project.name_candidates[0] if project.name_candidates else "Brand")
    dirs = project.ensure_output_dirs()
    fmt_id = args.format or "teaser"

    identity_ctx = ""
    if project.identity and project.identity.tone:
        identity_ctx = (
            f"Tone: {project.identity.tone}. "
            f"Colors: {project.identity.primary_color}, {project.identity.secondary_color}, {project.identity.accent_color}. "
            f"Tagline: {project.identity.tagline}."
        )

    output_path = str(dirs["videos"] / f"video_{fmt_id}.mp4")

    # --- Try Manus first (superior quality) ---
    if not args.local:
        try:
            from brand_box.generators.manus_video import ManusVideoGenerator
            from brand_box.config import MANUS_API_KEY
            if MANUS_API_KEY:
                _print("Generating video via Manus AI…")
                manus = ManusVideoGenerator()
                logo_path = project.metadata.get("chosen_logo") or (project.logo_paths[0] if project.logo_paths else None)
                result_path = manus.generate_video(
                    brand_name=name,
                    concept=project.concept,
                    format_id=fmt_id,
                    identity_context=identity_ctx,
                    output_path=output_path,
                    logo_path=logo_path,
                )
                project.video_paths.append(result_path)
                project.save(Path.cwd() / "brand.json")
                _success(f"Video saved to {result_path}")
                return
        except Exception as e:
            _print(f"  Manus failed: {e} — falling back to local pipeline")

    # --- Local pipeline fallback ---
    from brand_box.generators.script import ScriptGenerator, BUILTIN_FORMATS
    from brand_box.generators.video import VideoAssembler

    if fmt_id not in BUILTIN_FORMATS:
        _error(f"Unknown format: {fmt_id}. Available: {list(BUILTIN_FORMATS.keys())}")
        sys.exit(1)

    # Step 1: Script
    _print(f"Generating script ({fmt_id} format)…")
    script_gen = ScriptGenerator()
    script = script_gen.generate_script(
        brand_name=name,
        concept=project.concept,
        format_id=fmt_id,
        identity_context=identity_ctx,
    )
    _print(f"  Title: {script.get('title', 'N/A')}")
    _print(f"  Segments: {len(script.get('segments', []))}")

    # Step 2: Images (unless --no-images)
    image_paths = {}
    if not args.no_images:
        _print("Generating visuals…")
        from brand_box.generators.image_backend import generate_image
        img_dir = dirs["videos"] / f"images_{fmt_id}"
        img_dir.mkdir(parents=True, exist_ok=True)

        for seg in script.get("segments", []):
            idx = seg["index"]
            desc = seg.get("visual_description", "Abstract brand visual")
            prompt = (
                f"Social media video illustration, NO TEXT, NO WORDS, NO LETTERS in the image. "
                f"Brand: {name}. Style: warm, colorful, professional. "
                f"Scene: {desc}"
            )
            img_path = str(img_dir / f"img_{idx}.png")
            try:
                generate_image(prompt, img_path)
                image_paths[idx] = img_path
                _print(f"  Image {idx + 1} ✓")
            except Exception as e:
                _print(f"  Image {idx + 1} failed: {e}")

    # Step 3: Audio (unless --no-audio)
    audio_paths: dict = {"segments": {}, "full": ""}
    if not args.no_audio:
        _print("Generating narration…")
        try:
            from brand_box.generators.audio import AudioGenerator
            audio_gen = AudioGenerator(cache_dir=str(dirs["videos"] / ".audio_cache"))
            audio_dir = dirs["videos"] / f"audio_{fmt_id}"
            audio_paths = audio_gen.generate_from_script(script, str(audio_dir))
            _print(f"  Audio segments: {len(audio_paths.get('segments', {}))}")
        except Exception as e:
            _print(f"  Audio skipped: {e}")

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

    assembler = VideoAssembler(brand_colors=colors if colors else None)
    tagline = project.identity.tagline if project.identity else ""

    try:
        result_path = assembler.assemble_video(
            script=script,
            audio_paths=audio_paths,
            image_paths=image_paths,
            output_path=output_path,
            brand_name=name,
            tagline=tagline,
        )
        project.video_paths.append(result_path)
        project.save(Path.cwd() / "brand.json")
        _success(f"Video saved to {result_path}")
    except Exception as e:
        _error(f"Video assembly failed: {e}")
        sys.exit(1)


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

    # logo
    p_logo = sub.add_parser("logo", help="Generate logo options")
    p_logo.add_argument("--name", help="Brand name (override)")
    p_logo.add_argument("--count", type=int, default=3, help="Number of logo variants")

    # identity
    sub.add_parser("identity", help="Generate brand identity (colors, fonts, tone)")

    # kit (after locking name + identity + logo)
    sub.add_parser("kit", help="Generate brand guidelines / brand kit page")

    # website
    sub.add_parser("website", help="Generate a landing page")

    # social
    p_social = sub.add_parser("social", help="Generate social media profile assets")
    p_social.add_argument("--platforms", help="Comma-separated platforms (default: tiktok,instagram,youtube)")

    # video
    p_video = sub.add_parser("video", help="Generate social media video content")
    p_video.add_argument("--format", choices=["teaser", "explainer", "testimonial", "fact", "founder"], help="Content format")
    p_video.add_argument("--local", action="store_true", help="Force local pipeline (skip Manus)")
    p_video.add_argument("--no-images", action="store_true", help="Skip AI image generation (local pipeline only)")
    p_video.add_argument("--no-audio", action="store_true", help="Skip audio generation (local pipeline only)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "name": cmd_name,
        "logo": cmd_logo,
        "identity": cmd_identity,
        "kit": cmd_kit,
        "website": cmd_website,
        "social": cmd_social,
        "video": cmd_video,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()

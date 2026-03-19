"""
Landing page generator.

This module now separates website generation into three steps:

1. strategy/spec generation
2. copy generation
3. HTML rendering

The renderer still outputs a single-file landing page so the current CLI
experience remains intact while the architecture becomes more structured.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path

from brand_box.evaluators.creative import WebsiteEvaluator
from brand_box.models.artifacts import WebsiteSpec
from brand_box.project import BrandIdentity, BrandProject

logger = logging.getLogger(__name__)


class WebsiteStrategist:
    """Create a structured WebsiteSpec from the project state."""

    def build_spec(self, project: BrandProject) -> WebsiteSpec:
        return self.build_spec_variant(project, variant="default")

    def build_spec_variant(self, project: BrandProject, variant: str = "default") -> WebsiteSpec:
        """Create a first-pass website spec for later rendering."""
        identity = project.identity or BrandIdentity()
        brief = project.brief
        name = project.active_name or project.name or "Brand"

        if brief.audience:
            audience = ", ".join(brief.audience)
        elif any(word in project.concept.lower() for word in ("parent", "child", "family", "kids")):
            audience = "Parents and families"
        else:
            audience = "Prospective customers and early adopters"

        conversion_goal = "Join the waitlist"
        if any(word in project.concept.lower() for word in ("app", "tool", "skill", "assistant")):
            conversion_goal = "Try the product or join the waitlist"

        sections = [
            {"id": "hero", "kind": "hero", "purpose": "Communicate the value proposition quickly"},
            {"id": "features", "kind": "feature_grid", "purpose": "Show the strongest product benefits"},
            {"id": "how_it_works", "kind": "process_steps", "purpose": "Reduce friction with a clear flow"},
            {"id": "proof", "kind": "social_proof", "purpose": "Build trust and emotional confidence"},
            {"id": "cta", "kind": "cta", "purpose": "Drive the primary conversion action"},
        ]

        design_tokens = {
            "colors": {
                "primary": identity.primary_color or "#5b4fc7",
                "secondary": identity.secondary_color or "#7e74d2",
                "accent": identity.accent_color or "#f6a623",
                "background": identity.background_color or "#faf7f2",
                "text": identity.text_color or "#3a3153",
            },
            "fonts": {
                "heading": identity.font_heading or "Segoe UI",
                "body": identity.font_body or "system-ui",
            },
            "tone": identity.tone or "professional, warm, trustworthy",
            "tagline": identity.tagline or "",
        }

        asset_refs = {
            "logo_path": project.active_logo_path,
            "logo_paths": list(project.logo_paths),
            "selected_logo": project.selected_logo,
        }

        spec = WebsiteSpec(
            id=f"website-{uuid.uuid4().hex[:8]}",
            audience=audience,
            conversion_goal=conversion_goal,
            visual_direction=self._derive_visual_direction(project, variant=variant),
            sections=sections,
            design_tokens=design_tokens,
            asset_refs=asset_refs,
        )
        spec.asset_refs["variant"] = variant
        return spec

    @staticmethod
    def _derive_visual_direction(project: BrandProject, variant: str = "default") -> str:
        """Infer a basic visual direction from the concept and identity."""
        identity = project.identity or BrandIdentity()
        name = project.active_name or project.name or "Brand"
        concept = project.concept.lower()
        tone = (identity.tone or "").lower()

        if variant == "editorial":
            return f"{name}: editorial, typography-led, premium landing page"
        if variant == "playful":
            return f"{name}: colorful, energetic, character-driven landing page"
        if variant == "trust":
            return f"{name}: calm, high-trust, product clarity landing page"

        if any(word in concept for word in ("story", "book", "child", "children", "kids", "family")):
            return f"{name}: warm, magical, story-led landing page"
        if any(word in tone for word in ("playful", "warm", "approachable")):
            return f"{name}: colorful, characterful, personality-driven landing page"
        return f"{name}: clean, clear, high-trust product landing page"


class WebsiteGenerator:
    """Generate a branded landing page from a BrandProject."""

    def __init__(self) -> None:
        self._openai_client = None
        self._gemini_client = None
        self._strategist = WebsiteStrategist()
        self._evaluator = WebsiteEvaluator()
        self.last_spec: WebsiteSpec | None = None
        self.last_specs: list[WebsiteSpec] = []
        self._init_clients()

    def _init_clients(self) -> None:
        from brand_box.config import (
            AZURE_OPENAI_DEPLOYMENT_GPT,
            AZURE_OPENAI_ENDPOINT,
            AZURE_OPENAI_KEY,
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
                return
            except Exception as e:
                logger.warning("Azure OpenAI init failed: %s", e)

        if GEMINI_API_KEY:
            try:
                from google import genai

                self._gemini_client = genai.Client(api_key=GEMINI_API_KEY)
                return
            except Exception as e:
                logger.warning("Gemini init failed: %s", e)

    def generate(self, project: BrandProject, output_dir: str) -> str:
        """Generate a landing page and return the path to index.html."""
        specs = self.generate_variants(project, count=3)
        spec = self.select_best_spec(specs)
        html = self._render_html(project, spec)
        self.last_spec = spec
        self.last_specs = specs

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        index_path = out / "index.html"
        index_path.write_text(html, encoding="utf-8")

        logger.info("Landing page saved to %s", index_path)
        return str(index_path)

    def generate_all(
        self,
        project: BrandProject,
        output_dir: str,
        filenames: list[str] | None = None,
    ) -> list[str]:
        """Render every variant to a separate HTML file.

        Args:
            project: The brand project.
            output_dir: Directory for output files.
            filenames: Optional list of filenames (e.g. ["a.html", "b.html", "c.html"]).
                       Defaults to variant_{n}.html if not provided.

        Returns: List of paths to generated HTML files.
        """
        specs = self.generate_variants(project, count=3)
        self.last_specs = specs
        self.last_spec = self.select_best_spec(specs)

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        default_names = [f"variant_{i + 1}.html" for i in range(len(specs))]
        names = filenames if filenames and len(filenames) >= len(specs) else default_names
        paths: list[str] = []

        for spec, name in zip(specs, names):
            html = self._render_html(project, spec)
            file_path = out / name
            file_path.write_text(html, encoding="utf-8")
            paths.append(str(file_path))
            logger.info("Landing page variant saved to %s", file_path)

        # Also write index.html as the best variant
        best_html = self._render_html(project, self.last_spec)
        index_path = out / "index.html"
        index_path.write_text(best_html, encoding="utf-8")
        paths.append(str(index_path))

        return paths

    def _generate_spec(self, project: BrandProject) -> WebsiteSpec:
        """Build a typed website spec for the current project."""
        return self._strategist.build_spec(project)

    def generate_variants(self, project: BrandProject, count: int = 3) -> list[WebsiteSpec]:
        """Generate multiple website variants and score them."""
        variants = ["default", "editorial", "trust", "playful"][: max(1, count)]
        specs: list[WebsiteSpec] = []
        for variant in variants:
            spec = self._strategist.build_spec_variant(project, variant=variant)
            spec.copy = self._generate_copy(project, spec)
            spec.review = self._evaluator.evaluate(spec)
            spec.scores = dict(spec.review.subscores)
            specs.append(spec)
        return specs

    @staticmethod
    def select_best_spec(specs: list[WebsiteSpec]) -> WebsiteSpec:
        """Pick the highest-scoring website spec."""
        if not specs:
            raise ValueError("No website specs available")
        return max(specs, key=lambda spec: (spec.review.score, spec.visual_direction))

    def _generate_copy(self, project: BrandProject, spec: WebsiteSpec) -> dict:
        """Use the LLM to generate copy for a specific website spec."""
        name = project.active_name or project.name or "Our Product"
        identity = project.identity
        tagline = identity.tagline if identity else ""
        sections = ", ".join(section.get("kind", "section") for section in spec.sections)

        prompt = f"""You are a conversion-focused copywriter. Generate landing page copy for:

Brand: {name}
Product: {project.concept}
Tagline: {tagline}
Tone: {identity.tone if identity else 'professional, warm, trustworthy'}
Target audience: {spec.audience}
Conversion goal: {spec.conversion_goal}
Visual direction: {spec.visual_direction}
Planned sections: {sections}

Return a JSON object with:
{{
  "hero_headline": "Main headline (under 10 words)",
  "hero_subheadline": "Supporting text (1-2 sentences)",
  "features": [
    {{"icon": "emoji", "title": "Feature Name", "description": "1-2 sentence description"}},
    {{"icon": "emoji", "title": "Feature Name", "description": "1-2 sentence description"}},
    {{"icon": "emoji", "title": "Feature Name", "description": "1-2 sentence description"}},
    {{"icon": "emoji", "title": "Feature Name", "description": "1-2 sentence description"}}
  ],
  "how_it_works": [
    {{"step": 1, "title": "Step Name", "description": "Brief description"}},
    {{"step": 2, "title": "Step Name", "description": "Brief description"}},
    {{"step": 3, "title": "Step Name", "description": "Brief description"}}
  ],
  "testimonials": [
    {{"quote": "What a user might say", "author": "Name, Role"}},
    {{"quote": "What a user might say", "author": "Name, Role"}},
    {{"quote": "What a user might say", "author": "Name, Role"}}
  ],
  "cta_headline": "Sign up headline",
  "cta_description": "Why they should sign up (1 sentence)",
  "cta_button_text": "Button text"
}}

Return ONLY valid JSON."""

        try:
            if self._openai_client:
                text = self._call_openai(prompt)
            elif self._gemini_client:
                text = self._call_gemini(prompt)
            else:
                return self._default_copy(name, tagline)

            return self._parse_copy(text, name, tagline)
        except Exception as e:
            logger.warning("LLM copy generation failed: %s — using defaults", e)
            return self._default_copy(name, tagline)

    def _call_openai(self, prompt: str) -> str:
        response = self._openai_client.chat.completions.create(
            model=self._openai_deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
        )
        return response.choices[0].message.content

    def _call_gemini(self, prompt: str) -> str:
        response = self._gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text

    @staticmethod
    def _parse_copy(text: str, name: str, tagline: str) -> dict:
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return WebsiteGenerator._default_copy(name, tagline)

    @staticmethod
    def _default_copy(name: str, tagline: str) -> dict:
        return {
            "hero_headline": tagline or f"Welcome to {name}",
            "hero_subheadline": f"Discover what {name} can do for you.",
            "features": [
                {"icon": "✨", "title": "Feature One", "description": "A great feature."},
                {"icon": "🚀", "title": "Feature Two", "description": "Another great feature."},
                {"icon": "💡", "title": "Feature Three", "description": "Yet another great feature."},
                {"icon": "❤️", "title": "Feature Four", "description": "One more great feature."},
            ],
            "how_it_works": [
                {"step": 1, "title": "Sign Up", "description": "Create your free account."},
                {"step": 2, "title": "Get Started", "description": "Set up your profile."},
                {"step": 3, "title": "Enjoy", "description": "Start using the product."},
            ],
            "testimonials": [
                {"quote": "This product changed everything.", "author": "Happy User"},
                {"quote": "I can't imagine going back.", "author": "Another Fan"},
                {"quote": "Absolutely love it!", "author": "Satisfied Customer"},
            ],
            "cta_headline": "Ready to get started?",
            "cta_description": "Join our waitlist and be the first to know when we launch.",
            "cta_button_text": "Join the Waitlist 🎉",
        }

    def _render_html(self, project: BrandProject, spec: WebsiteSpec) -> str:
        """Render the full HTML page from a typed website spec."""
        name = project.active_name or project.name or "Brand"
        identity = project.identity or BrandIdentity()
        copy = spec.copy or self._default_copy(name, identity.tagline or "")

        colors = spec.design_tokens.get("colors", {})
        fonts = spec.design_tokens.get("fonts", {})

        primary = colors.get("primary") or identity.primary_color or "#5b4fc7"
        secondary = colors.get("secondary") or identity.secondary_color or "#7e74d2"
        accent = colors.get("accent") or identity.accent_color or "#f6a623"
        bg = colors.get("background") or identity.background_color or "#faf7f2"
        text_color = colors.get("text") or identity.text_color or "#3a3153"
        font_heading = fonts.get("heading") or identity.font_heading or "Segoe UI"
        font_body = fonts.get("body") or identity.font_body or "system-ui"

        def lighten(hex_color: str, factor: float = 0.2) -> str:
            h = hex_color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            r = min(255, int(r + (255 - r) * factor))
            g = min(255, int(g + (255 - g) * factor))
            b = min(255, int(b + (255 - b) * factor))
            return f"#{r:02x}{g:02x}{b:02x}"

        primary_light = lighten(primary)
        accent_hover = lighten(accent, -0.1)
        text_light = lighten(text_color, 0.3)
        border_color = lighten(primary, 0.7)

        features_html = ""
        for feature in copy.get("features", []):
            features_html += f"""
            <div class="prop-card fade-in">
                <span class="prop-icon">{feature['icon']}</span>
                <h3>{feature['title']}</h3>
                <p>{feature['description']}</p>
            </div>"""

        steps_html = ""
        steps = copy.get("how_it_works", [])
        for i, step in enumerate(steps):
            arrow = '<span class="step-arrow" aria-hidden="true">→</span>' if i < len(steps) - 1 else ""
            steps_html += f"""
            <div class="step-card fade-in">
                <span class="step-num">{step['step']}</span>
                <h3>{step['title']}</h3>
                <p>{step['description']}</p>
            </div>{arrow}"""

        testimonials_html = ""
        for testimonial in copy.get("testimonials", []):
            testimonials_html += f"""
            <div class="testimonial-card fade-in">
                <div class="stars">⭐⭐⭐⭐⭐</div>
                <p class="quote">"{testimonial['quote']}"</p>
                <p class="author">— {testimonial['author']}</p>
            </div>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name}</title>
<style>
:root {{
    --clr-primary: {primary};
    --clr-primary-light: {primary_light};
    --clr-secondary: {secondary};
    --clr-accent: {accent};
    --clr-accent-hover: {accent_hover};
    --clr-bg: {bg};
    --clr-bg-alt: #fff;
    --clr-text: {text_color};
    --clr-text-light: {text_light};
    --clr-border: {border_color};
    --radius: 12px;
    --shadow-sm: 0 2px 8px rgba(0,0,0,.06);
    --shadow-md: 0 6px 24px rgba(0,0,0,.10);
    --max-w: 1120px;
    --font-heading: '{font_heading}', system-ui, sans-serif;
    --font-body: '{font_body}', system-ui, sans-serif;
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ scroll-behavior: smooth; }}
body {{ font-family: var(--font-body); color: var(--clr-text); background: var(--clr-bg); line-height: 1.6; }}
h1, h2, h3 {{ font-family: var(--font-heading); }}

.nav {{
    position: sticky; top: 0; z-index: 100;
    background: rgba(255,255,255,.92); backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--clr-border);
    padding: 16px 32px;
    display: flex; align-items: center; justify-content: space-between;
    max-width: var(--max-w); margin: 0 auto;
}}
.nav-brand {{ font-family: var(--font-heading); font-size: 1.3rem; font-weight: 700; color: var(--clr-primary); text-decoration: none; }}
.nav-cta {{
    background: var(--clr-accent); color: #fff; border: none; padding: 10px 24px;
    border-radius: var(--radius); font-weight: 600; cursor: pointer;
    text-decoration: none; font-size: .95rem;
    transition: background .2s;
}}
.nav-cta:hover {{ background: var(--clr-accent-hover); }}

.hero {{
    text-align: center; padding: 100px 24px 80px;
    background:
        radial-gradient(circle at top left, {lighten(accent, 0.75)} 0%, transparent 28%),
        linear-gradient(175deg, {lighten(primary, 0.85)} 0%, var(--clr-bg) 60%);
}}
.hero-kicker {{
    display: inline-block;
    padding: 8px 14px;
    border-radius: 999px;
    background: rgba(255,255,255,.8);
    border: 1px solid var(--clr-border);
    color: var(--clr-primary);
    font-size: .85rem;
    font-weight: 700;
    margin-bottom: 18px;
}}
.hero h1 {{ font-size: 2.8rem; margin-bottom: 16px; color: var(--clr-primary); }}
.hero p {{ font-size: 1.2rem; color: var(--clr-text-light); max-width: 600px; margin: 0 auto 32px; }}
.hero-cta {{
    display: inline-block; background: var(--clr-accent); color: #fff;
    padding: 16px 40px; border-radius: var(--radius); font-size: 1.1rem;
    font-weight: 700; text-decoration: none; transition: background .2s, transform .2s;
}}
.hero-cta:hover {{ background: var(--clr-accent-hover); transform: translateY(-2px); }}

section {{ padding: 80px 24px; max-width: var(--max-w); margin: 0 auto; }}
.section-title {{ text-align: center; font-size: 2rem; margin-bottom: 48px; color: var(--clr-primary); }}

.props-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 32px;
}}
.prop-card {{
    background: var(--clr-bg-alt); border: 1px solid var(--clr-border);
    border-radius: var(--radius); padding: 32px 24px; text-align: center;
    transition: transform .25s, box-shadow .25s;
}}
.prop-card:hover {{ transform: translateY(-4px); box-shadow: var(--shadow-md); }}
.prop-icon {{ font-size: 2.5rem; display: block; margin-bottom: 12px; }}
.prop-card h3 {{ margin-bottom: 8px; color: var(--clr-primary); }}
.prop-card p {{ color: var(--clr-text-light); font-size: .95rem; }}

.steps {{
    display: flex; align-items: flex-start; justify-content: center;
    gap: 16px; flex-wrap: wrap;
}}
.step-card {{
    background: var(--clr-bg-alt); border: 1px solid var(--clr-border);
    border-radius: var(--radius); padding: 32px 24px; text-align: center;
    flex: 1; min-width: 200px; max-width: 300px;
}}
.step-num {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 48px; height: 48px; border-radius: 50%;
    background: var(--clr-primary); color: #fff; font-weight: 700;
    font-size: 1.2rem; margin-bottom: 12px;
}}
.step-arrow {{ font-size: 2rem; color: var(--clr-primary); align-self: center; margin-top: 30px; }}

.testimonials-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 32px;
}}
.testimonial-card {{
    background: var(--clr-bg-alt); border: 1px solid var(--clr-border);
    border-radius: var(--radius); padding: 32px; text-align: center;
}}
.stars {{ margin-bottom: 12px; }}
.quote {{ font-style: italic; color: var(--clr-text); margin-bottom: 12px; }}
.author {{ color: var(--clr-text-light); font-size: .9rem; }}

.cta-section {{
    text-align: center; padding: 80px 24px;
    background: linear-gradient(175deg, var(--clr-bg) 0%, {lighten(primary, 0.85)} 100%);
}}
.cta-section h2 {{ font-size: 2rem; margin-bottom: 12px; color: var(--clr-primary); }}
.cta-section p {{ color: var(--clr-text-light); margin-bottom: 32px; }}
.signup-form {{
    display: flex; gap: 12px; justify-content: center; max-width: 500px; margin: 0 auto;
}}
.signup-form input {{
    flex: 1; padding: 14px 20px; border: 1px solid var(--clr-border);
    border-radius: var(--radius); font-size: 1rem; outline: none;
    transition: border-color .2s;
}}
.signup-form input:focus {{ border-color: var(--clr-primary); }}
.signup-form button {{
    background: var(--clr-accent); color: #fff; border: none;
    padding: 14px 32px; border-radius: var(--radius);
    font-weight: 700; font-size: 1rem; cursor: pointer;
    transition: background .2s;
    white-space: nowrap;
}}
.signup-form button:hover {{ background: var(--clr-accent-hover); }}

footer {{
    text-align: center; padding: 32px 24px;
    color: var(--clr-text-light); font-size: .85rem;
    border-top: 1px solid var(--clr-border);
}}

.fade-in {{
    opacity: 0; transform: translateY(28px);
    transition: opacity .7s ease, transform .7s ease;
}}
.fade-in.visible {{ opacity: 1; transform: translateY(0); }}

@media (max-width: 600px) {{
    .hero h1 {{ font-size: 2rem; }}
    .signup-form {{ flex-direction: column; }}
    .step-arrow {{ display: none; }}
    section {{ padding: 48px 16px; }}
}}
</style>
</head>
<body>

<nav class="nav" role="navigation">
    <a href="#" class="nav-brand">{name}</a>
    <a href="#signup" class="nav-cta">{copy.get('cta_button_text', 'Join Waitlist')}</a>
</nav>

<section class="hero">
    <div class="hero-kicker fade-in">{spec.visual_direction}</div>
    <h1 class="fade-in">{copy.get('hero_headline', f'Welcome to {name}')}</h1>
    <p class="fade-in">{copy.get('hero_subheadline', '')}</p>
    <a href="#signup" class="hero-cta fade-in">{copy.get('cta_button_text', 'Get Started')}</a>
</section>

<section>
    <h2 class="section-title fade-in">Why {name}?</h2>
    <div class="props-grid">{features_html}
    </div>
</section>

<section>
    <h2 class="section-title fade-in">How It Works</h2>
    <div class="steps">{steps_html}
    </div>
</section>

<section>
    <h2 class="section-title fade-in">What People Are Saying</h2>
    <div class="testimonials-grid">{testimonials_html}
    </div>
</section>

<section class="cta-section" id="signup">
    <h2 class="fade-in">{copy.get('cta_headline', 'Ready to get started?')}</h2>
    <p class="fade-in">{copy.get('cta_description', 'Join our waitlist today.')}</p>
    <form class="signup-form fade-in" action="https://formspree.io/f/placeholder" method="POST">
        <input type="email" name="email" placeholder="you@example.com" required aria-label="Email address">
        <button type="submit">{copy.get('cta_button_text', 'Join the Waitlist 🎉')}</button>
    </form>
    <noscript><p style="margin-top:16px">JavaScript is disabled. Email us directly to join.</p></noscript>
</section>

<footer>
    <p>&copy; 2026 {name}. All rights reserved.</p>
</footer>

<script>
const obs = new IntersectionObserver((entries) => {{
    entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }});
}}, {{ threshold: 0.15 }});
document.querySelectorAll('.fade-in').forEach(el => obs.observe(el));
</script>
</body>
</html>"""

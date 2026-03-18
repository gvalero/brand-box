"""
Landing page generator.

Creates a responsive, single-page HTML landing page from brand identity.
Uses an LLM to generate copy, then fills a template with brand colors,
fonts, and content.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from brand_box.project import BrandProject, BrandIdentity

logger = logging.getLogger(__name__)


class WebsiteGenerator:
    """Generate a branded landing page from a BrandProject."""

    def __init__(self) -> None:
        self._openai_client = None
        self._gemini_client = None
        self._init_clients()

    def _init_clients(self) -> None:
        from brand_box.config import (
            AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY,
            AZURE_OPENAI_DEPLOYMENT_GPT, GEMINI_API_KEY,
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
        copy = self._generate_copy(project)
        html = self._render_html(project, copy)

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        index_path = out / "index.html"
        index_path.write_text(html, encoding="utf-8")

        logger.info("Landing page saved to %s", index_path)
        return str(index_path)

    def _generate_copy(self, project: BrandProject) -> dict:
        """Use LLM to generate page copy."""
        name = project.name or "Our Product"
        identity = project.identity
        tagline = identity.tagline if identity else ""

        prompt = f"""You are a conversion-focused copywriter. Generate landing page copy for:

Brand: {name}
Product: {project.concept}
Tagline: {tagline}
Tone: {identity.tone if identity else 'professional, warm, trustworthy'}

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

    def _render_html(self, project: BrandProject, copy: dict) -> str:
        """Render the full HTML page."""
        name = project.name or "Brand"
        identity = project.identity or BrandIdentity()

        primary = identity.primary_color or "#5b4fc7"
        secondary = identity.secondary_color or "#7e74d2"
        accent = identity.accent_color or "#f6a623"
        bg = identity.background_color or "#faf7f2"
        text_color = identity.text_color or "#3a3153"
        font_heading = identity.font_heading or "Segoe UI"
        font_body = identity.font_body or "system-ui"

        # Derive lighter primary
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
        for f in copy.get("features", []):
            features_html += f"""
            <div class="prop-card fade-in">
                <span class="prop-icon">{f['icon']}</span>
                <h3>{f['title']}</h3>
                <p>{f['description']}</p>
            </div>"""

        steps_html = ""
        steps = copy.get("how_it_works", [])
        for i, s in enumerate(steps):
            arrow = '<span class="step-arrow" aria-hidden="true">→</span>' if i < len(steps) - 1 else ""
            steps_html += f"""
            <div class="step-card fade-in">
                <span class="step-num">{s['step']}</span>
                <h3>{s['title']}</h3>
                <p>{s['description']}</p>
            </div>{arrow}"""

        testimonials_html = ""
        for t in copy.get("testimonials", []):
            testimonials_html += f"""
            <div class="testimonial-card fade-in">
                <div class="stars">⭐⭐⭐⭐⭐</div>
                <p class="quote">"{t['quote']}"</p>
                <p class="author">— {t['author']}</p>
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

/* Nav */
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

/* Hero */
.hero {{
    text-align: center; padding: 100px 24px 80px;
    background: linear-gradient(175deg, {lighten(primary, 0.85)} 0%, var(--clr-bg) 60%);
}}
.hero h1 {{ font-size: 2.8rem; margin-bottom: 16px; color: var(--clr-primary); }}
.hero p {{ font-size: 1.2rem; color: var(--clr-text-light); max-width: 600px; margin: 0 auto 32px; }}
.hero-cta {{
    display: inline-block; background: var(--clr-accent); color: #fff;
    padding: 16px 40px; border-radius: var(--radius); font-size: 1.1rem;
    font-weight: 700; text-decoration: none; transition: background .2s, transform .2s;
}}
.hero-cta:hover {{ background: var(--clr-accent-hover); transform: translateY(-2px); }}

/* Sections */
section {{ padding: 80px 24px; max-width: var(--max-w); margin: 0 auto; }}
.section-title {{ text-align: center; font-size: 2rem; margin-bottom: 48px; color: var(--clr-primary); }}

/* Features */
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

/* How it works */
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

/* Testimonials */
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

/* CTA section */
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

/* Footer */
footer {{
    text-align: center; padding: 32px 24px;
    color: var(--clr-text-light); font-size: .85rem;
    border-top: 1px solid var(--clr-border);
}}

/* Animations */
.fade-in {{
    opacity: 0; transform: translateY(28px);
    transition: opacity .7s ease, transform .7s ease;
}}
.fade-in.visible {{ opacity: 1; transform: translateY(0); }}

/* Responsive */
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

"""
Brand kit / brand guidelines generator.

Creates a self-contained HTML brand guidelines page that includes:
  - Logo display (on light & dark backgrounds)
  - Color palette with hex/RGB swatches
  - Typography samples
  - Tone of voice & brand personality
  - Usage do's and don'ts

Logos are embedded as base64 so the HTML file is fully portable.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path
from typing import Optional

from brand_box.project import BrandProject, BrandIdentity

logger = logging.getLogger(__name__)


class KitGenerator:
    """Generate a brand guidelines HTML page from a BrandProject."""

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, project: BrandProject, output_dir: str) -> str:
        """Generate brand guidelines and return the path to the HTML file."""
        guidelines = self._generate_guidelines(project)
        logos_b64 = self._encode_logos(project)
        html = self._render_html(project, guidelines, logos_b64)

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "brand-guidelines.html"
        path.write_text(html, encoding="utf-8")
        logger.info("Brand guidelines saved to %s", path)
        return str(path)

    # ------------------------------------------------------------------
    # LLM-generated guidelines
    # ------------------------------------------------------------------

    def _generate_guidelines(self, project: BrandProject) -> dict:
        name = project.name or "Brand"
        identity = project.identity

        prompt = f"""You are a brand strategist. Generate brand usage guidelines for:

Brand: {name}
Product: {project.concept}
Tagline: {identity.tagline if identity else ''}
Tone: {identity.tone if identity else 'professional'}
Colors: primary {identity.primary_color}, secondary {identity.secondary_color}, accent {identity.accent_color}
Fonts: {identity.font_heading} (headings), {identity.font_body} (body)

Return a JSON object with:
{{
  "brand_story": "2-3 sentence brand mission/story",
  "personality_traits": ["trait1", "trait2", "trait3", "trait4", "trait5"],
  "voice_guidelines": "2-3 sentences describing the brand voice",
  "writing_examples": {{
    "do": ["Example of good copy", "Another good example", "Third example"],
    "dont": ["Example of bad copy", "Another bad example", "Third example"]
  }},
  "logo_guidelines": {{
    "do": ["Use on clean backgrounds", "Maintain minimum clear space", "Use approved colors only"],
    "dont": ["Don't stretch or distort", "Don't place on busy backgrounds", "Don't change the colors"]
  }},
  "color_usage": {{
    "primary_usage": "When to use the primary color",
    "secondary_usage": "When to use the secondary color",
    "accent_usage": "When to use the accent color"
  }}
}}

Return ONLY valid JSON."""

        try:
            if self._openai_client:
                text = self._call_openai(prompt)
            elif self._gemini_client:
                text = self._call_gemini(prompt)
            else:
                return self._default_guidelines(name)
            return self._parse_json(text, name)
        except Exception as e:
            logger.warning("LLM guidelines generation failed: %s — using defaults", e)
            return self._default_guidelines(name)

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

    def _parse_json(self, text: str, name: str) -> dict:
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return self._default_guidelines(name)

    @staticmethod
    def _default_guidelines(name: str) -> dict:
        return {
            "brand_story": f"{name} is committed to delivering an exceptional experience. Our brand represents quality, trust, and innovation.",
            "personality_traits": ["Approachable", "Trustworthy", "Innovative", "Playful", "Warm"],
            "voice_guidelines": f"{name} speaks in a warm, conversational tone. We're friendly but not overly casual — helpful but not condescending.",
            "writing_examples": {
                "do": [
                    "Let's make something magical together!",
                    "Simple, joyful, and made for you.",
                    "We're here to help, every step of the way.",
                ],
                "dont": [
                    "BUY NOW!!! LIMITED TIME ONLY!!!",
                    "Our disruptive synergy leverages paradigm shifts.",
                    "You need this or you're missing out.",
                ],
            },
            "logo_guidelines": {
                "do": [
                    "Use on clean, uncluttered backgrounds",
                    "Maintain minimum clear space equal to the logo height",
                    "Use only the approved color variants",
                ],
                "dont": [
                    "Don't stretch, skew, or distort the logo",
                    "Don't place on busy photographic backgrounds",
                    "Don't alter the colors or add effects",
                ],
            },
            "color_usage": {
                "primary_usage": "Headings, buttons, key UI elements, and brand anchors",
                "secondary_usage": "Supporting elements, backgrounds, and secondary actions",
                "accent_usage": "Call-to-action buttons, highlights, and interactive elements",
            },
        }

    # ------------------------------------------------------------------
    # Logo embedding
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_logos(project: BrandProject) -> list[dict]:
        """Read logo files and encode as base64 data URIs."""
        logos = []
        for i, path_str in enumerate(project.logo_paths):
            path = Path(path_str)
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            mime = "image/png" if suffix == ".png" else "image/jpeg"
            try:
                data = path.read_bytes()
                b64 = base64.b64encode(data).decode("ascii")
                logos.append({
                    "index": i + 1,
                    "data_uri": f"data:{mime};base64,{b64}",
                    "filename": path.name,
                    "size_kb": len(data) // 1024,
                })
            except Exception as e:
                logger.warning("Could not read logo %s: %s", path, e)
        return logos

    # ------------------------------------------------------------------
    # HTML rendering
    # ------------------------------------------------------------------

    def _render_html(self, project: BrandProject, guidelines: dict, logos: list[dict]) -> str:
        name = project.name or "Brand"
        identity = project.identity or BrandIdentity()

        primary = identity.primary_color or "#5b4fc7"
        secondary = identity.secondary_color or "#7e74d2"
        accent = identity.accent_color or "#6CCFF6"
        bg = identity.background_color or "#faf7f2"
        text_color = identity.text_color or "#333333"
        font_heading = identity.font_heading or "Segoe UI"
        font_body = identity.font_body or "system-ui"
        tagline = identity.tagline or ""
        tone = identity.tone or ""

        colors = [
            ("Primary", primary, identity.primary_color, guidelines.get("color_usage", {}).get("primary_usage", "")),
            ("Secondary", secondary, identity.secondary_color, guidelines.get("color_usage", {}).get("secondary_usage", "")),
            ("Accent", accent, identity.accent_color, guidelines.get("color_usage", {}).get("accent_usage", "")),
            ("Background", bg, identity.background_color, "Page backgrounds and content areas"),
            ("Text", text_color, identity.text_color, "Body text and readable content"),
        ]

        # Build color swatches HTML
        swatches_html = ""
        for label, hex_val, _raw, usage in colors:
            h = hex_val.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            # Choose white or dark text for contrast
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            fg = "#ffffff" if lum < 140 else "#222222"
            swatches_html += f"""
                <div class="swatch">
                    <div class="swatch-color" style="background:{hex_val};color:{fg}">
                        <span class="swatch-label">{label}</span>
                    </div>
                    <div class="swatch-info">
                        <code>{hex_val.upper()}</code>
                        <span class="swatch-rgb">RGB({r}, {g}, {b})</span>
                        <p class="swatch-usage">{usage}</p>
                    </div>
                </div>"""

        # Build logos HTML
        logos_html = ""
        for logo in logos:
            logos_html += f"""
                <div class="logo-variant">
                    <div class="logo-light">
                        <img src="{logo['data_uri']}" alt="{name} logo variant {logo['index']}">
                    </div>
                    <div class="logo-dark">
                        <img src="{logo['data_uri']}" alt="{name} logo variant {logo['index']} on dark">
                    </div>
                    <p class="logo-caption">Variant {logo['index']} — {logo['filename']} ({logo['size_kb']}KB)</p>
                </div>"""

        # Personality traits
        traits = guidelines.get("personality_traits", [])
        traits_html = "".join(f'<span class="trait-tag">{t}</span>' for t in traits)

        # Logo do's and don'ts
        logo_gl = guidelines.get("logo_guidelines", {})
        logo_dos = "".join(f"<li>✅ {d}</li>" for d in logo_gl.get("do", []))
        logo_donts = "".join(f"<li>❌ {d}</li>" for d in logo_gl.get("dont", []))

        # Writing do's and don'ts
        writing = guidelines.get("writing_examples", {})
        writing_dos = "".join(f'<li class="do-item">"{d}"</li>' for d in writing.get("do", []))
        writing_donts = "".join(f'<li class="dont-item">"{d}"</li>' for d in writing.get("dont", []))

        def lighten(hex_color: str, factor: float = 0.2) -> str:
            h = hex_color.lstrip("#")
            rv, gv, bv = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            rv = min(255, int(rv + (255 - rv) * factor))
            gv = min(255, int(gv + (255 - gv) * factor))
            bv = min(255, int(bv + (255 - bv) * factor))
            return f"#{rv:02x}{gv:02x}{bv:02x}"

        primary_light = lighten(primary, 0.85)
        border = lighten(primary, 0.7)

        # Google Fonts import for heading/body fonts
        font_import = ""
        gfonts = []
        for f in [font_heading, font_body]:
            if f and f not in ("Segoe UI", "system-ui", "Arial", "Helvetica"):
                gfonts.append(f.replace(" ", "+"))
        if gfonts:
            families = "&family=".join(f"{f}:wght@400;600;700" for f in set(gfonts))
            font_import = f'<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family={families}&display=swap" rel="stylesheet">'

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} — Brand Guidelines</title>
{font_import}
<style>
:root {{
    --primary: {primary};
    --secondary: {secondary};
    --accent: {accent};
    --bg: {bg};
    --text: {text_color};
    --border: {border};
    --primary-light: {primary_light};
    --font-heading: '{font_heading}', system-ui, sans-serif;
    --font-body: '{font_body}', system-ui, sans-serif;
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ scroll-behavior: smooth; }}
body {{ font-family: var(--font-body); color: var(--text); background: #fff; line-height: 1.7; }}
h1, h2, h3, h4 {{ font-family: var(--font-heading); }}

/* Cover */
.cover {{
    background: linear-gradient(135deg, var(--primary) 0%, {lighten(primary, 0.3)} 100%);
    color: #fff;
    padding: 120px 40px 100px;
    text-align: center;
}}
.cover h1 {{
    font-size: 3.2rem;
    margin-bottom: 8px;
    letter-spacing: -0.02em;
}}
.cover .subtitle {{
    font-size: 1.4rem;
    opacity: 0.9;
    font-weight: 300;
    margin-bottom: 16px;
}}
.cover .tagline {{
    font-size: 1.1rem;
    opacity: 0.75;
    font-style: italic;
}}

/* Navigation */
.toc {{
    position: sticky;
    top: 0;
    z-index: 100;
    background: rgba(255,255,255,0.95);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border);
    padding: 14px 32px;
    display: flex;
    gap: 24px;
    justify-content: center;
    flex-wrap: wrap;
}}
.toc a {{
    color: var(--primary);
    text-decoration: none;
    font-size: 0.9rem;
    font-weight: 600;
    padding: 4px 0;
    border-bottom: 2px solid transparent;
    transition: border-color 0.2s;
}}
.toc a:hover {{ border-color: var(--accent); }}

/* Sections */
.section {{
    max-width: 960px;
    margin: 0 auto;
    padding: 80px 32px;
    border-bottom: 1px solid #eee;
}}
.section:last-child {{ border-bottom: none; }}
.section-num {{
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: var(--accent);
    font-weight: 700;
    margin-bottom: 8px;
}}
.section h2 {{
    font-size: 2rem;
    color: var(--primary);
    margin-bottom: 24px;
}}

/* Brand Story */
.brand-story {{
    font-size: 1.15rem;
    line-height: 1.8;
    max-width: 700px;
}}
.traits {{
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 24px;
}}
.trait-tag {{
    background: var(--primary-light);
    color: var(--primary);
    padding: 6px 18px;
    border-radius: 100px;
    font-size: 0.85rem;
    font-weight: 600;
}}

/* Logos */
.logos-grid {{
    display: flex;
    flex-direction: column;
    gap: 48px;
}}
.logo-variant {{
    text-align: center;
}}
.logo-variant img {{
    max-width: 280px;
    max-height: 200px;
    object-fit: contain;
}}
.logo-light, .logo-dark {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 40px;
    border-radius: 16px;
    margin: 8px;
    min-width: 320px;
    min-height: 220px;
}}
.logo-light {{
    background: #f8f8f8;
    border: 1px solid #e0e0e0;
}}
.logo-dark {{
    background: #1a1a2e;
    border: 1px solid #333;
}}
.logo-caption {{
    margin-top: 12px;
    font-size: 0.85rem;
    color: #999;
}}

/* Logo guidelines */
.guidelines-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 32px;
    margin-top: 32px;
}}
.guidelines-col h3 {{
    font-size: 1.1rem;
    margin-bottom: 16px;
    color: var(--primary);
}}
.guidelines-col ul {{
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 10px;
}}
.guidelines-col li {{
    font-size: 0.95rem;
    padding: 10px 16px;
    background: #f9f9f9;
    border-radius: 8px;
    border-left: 3px solid var(--accent);
}}

/* Color Palette */
.palette {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 20px;
}}
.swatch {{
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid #e8e8e8;
    transition: transform 0.2s;
}}
.swatch:hover {{ transform: translateY(-3px); }}
.swatch-color {{
    height: 120px;
    display: flex;
    align-items: flex-end;
    padding: 12px 16px;
}}
.swatch-label {{
    font-weight: 700;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
.swatch-info {{
    padding: 14px 16px;
    background: #fff;
}}
.swatch-info code {{
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--text);
}}
.swatch-rgb {{
    display: block;
    font-size: 0.8rem;
    color: #999;
    margin-top: 2px;
}}
.swatch-usage {{
    font-size: 0.8rem;
    color: #777;
    margin-top: 8px;
    line-height: 1.4;
}}

/* Typography */
.type-specimen {{
    display: flex;
    flex-direction: column;
    gap: 40px;
}}
.type-block {{
    padding: 32px;
    background: #fafafa;
    border-radius: 12px;
    border: 1px solid #eee;
}}
.type-block h3 {{
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--accent);
    margin-bottom: 16px;
}}
.type-sample-xl {{ font-size: 2.4rem; font-weight: 700; line-height: 1.2; margin-bottom: 8px; }}
.type-sample-lg {{ font-size: 1.6rem; font-weight: 600; line-height: 1.3; margin-bottom: 8px; }}
.type-sample-md {{ font-size: 1.1rem; line-height: 1.6; margin-bottom: 8px; }}
.type-sample-sm {{ font-size: 0.9rem; line-height: 1.6; color: #666; }}
.type-meta {{
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #e0e0e0;
    font-size: 0.8rem;
    color: #999;
}}

/* Voice & Tone */
.voice-text {{
    font-size: 1.05rem;
    line-height: 1.8;
    max-width: 700px;
    margin-bottom: 32px;
}}
.examples-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 32px;
}}
.examples-col h3 {{
    font-size: 1rem;
    margin-bottom: 16px;
}}
.examples-col ul {{
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 8px;
}}
.do-item {{
    padding: 10px 16px;
    background: #eafbea;
    border-radius: 8px;
    border-left: 3px solid #4caf50;
    font-size: 0.9rem;
}}
.dont-item {{
    padding: 10px 16px;
    background: #fdeaea;
    border-radius: 8px;
    border-left: 3px solid #e53935;
    font-size: 0.9rem;
}}

/* Footer */
.kit-footer {{
    text-align: center;
    padding: 40px;
    color: #aaa;
    font-size: 0.8rem;
}}

/* Responsive */
@media (max-width: 700px) {{
    .cover h1 {{ font-size: 2.2rem; }}
    .section {{ padding: 48px 20px; }}
    .guidelines-grid, .examples-grid {{ grid-template-columns: 1fr; }}
    .logo-light, .logo-dark {{ min-width: unset; width: 100%; }}
    .palette {{ grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }}
}}
</style>
</head>
<body>

<!-- Cover -->
<header class="cover">
    <h1>{name}</h1>
    <p class="subtitle">Brand Guidelines</p>
    {"<p class='tagline'>" + tagline + "</p>" if tagline else ""}
</header>

<!-- Table of Contents -->
<nav class="toc">
    <a href="#story">Brand Story</a>
    <a href="#logos">Logo</a>
    <a href="#colors">Colors</a>
    <a href="#typography">Typography</a>
    <a href="#voice">Voice &amp; Tone</a>
</nav>

<!-- 01 — Brand Story -->
<section class="section" id="story">
    <p class="section-num">01</p>
    <h2>Brand Story</h2>
    <p class="brand-story">{guidelines.get('brand_story', '')}</p>
    <div class="traits">{traits_html}</div>
</section>

<!-- 02 — Logo -->
<section class="section" id="logos">
    <p class="section-num">02</p>
    <h2>Logo</h2>
    <p>Our logo is the primary visual identifier. Always use approved files and maintain proper clear space.</p>
    <div class="logos-grid" style="margin-top:32px">
        {logos_html if logos_html else '<p style="color:#999;font-style:italic">No logos generated yet. Run <code>brand-box logo</code> first.</p>'}
    </div>
    <div class="guidelines-grid">
        <div class="guidelines-col">
            <h3>Do</h3>
            <ul>{logo_dos}</ul>
        </div>
        <div class="guidelines-col">
            <h3>Don't</h3>
            <ul>{logo_donts}</ul>
        </div>
    </div>
</section>

<!-- 03 — Color Palette -->
<section class="section" id="colors">
    <p class="section-num">03</p>
    <h2>Color Palette</h2>
    <p style="margin-bottom:32px">These are the official brand colors. Use them consistently across all touchpoints.</p>
    <div class="palette">{swatches_html}</div>
</section>

<!-- 04 — Typography -->
<section class="section" id="typography">
    <p class="section-num">04</p>
    <h2>Typography</h2>
    <div class="type-specimen">
        <div class="type-block">
            <h3>Heading Font</h3>
            <p class="type-sample-xl" style="font-family:var(--font-heading)">The quick brown fox</p>
            <p class="type-sample-lg" style="font-family:var(--font-heading)">Jumps over the lazy dog</p>
            <p class="type-sample-md" style="font-family:var(--font-heading)">ABCDEFGHIJKLMNOPQRSTUVWXYZ</p>
            <p class="type-sample-sm" style="font-family:var(--font-heading)">abcdefghijklmnopqrstuvwxyz 0123456789</p>
            <p class="type-meta"><strong>{font_heading}</strong> — Used for headings, titles, and display text. Weights: 400, 600, 700.</p>
        </div>
        <div class="type-block">
            <h3>Body Font</h3>
            <p class="type-sample-lg" style="font-family:var(--font-body)">Readable at every size</p>
            <p class="type-sample-md" style="font-family:var(--font-body)">
                Good typography is invisible. It lets the message speak for itself
                while guiding the reader naturally through the content. Our body font
                is chosen for clarity, warmth, and readability.
            </p>
            <p class="type-sample-sm" style="font-family:var(--font-body)">ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz 0123456789</p>
            <p class="type-meta"><strong>{font_body}</strong> — Used for body text, descriptions, and UI elements. Weights: 400, 600.</p>
        </div>
    </div>
</section>

<!-- 05 — Voice & Tone -->
<section class="section" id="voice">
    <p class="section-num">05</p>
    <h2>Voice &amp; Tone</h2>
    {"<p style='margin-bottom:16px'><strong>Our tone:</strong> " + tone + "</p>" if tone else ""}
    <p class="voice-text">{guidelines.get('voice_guidelines', '')}</p>
    <div class="examples-grid">
        <div class="examples-col">
            <h3>✅ Do write like this</h3>
            <ul>{writing_dos}</ul>
        </div>
        <div class="examples-col">
            <h3>❌ Don't write like this</h3>
            <ul>{writing_donts}</ul>
        </div>
    </div>
</section>

<footer class="kit-footer">
    <p>{name} Brand Guidelines &middot; Generated by brand-box</p>
</footer>

</body>
</html>"""

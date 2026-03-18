# brand-box

A CLI toolkit for generating complete brand identities from a concept description.

Takes a project idea and produces: **name → logo → brand identity → landing page → social media assets → video content**.

## Quick Start

```bash
pip install -e .
brand-box init "LiveWord - real-time translation for live events"
```

## Commands

| Command | Description |
|---------|-------------|
| `brand-box init <concept>` | Initialize a new brand project |
| `brand-box name` | Generate name candidates |
| `brand-box logo` | Generate logo options |
| `brand-box identity` | Generate color palette, fonts, tone |
| `brand-box website` | Scaffold a landing page |
| `brand-box social` | Generate social media profile assets |
| `brand-box video` | Generate social media video content |

## Configuration

Create a `.env` file in the project root (or pass via environment):

```
# Required for AI generation
GEMINI_API_KEY=your-key-here

# Optional: Azure OpenAI (for GPT-4o scriptwriting)
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_OPENAI_KEY=your-key
AZURE_OPENAI_DEPLOYMENT_GPT=gpt-4o

# Optional: Azure Speech (for video narration)
AZURE_SPEECH_KEY=your-key
AZURE_SPEECH_REGION=westeurope
```

## Architecture

```
brand-box/
├── src/brand_box/
│   ├── __init__.py
│   ├── cli.py              # CLI entry point
│   ├── config.py            # Configuration / env loading
│   ├── project.py           # Brand project state management
│   ├── generators/
│   │   ├── name.py          # Name brainstorming + validation
│   │   ├── logo.py          # AI logo generation
│   │   ├── identity.py      # Brand identity (colors, fonts, tone)
│   │   ├── website.py       # Landing page scaffolding
│   │   ├── social.py        # Social media asset generation
│   │   └── video.py         # Video content pipeline
│   └── templates/
│       └── landing/         # HTML templates for landing pages
├── tests/
├── pyproject.toml
└── README.md
```

## Reusable Across Projects

brand-box stores project state in a `brand.json` file. Each project gets its own output directory:

```
my-project/
├── brand.json          # Project config + generated brand state
├── output/
│   ├── names/          # Name candidates
│   ├── logos/          # Generated logo images
│   ├── identity/       # Color palette, style guide
│   ├── website/        # Landing page HTML
│   ├── social/         # Profile pics, banners, bios
│   └── videos/         # Social media videos
```

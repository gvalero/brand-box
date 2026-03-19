# Refactor Handoff

This repo was refactored from a linear "generate one thing and continue" pipeline toward a staged creative system with typed artifacts, variant generation, evaluation, and richer rendering.

## Next Agent Prompt

Pick up from the current refactor state and continue improving the local video production path.

Priority task:

- implement multi-asset scenes and cutaways in the local renderer so a single storyboard scene can use more than one visual layer or shot instead of one primary image only

Suggested focus:

- extend `VideoStoryboard.scenes` so a scene can carry multiple visual assets or shot beats
- update the local renderer in `src/brand_box/generators/video.py` to support cutaways, split layouts, inserts, and more editorial variation within one scene
- keep profile-aware rendering (`reel`, `square`, `web-hero`, `youtube`) working
- preserve backward compatibility with existing single-image scenes
- if possible, improve music mixing so ducking reacts to voice segments rather than using a single static bed level

Constraints:

- do not break existing CLI behavior
- keep `brand-box video` working without requiring new external services
- preserve compatibility with existing `brand.json` files

Good validation target:

- produce one smoke render for `reel`
- produce one smoke render for `web-hero`
- confirm storyboard serialization still works

## Foundation

Changed [project.py](/Users/givalero/Projects/brand-box/src/brand_box/project.py) and added [artifacts.py](/Users/givalero/Projects/brand-box/src/brand_box/models/artifacts.py).

New typed artifacts:

- `BrandBrief`
- `NameCandidate`
- `LogoConcept`
- `BrandDirection`
- `WebsiteSpec`
- `VideoStoryboard`
- `MusicPlan`
- `StageReview`

`BrandProject` now persists:

- `brief`
- `selected_name`
- `naming_candidates`
- `logo_concepts`
- `selected_logo`
- `brand_direction`
- `website_specs`
- `selected_website_spec`
- `storyboards`
- `music_plans`
- `selected_music_plan`
- `reviews`
- `run_history`

Backward compatibility with existing `brand.json` was preserved.

## Website

Reworked [website.py](/Users/givalero/Projects/brand-box/src/brand_box/generators/website.py).

It is now split internally into:

- strategy/spec generation via `WebsiteStrategist`
- copy generation conditioned on the spec
- rendering from the structured spec

Website changes:

- generates multiple website variants
- scores them with a heuristic evaluator
- stores all variants in `project.website_specs`
- selects the best one and renders it
- persists `selected_website_spec`

Evaluator added in [creative.py](/Users/givalero/Projects/brand-box/src/brand_box/evaluators/creative.py):

- `WebsiteEvaluator`

CLI changes in [cli.py](/Users/givalero/Projects/brand-box/src/brand_box/cli.py):

- `brand-box website` still works the same externally
- now saves all website specs and the selected winner

## Video Architecture

Reworked [script.py](/Users/givalero/Projects/brand-box/src/brand_box/generators/script.py).

Video is now storyboard-first:

- `VideoStrategist`
- `StoryboardGenerator`
- legacy script dict produced via `storyboard_to_script(...)`

Video changes:

- generates multiple storyboard variants
- scores them with heuristic evaluator
- stores all in `project.storyboards`
- selects best storyboard before rendering

Evaluator added in [creative.py](/Users/givalero/Projects/brand-box/src/brand_box/evaluators/creative.py):

- `VideoEvaluator`

CLI changes in [cli.py](/Users/givalero/Projects/brand-box/src/brand_box/cli.py):

- fixed bug where Manus branch referenced `storyboard` before creation
- now generates storyboard variants first
- selects best storyboard
- uses storyboard for both Manus and local rendering

## Video Renderer Quality

Major refactor in [video.py](/Users/givalero/Projects/brand-box/src/brand_box/generators/video.py).

Old behavior:

- full-screen still
- bottom caption strip
- slideshow feel

New behavior:

- layered scene composition
- blurred background derived from source visual
- framed foreground panel with shadow/depth
- scene chip + scene count from storyboard
- headline card using `on_screen_text`
- supporting copy block
- progress indicator
- fade transitions and slight overlap between scenes
- richer intro and CTA cards

Smoke renders created successfully:

- [render_smoke.mp4](/Users/givalero/Projects/brand-box/tmp/render_smoke.mp4)
- [render_reel_smoke.mp4](/Users/givalero/Projects/brand-box/tmp/render_reel_smoke.mp4)
- [render_web_smoke.mp4](/Users/givalero/Projects/brand-box/tmp/render_web_smoke.mp4)

## Aspect Ratio / Output Profiles

Added profile-driven rendering in [video.py](/Users/givalero/Projects/brand-box/src/brand_box/generators/video.py) with `RENDER_PROFILES`.

Supported profiles:

- `reel`
- `square`
- `web-hero`
- `youtube`

Renderer now adapts layout and sizing by profile instead of assuming vertical `9:16`.

CLI changes in [cli.py](/Users/givalero/Projects/brand-box/src/brand_box/cli.py):

- added `--profile`

Manus prompt updated in [manus_video.py](/Users/givalero/Projects/brand-box/src/brand_box/generators/manus_video.py):

- receives profile info
- receives storyboard scene guidance

## Music Subroutine

Added [music.py](/Users/givalero/Projects/brand-box/src/brand_box/generators/music.py).

Music changes:

- introduced typed `MusicPlan`
- music is now treated as a video-production subroutine
- planner can derive mood/tempo/instrumentation from concept + format
- supports user-supplied track via `--music`
- supports folder auto-pick via `--music-dir`

Renderer changes in [video.py](/Users/givalero/Projects/brand-box/src/brand_box/generators/video.py):

- optional background music mixing
- loops/trims music to video duration
- lowers music volume under narration
- adds music fade in/out

CLI changes in [cli.py](/Users/givalero/Projects/brand-box/src/brand_box/cli.py):

- added `--music`
- added `--music-dir`
- persists selected music plan

Smoke render with music succeeded:

- [render_music_smoke.mp4](/Users/givalero/Projects/brand-box/tmp/render_music_smoke.mp4)

## New Files Added

- [artifacts.py](/Users/givalero/Projects/brand-box/src/brand_box/models/artifacts.py)
- [__init__.py](/Users/givalero/Projects/brand-box/src/brand_box/models/__init__.py)
- [creative.py](/Users/givalero/Projects/brand-box/src/brand_box/evaluators/creative.py)
- [__init__.py](/Users/givalero/Projects/brand-box/src/brand_box/evaluators/__init__.py)
- [music.py](/Users/givalero/Projects/brand-box/src/brand_box/generators/music.py)

## Current State

The system now has:

- typed project state
- website spec generation
- storyboard-first video generation
- variant generation + selection
- heuristic evaluators
- richer local video rendering
- profile-aware output formats
- background music planning and mixing

## Known Remaining Gaps / Likely Next Work

- local video renderer still uses one main source visual per scene
- no true multi-asset scene editing yet
- no AI music provider integration yet, only planning/selection/mixing
- no beat-synced text animation
- no dynamic ducking envelope by spoken segment, just static lowered bed
- Manus backend still doesn't upload logo/assets as true input files, it only gets richer prompt context
- website renderer is still one renderer with variant specs, not multiple render engines/themes
- tests are still effectively missing

## Best Next Step

Most likely next high-impact task:

- multi-asset scenes and cutaways in the local video renderer

After that:

- AI music provider integration
- stronger website render variants
- model-based critics instead of heuristic-only evaluators

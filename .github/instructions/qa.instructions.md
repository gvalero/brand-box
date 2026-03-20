# QA Instructions — Brand Box

## Project-Specific QA Concerns

- **No test suite**: The `tests/` directory is empty. Any code change is completely unverified. High risk of regression.
- **Multi-API dependency chain**: Brand generation calls Gemini, Azure OpenAI, and Azure Speech Service in sequence. Any one failing breaks the entire pipeline with no fallback for most stages.
- **Video generation fragility**: MoviePy is notoriously fragile — codec issues, format mismatches, and file handle leaks are common. Video generation needs defensive error handling.
- **File I/O validation**: Writes to `brand.json` and output directories. Missing write permission checks, no handling for disk full or path-too-long scenarios.
- **Decision gates are critical**: The `select` command is the only way to advance past name/logo stages. If gates are bypassed or broken, the entire pipeline auto-selects creative decisions — the core design violation.

## Architecture

- **Two-agent model**: `@brand-architect` (brand definition, occasional) and `@brand-producer` (video content, frequent). Both agents invoke the `brand-box` CLI.
- **Decision gates**: `brand-box name` and `brand-box logo` return `awaiting_selection` status. User must run `brand-box select name/logo` before downstream commands work. `_require_gate()` enforces this.
- **Pipeline dependency chain**: init → name → [SELECT] → logo → [SELECT] → identity → kit → website → social → video. Each stage depends on previous stage output + gate clearance.
- **No auto-selection**: `active_logo_path` returns empty string if nothing is explicitly selected — no `[0]` fallback, no heuristic. `active_name` only returns `selected_name` (or legacy `name` for backward compat).

## Critical Paths

- **Happy path**: init → name (presents candidates) → select name → logo (generates options) → select logo → identity → kit → website → social → video
- **Gate enforcement**: Every downstream command must call `_require_gate()`. If any new command is added without gate checks, it silently bypasses human approval.
- **Legacy migration**: `from_dict()` falls back `selected_name` to legacy `name` field. Old `brand.json` files without `selected_name` should still work.
- **JSON mode**: `--json` flag on name/logo/select must output parseable JSON for agent consumption. Broken JSON = agents can't parse and the pipeline stalls.

## Known Fragile Areas

- Video generation with MoviePy — codec and format issues. Must track all intermediate clips for cleanup (transformation methods return NEW objects).
- Logo generation — Pillow-based fallback exists, but quality varies by system fonts
- Audio caching — uses MD5 of text as cache key; special characters could cause issues
- `_require_gate()` — single enforcement point for all gates. If this function has a bug, all gates fail open.
- `concatenate_videoclips(padding=-0.12)` — can throw TypeError on some MoviePy versions

## External Dependencies

- **Google Gemini API**: Name and brand identity generation. Rate limits and quota apply.
- **Azure OpenAI**: Content generation. Shared quota with other projects.
- **Azure Speech Service**: Audio narration. Region and deployment specific.
- **Pillow**: Image generation fallback. Font availability varies by system.
- **MoviePy**: Video assembly. Requires ffmpeg installed and accessible.

## Testing Notes

- Test command: `pytest` (but no tests exist yet)
- **Priority test areas**:
  1. Decision gate enforcement: verify `_require_gate()` blocks all downstream commands when name/logo not selected
  2. `brand-box select` command: valid selection, invalid selection, selection when no candidates exist
  3. JSON output parsing: verify `--json` output is valid JSON on name, logo, select commands
  4. Legacy `brand.json` migration: old files without `selected_name`/`selected_logo` fields
  5. MoviePy resource cleanup: verify clips are closed after video generation
  6. API fallback paths: behavior when Gemini/Azure calls fail

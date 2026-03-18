# QA Instructions — Brand Box

## Project-Specific QA Concerns

- **No test suite**: The `tests/` directory is empty. Any code change is completely unverified. High risk of regression.
- **Multi-API dependency chain**: Brand generation calls Gemini, Azure OpenAI, and Azure Speech Service in sequence. Any one failing breaks the entire pipeline with no fallback for most stages.
- **Video generation fragility**: MoviePy is notoriously fragile — codec issues, format mismatches, and file handle leaks are common. Video generation needs defensive error handling.
- **File I/O validation**: Writes to `brand.json` and output directories. Missing write permission checks, no handling for disk full or path-too-long scenarios.

## Critical Paths

- Concept → Name → Logo → Brand Identity → Landing Page → Social Assets → Video
- Each stage depends on the previous stage's output
- API calls to Gemini (name/identity gen), Azure OpenAI (content gen), Azure Speech (audio)

## Known Fragile Areas

- Video generation with MoviePy — codec and format issues
- Logo generation — Pillow-based fallback exists, but quality varies
- Audio caching — uses MD5 of text as cache key; special characters could cause issues

## External Dependencies

- **Google Gemini API**: Name and brand identity generation. Rate limits and quota apply.
- **Azure OpenAI**: Content generation. Shared quota with other projects.
- **Azure Speech Service**: Audio narration. Region and deployment specific.
- **Pillow**: Image generation fallback. Font availability varies by system.
- **MoviePy**: Video assembly. Requires ffmpeg installed and accessible.

## Testing Notes

- Test command: `pytest` (but no tests exist yet)
- Coverage gaps: Everything — no test suite. Priority: add tests for API fallback paths and file I/O error handling.

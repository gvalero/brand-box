from __future__ import annotations

from pathlib import Path

from PIL import Image

from brand_box.generators.video import VideoAssembler


class FakeAudioClip:
    def __init__(self, duration: float) -> None:
        self.duration = duration
        self.closed = False
        self.subclip_calls: list[tuple[float, float]] = []

    def subclipped(self, start: float, end: float) -> "FakeAudioClip":
        self.subclip_calls.append((start, end))
        return FakeAudioClip(end - start)

    def close(self) -> None:
        self.closed = True


def test_video_assembler_uses_profile_dimensions() -> None:
    reel = VideoAssembler(profile="reel")
    web = VideoAssembler(profile="web-hero")

    assert (reel.width, reel.height) == (1080, 1920)
    assert (web.width, web.height) == (1920, 1080)
    assert web._scale(100, axis="w") > reel._scale(100, axis="w")


def test_normalize_scene_assets_handles_single_multi_and_empty() -> None:
    assert VideoAssembler._normalize_scene_assets("a.png") == ["a.png"]
    assert VideoAssembler._normalize_scene_assets(["a.png", " ", "b.png"]) == ["a.png", "b.png"]
    assert VideoAssembler._normalize_scene_assets(None) == []


def test_crop_to_aspect_preserves_requested_ratio() -> None:
    img = Image.new("RGB", (1600, 900), "white")

    cropped = VideoAssembler._crop_to_aspect(img, 1080, 1920)

    ratio = cropped.size[0] / cropped.size[1]
    assert round(ratio, 2) == round(1080 / 1920, 2)


def test_build_foreground_panel_changes_with_profile() -> None:
    source = Image.new("RGB", (1200, 900), "navy")
    reel = VideoAssembler(profile="reel")
    web = VideoAssembler(profile="web-hero")

    reel_panel = reel._build_foreground_panel(source)
    web_panel = web._build_foreground_panel(source)

    assert reel_panel.size[0] < reel.width
    assert reel_panel.size[1] < reel.height
    assert web_panel.size[0] > reel_panel.size[0]


def test_loop_audio_to_duration_reuses_full_clip_and_partial_tail() -> None:
    source = FakeAudioClip(duration=2.0)

    calls: list[list[FakeAudioClip]] = []

    def fake_concat(parts: list[FakeAudioClip]) -> FakeAudioClip:
        calls.append(parts)
        return FakeAudioClip(sum(part.duration for part in parts))

    looped = VideoAssembler._loop_audio_to_duration(source, 5.0, fake_concat)

    assert len(calls) == 1
    assert [part.duration for part in calls[0]] == [2.0, 2.0, 1.0]
    assert looped.duration == 5.0

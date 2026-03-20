from __future__ import annotations

import sys
import types

from brand_box.generators.video import RENDER_PROFILES, VideoAssembler


def test_renderer_profiles_define_expected_dimensions() -> None:
    reel = VideoAssembler(profile="reel")
    square = VideoAssembler(profile="square")
    web = VideoAssembler(profile="web-hero")

    assert (reel.width, reel.height) == (1080, 1920)
    assert (square.width, square.height) == (1080, 1080)
    assert (web.width, web.height) == (1920, 1080)
    assert RENDER_PROFILES["youtube"]["label"] == "YouTube landscape"


def test_normalize_scene_assets_handles_single_and_multi_asset_inputs() -> None:
    assembler = VideoAssembler()

    assert assembler._normalize_scene_assets("img-1.png") == ["img-1.png"]
    assert assembler._normalize_scene_assets(["img-1.png", " ", "img-2.png"]) == ["img-1.png", "img-2.png"]
    assert assembler._normalize_scene_assets(None) == []


def test_scale_respects_axis_specific_resize() -> None:
    assembler = VideoAssembler(width=540, height=960)

    assert assembler._scale(100, axis="w") == 50
    assert assembler._scale(100, axis="h") == 50
    assert assembler._scale(100) == 50


def test_create_scene_sequence_clip_uses_each_asset_and_closes_intermediates(monkeypatch, tmp_path) -> None:
    assembler = VideoAssembler()
    created = []

    class FakeClip:
        def __init__(self, label: str) -> None:
            self.label = label
            self.closed = False

        def close(self) -> None:
            self.closed = True

    def fake_create_scene_clip(image_path, text, duration, scene, scene_number, scene_count):
        clip = FakeClip(image_path)
        created.append(
            {
                "image_path": image_path,
                "scene": dict(scene),
                "duration": duration,
                "clip": clip,
            }
        )
        return clip

    fake_moviepy = types.ModuleType("moviepy")

    def fake_concatenate_videoclips(clips, method="compose", padding=0):
        return {
            "clips": clips,
            "method": method,
            "padding": padding,
        }

    fake_moviepy.concatenate_videoclips = fake_concatenate_videoclips
    monkeypatch.setitem(sys.modules, "moviepy", fake_moviepy)
    monkeypatch.setattr(assembler, "_create_scene_clip", fake_create_scene_clip)

    asset_paths = []
    for name in ("a.png", "b.png", "c.png"):
        path = tmp_path / name
        path.write_text("stub", encoding="utf-8")
        asset_paths.append(str(path))

    result = assembler._create_scene_sequence_clip(
        image_paths=asset_paths,
        text="Narration copy",
        duration=9.0,
        scene={
            "purpose": "hook",
            "shot_type": "close-up",
            "visual_beats": ["cutaway one", "cutaway two"],
            "on_screen_text": "",
        },
        scene_number=2,
        scene_count=3,
    )

    assert result["method"] == "compose"
    assert len(result["clips"]) == 3
    assert [item["image_path"] for item in created] == asset_paths
    assert created[1]["scene"]["purpose"] == "cutaway"
    assert created[2]["scene"]["purpose"] == "cutaway"
    assert created[1]["scene"]["on_screen_text"] == "cutaway one"
    assert created[2]["scene"]["on_screen_text"] == "cutaway two"
    assert all(item["clip"].closed for item in created)


def test_loop_audio_to_duration_closes_partial_clips() -> None:
    class FakeClip:
        def __init__(self, duration: float) -> None:
            self.duration = duration
            self.closed = False
            self.subclip_calls = []

        def subclipped(self, start: float, end: float):
            self.subclip_calls.append((start, end))
            return FakeClip(end - start)

        def close(self) -> None:
            self.closed = True

    source = FakeClip(1.25)
    parts = []

    def fake_concatenate_audioclips(clips):
        parts.extend(clips)
        return {"clips": clips}

    result = VideoAssembler._loop_audio_to_duration(source, 2.6, fake_concatenate_audioclips)

    assert len(parts) == 3
    assert isinstance(result, dict)
    assert parts[-1].closed is True

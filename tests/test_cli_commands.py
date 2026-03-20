from __future__ import annotations

import argparse
import json
import sys
import types

import pytest

from brand_box import cli
from brand_box.models.artifacts import BrandDirection, MusicPlan, StageReview, VideoStoryboard, WebsiteSpec
from brand_box.project import BrandIdentity, BrandProject


def test_cmd_content_plan_outputs_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    project = BrandProject(concept="A reading companion for kids")
    monkeypatch.setattr(cli, "_load_project", lambda: project)

    cli.cmd_content_plan(
        argparse.Namespace(
            count=2,
            formats="teaser,explainer",
            profiles="reel",
            json=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 2
    assert payload[0]["format_id"] in {"teaser", "explainer"}


def test_cmd_evaluate_outputs_storyboard_review(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path
) -> None:
    project = BrandProject(
        concept="A reading companion for kids",
        storyboards=[
            VideoStoryboard(
                id="sb-1",
                platform="reel",
                angle="curiosity",
                hook="What if reading practice felt like play?",
                scenes=[
                    {
                        "scene_id": "s1",
                        "index": 0,
                        "voiceover": "What if reading felt like play?",
                        "visual_description": "Joyful child reading",
                        "on_screen_text": "Reading can feel playful",
                    }
                ],
                voiceover="What if reading felt like play?",
                caption_plan=["Reading can feel playful"],
            )
        ],
    )
    monkeypatch.setattr(cli, "_load_project", lambda: project)
    monkeypatch.chdir(tmp_path)

    cli.cmd_evaluate(argparse.Namespace(json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload["storyboard_id"] == "sb-1"
    assert "score" in payload
    assert "recommendation" in payload
    assert project.storyboards[-1].review.stage == "video"
    assert project.reviews[-1].stage == "video"


def test_cmd_evaluate_preserves_distinct_reviews_with_same_score(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    existing_review = StageReview(stage="video", score=0.5, subscores={"clarity": 0.5}, issues=["Missing hook"], recommendation="revise")
    project = BrandProject(
        concept="A reading companion for kids",
        storyboards=[
            VideoStoryboard(
                id="sb-1",
                platform="reel",
                angle="curiosity",
                hook="What if reading practice felt like play?",
                scenes=[{"scene_id": "s1", "index": 0, "voiceover": "One", "visual_description": "A", "on_screen_text": "A"}],
                voiceover="One",
                caption_plan=["A"],
                review=existing_review,
            ),
            VideoStoryboard(
                id="sb-2",
                platform="reel",
                angle="question",
                hook="Can reading feel lighter?",
                scenes=[{"scene_id": "s1", "index": 0, "voiceover": "Two", "visual_description": "B", "on_screen_text": "B"}],
                voiceover="Two",
                caption_plan=["B"],
            ),
        ],
        reviews=[existing_review, StageReview(stage="video", score=0.5, subscores={"clarity": 0.5}, issues=["Missing hook"], recommendation="revise")],
    )
    monkeypatch.setattr(cli, "_load_project", lambda: project)
    monkeypatch.chdir(tmp_path)

    import brand_box.evaluators.creative as creative_mod

    class FakeVideoEvaluator:
        def evaluate(self, storyboard):
            return StageReview(stage="video", score=0.5, subscores={"clarity": 0.5}, issues=["Missing hook"], recommendation="revise")

    monkeypatch.setattr(creative_mod, "VideoEvaluator", FakeVideoEvaluator)

    cli.cmd_evaluate(argparse.Namespace(json=False))

    assert len(project.reviews) == 3


def test_cmd_video_exits_cleanly_when_no_storyboards_generated(monkeypatch: pytest.MonkeyPatch) -> None:
    project = BrandProject(
        concept="A reading companion for kids",
        selected_name="PageBloom",
        selected_logo="/tmp/logo.png",
    )
    monkeypatch.setattr(cli, "_load_project", lambda: project)

    fake_script_module = types.ModuleType("brand_box.generators.script")

    class FakeScriptGenerator:
        def generate_storyboard_variants(self, **kwargs):
            return []

    fake_script_module.ScriptGenerator = FakeScriptGenerator
    fake_script_module.BUILTIN_FORMATS = {"teaser": object()}
    monkeypatch.setitem(sys.modules, "brand_box.generators.script", fake_script_module)

    errors: list[str] = []
    monkeypatch.setattr(cli, "_error", lambda message: errors.append(message))

    with pytest.raises(SystemExit) as exc:
        cli.cmd_video(
            argparse.Namespace(
                format="teaser",
                profile="reel",
                music=None,
                music_dir=None,
                local=True,
                no_images=False,
                no_audio=False,
                json=False,
            )
        )

    assert exc.value.code == 1
    assert errors == ["No storyboard variants were generated. Check your model configuration or try again."]


def test_cmd_render_forces_local_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[bool] = []

    def fake_cmd_video(args: argparse.Namespace) -> None:
        seen.append(args.local)

    monkeypatch.setattr(cli, "cmd_video", fake_cmd_video)

    cli.cmd_render(
        argparse.Namespace(
            format="teaser",
            profile="reel",
            music=None,
            music_dir=None,
            json=False,
        )
    )

    assert seen == [True]


def test_cmd_name_clears_stale_selections_before_saving(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    project = BrandProject(
        concept="A reading companion for kids",
        selected_name="OldName",
        name="OldName",
        selected_logo="/tmp/logo.png",
        logo_paths=["/tmp/logo.png"],
        website_specs=[WebsiteSpec(id="site-1")],
        website_path="/tmp/index.html",
        video_paths=["/tmp/video.mp4"],
    )
    monkeypatch.setattr(cli, "_load_project", lambda: project)
    monkeypatch.chdir(tmp_path)

    import brand_box.generators.name as name_mod

    class FakeNameGenerator:
        def generate_rich(self, concept, count=10):
            return []

    monkeypatch.setattr(name_mod, "NameGenerator", FakeNameGenerator)

    cli.cmd_name(argparse.Namespace(count=2, json=True))

    assert project.selected_name == ""
    assert project.selected_logo == ""
    assert project.logo_paths == []
    assert project.website_specs == []
    assert len(project.archived_artifacts) == 1
    assert project.archived_artifacts[0]["reason"] == "regenerated_name_candidates"
    assert project.archived_artifacts[0]["previous_name"] == "OldName"


def test_cmd_logo_clears_stale_logo_selection_before_saving(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    project = BrandProject(
        concept="A reading companion for kids",
        selected_name="PageBloom",
        selected_logo="/tmp/old-logo.png",
        logo_paths=["/tmp/old-logo.png"],
        website_specs=[WebsiteSpec(id="site-1")],
    )
    monkeypatch.setattr(cli, "_load_project", lambda: project)
    monkeypatch.chdir(tmp_path)

    import brand_box.generators.logo as logo_mod

    class FakeLogoGenerator:
        def __init__(self) -> None:
            self.last_concepts = []

        def generate(self, brand_name, concept, identity, output_dir, count):
            return ["/tmp/new-logo.png"]

    monkeypatch.setattr(logo_mod, "LogoGenerator", FakeLogoGenerator)

    cli.cmd_logo(argparse.Namespace(name=None, count=1, json=True))

    assert project.selected_logo == ""
    assert project.logo_paths == ["/tmp/new-logo.png"]


def test_cmd_select_locks_name_and_logo(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    logo_1 = tmp_path / "logo-1.png"
    logo_2 = tmp_path / "logo-2.png"
    logo_1.write_bytes(b"a")
    logo_2.write_bytes(b"b")
    project = BrandProject(
        concept="A reading companion for kids",
        name_candidates=["PageBloom", "ReadNest"],
        logo_paths=[str(logo_1), str(logo_2)],
    )
    monkeypatch.setattr(cli, "_load_project", lambda: project)
    monkeypatch.chdir(tmp_path)

    cli.cmd_select(argparse.Namespace(target="name", value="pagebloom", json=False))
    project.logo_paths = [str(logo_1), str(logo_2)]
    cli.cmd_select(argparse.Namespace(target="logo", value="2", json=False))

    assert project.selected_name == "PageBloom"
    assert project.name == "PageBloom"
    assert project.selected_logo == str(logo_2)


def test_cmd_logo_and_identity_use_selected_name(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    project = BrandProject(
        concept="A reading companion for kids",
        selected_name="PageBloom",
        identity=BrandIdentity(),
        logo_paths=["/tmp/logo-1.png"],
    )
    monkeypatch.setattr(cli, "_load_project", lambda: project)
    monkeypatch.chdir(tmp_path)

    import brand_box.generators.identity as identity_mod
    import brand_box.generators.logo as logo_mod

    seen: dict[str, str] = {}

    class FakeLogoGenerator:
        def __init__(self) -> None:
            self.last_concepts = []

        def generate(self, brand_name, concept, identity, output_dir, count):
            seen["logo_brand_name"] = brand_name
            return ["/tmp/logo-1.png"]

    class FakeIdentityGenerator:
        def generate_rich(self, concept, name):
            seen["identity_name"] = name
            return (
                BrandIdentity(primary_color="#112233", tagline="Read with confidence"),
                BrandDirection(positioning="Warm reading coach"),
            )

    monkeypatch.setattr(logo_mod, "LogoGenerator", FakeLogoGenerator)
    monkeypatch.setattr(identity_mod, "IdentityGenerator", FakeIdentityGenerator)

    cli.cmd_logo(argparse.Namespace(name=None, count=1, json=False))
    cli.cmd_identity(argparse.Namespace())

    assert seen["logo_brand_name"] == "PageBloom"
    assert seen["identity_name"] == "PageBloom"


def test_cmd_video_uses_selected_name_and_music_selection(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    project = BrandProject(
        concept="A reading companion for kids",
        selected_name="PageBloom",
        selected_logo="/tmp/logo-1.png",
        identity=BrandIdentity(
            primary_color="#112233",
            secondary_color="#445566",
            accent_color="#778899",
            background_color="#000000",
            text_color="#ffffff",
            font_heading="Alegreya",
            font_body="Nunito",
            tone="warm",
            tagline="Read with confidence",
        ),
    )
    monkeypatch.setattr(cli, "_load_project", lambda: project)
    monkeypatch.chdir(tmp_path)

    import brand_box.generators.music as music_mod
    import brand_box.generators.script as script_mod
    import brand_box.generators.video as video_mod

    seen: dict[str, object] = {}

    storyboard = VideoStoryboard(
        id="sb-1",
        platform="reel",
        angle="curiosity",
        hook="What if reading felt like play?",
        scenes=[
            {
                "scene_id": "s1",
                "index": 0,
                "purpose": "hook",
                "duration_seconds": 4,
                "shot_type": "close-up",
                "visual_description": "Joyful child reading",
                "visual_beats": ["Supportive parent beside child"],
                "on_screen_text": "Reading can feel fun",
                "voiceover": "What if reading felt like play?",
            }
        ],
        voiceover="What if reading felt like play?",
        caption_plan=["Reading can feel fun"],
        review=StageReview(stage="video", score=0.91, subscores={"clarity": 0.9}, recommendation="approve"),
    )

    class FakeScriptGenerator:
        def generate_storyboard_variants(self, **kwargs):
            seen["storyboard_brand_name"] = kwargs["brand_name"]
            return [storyboard]

        def select_best_storyboard(self, storyboards):
            return storyboards[0]

        def storyboard_to_script(self, storyboard, format_id=None):
            return {
                "title": "PageBloom teaser",
                "hook": storyboard.hook,
                "segments": [
                    {
                        "index": 0,
                        "text": storyboard.voiceover,
                        "visual_description": "Joyful child reading",
                        "visual_beats": ["Supportive parent beside child"],
                        "duration_seconds": 4,
                        "on_screen_text": "Reading can feel fun",
                    }
                ],
                "cta": "Start your free trial",
                "hashtags": ["#reading"],
                "total_duration_seconds": 8,
                "narration_text": storyboard.voiceover,
                "format_id": format_id or "teaser",
                "hook_angle": storyboard.angle,
            }

    class FakeMusicPlanner:
        def plan(self, **kwargs):
            seen["music_brand_name"] = kwargs["brand_name"]
            return MusicPlan(
                id="music-1",
                platform=kwargs["profile"],
                format_id=kwargs["format_id"],
                mood="warm",
                tempo="mid-tempo",
                source="planned",
                review=StageReview(stage="music", score=0.62, recommendation="revise"),
            )

    class FakeVideoAssembler:
        def __init__(self, brand_colors=None, profile="reel"):
            seen["assembler_profile"] = profile
            seen["assembler_colors"] = brand_colors

        def assemble_video(self, **kwargs):
            seen["assemble_brand_name"] = kwargs["brand_name"]
            seen["assemble_storyboard_hook"] = kwargs["storyboard"]["hook"]
            seen["assemble_background_music"] = kwargs["background_music_path"]
            return kwargs["output_path"]

    monkeypatch.setattr(script_mod, "ScriptGenerator", FakeScriptGenerator)
    monkeypatch.setattr(music_mod, "MusicPlanner", FakeMusicPlanner)
    monkeypatch.setattr(video_mod, "VideoAssembler", FakeVideoAssembler)

    cli.cmd_video(
        argparse.Namespace(
            format="teaser",
            profile="web-hero",
            music=None,
            music_dir=None,
            local=True,
            no_images=True,
            no_audio=True,
            json=False,
        )
    )

    assert seen["storyboard_brand_name"] == "PageBloom"
    assert seen["music_brand_name"] == "PageBloom"
    assert seen["assemble_brand_name"] == "PageBloom"
    assert seen["assembler_profile"] == "web-hero"
    assert project.selected_music_plan == "music-1"

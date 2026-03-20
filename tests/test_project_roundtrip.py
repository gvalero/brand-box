from __future__ import annotations

from pathlib import Path

from brand_box.models.artifacts import (
    BrandBrief,
    BrandDirection,
    LogoConcept,
    MusicPlan,
    NameCandidate,
    StageReview,
    VideoStoryboard,
    WebsiteSpec,
)
from brand_box.project import BrandIdentity, BrandProject


def test_brand_project_round_trip_preserves_rich_artifacts(tmp_path: Path) -> None:
    project = BrandProject(
        concept="AI reading companion for children",
        name="Legacy Name",
        name_candidates=["Legacy Name", "PageBloom"],
        identity=BrandIdentity(
            primary_color="#112233",
            secondary_color="#445566",
            accent_color="#778899",
            tagline="Read with confidence",
        ),
        logo_paths=["/tmp/legacy-logo.png"],
        brief=BrandBrief(
            product="Reading Companion",
            audience=["parents", "children"],
            problem="Reading practice feels lonely",
            category="education",
            goals=["Build awareness"],
        ),
        selected_name="PageBloom",
        naming_candidates=[
            NameCandidate(
                name="PageBloom",
                rationale="Feels warm and growth-oriented",
                tone=["warm", "encouraging"],
                review=StageReview(stage="name", score=0.91),
            )
        ],
        logo_concepts=[
            LogoConcept(
                id="logo-1",
                style="storybook badge",
                prompt="Create a storybook badge logo",
                rationale="Friendly and playful",
                asset_paths=["/tmp/selected-logo.png"],
                review=StageReview(stage="logo", score=0.88),
            )
        ],
        selected_logo="/tmp/selected-logo.png",
        brand_direction=BrandDirection(
            positioning="A warm reading coach for early learners",
            audience="Parents of children aged 5-8",
            personality=["warm", "trustworthy", "playful"],
            messaging_pillars=["confidence", "consistency"],
            palette={"primary": "#112233"},
            typography={"heading": "Alegreya", "body": "Nunito"},
            imagery_keywords=["storybook", "cozy"],
            review=StageReview(stage="identity", score=0.86),
        ),
        website_specs=[
            WebsiteSpec(
                id="site-1",
                audience="Parents",
                conversion_goal="Start free trial",
                visual_direction="storybook warmth",
                sections=[{"type": "hero"}],
                copy={"hero_headline": "Make reading practice feel magical"},
                review=StageReview(stage="website", score=0.83),
            )
        ],
        selected_website_spec="site-1",
        storyboards=[
            VideoStoryboard(
                id="sb-1",
                platform="reel",
                angle="problem-first",
                hook="Reading practice shouldn't feel lonely.",
                scenes=[{"scene_id": "s1", "index": 0, "voiceover": "Hook"}],
                review=StageReview(stage="video", score=0.79),
            )
        ],
        music_plans=[
            MusicPlan(
                id="music-1",
                platform="reel",
                format_id="teaser",
                mood="warm",
                tempo="mid-tempo",
                track_path="/tmp/music.mp3",
                review=StageReview(stage="music", score=0.77),
            )
        ],
        selected_music_plan="music-1",
        reviews=[StageReview(stage="video", score=0.79, recommendation="approve")],
        run_history=[{"stage": "video", "status": "completed"}],
        archived_artifacts=[{"reason": "selected_new_name", "previous_name": "Legacy Name"}],
        metadata={"chosen_logo": "/tmp/legacy-chosen-logo.png"},
    )

    path = tmp_path / "brand.json"
    project.save(path)
    loaded = BrandProject.load(path)

    assert loaded.active_name == "PageBloom"
    assert loaded.active_logo_path == "/tmp/selected-logo.png"
    assert loaded.brief.product == "Reading Companion"
    assert loaded.naming_candidates[0].name == "PageBloom"
    assert loaded.logo_concepts[0].id == "logo-1"
    assert loaded.brand_direction.positioning.startswith("A warm reading coach")
    assert loaded.website_specs[0].id == "site-1"
    assert loaded.storyboards[0].id == "sb-1"
    assert loaded.music_plans[0].id == "music-1"
    assert loaded.reviews[0].stage == "video"
    assert loaded.run_history[0]["status"] == "completed"
    assert loaded.archived_artifacts[0]["reason"] == "selected_new_name"


def test_from_dict_promotes_legacy_fields_into_selections() -> None:
    project = BrandProject.from_dict(
        {
            "concept": "A literacy app for kids",
            "name": "StoryGlow",
            "name_candidates": ["StoryGlow", "PageNest"],
            "logo_paths": ["/tmp/logo-a.png"],
            "metadata": {"chosen_logo": "/tmp/logo-b.png"},
        }
    )

    assert project.selected_name == "StoryGlow"
    assert project.active_name == "StoryGlow"
    assert project.selected_logo == "/tmp/logo-b.png"
    assert project.active_logo_path == "/tmp/logo-b.png"
    assert [candidate.name for candidate in project.naming_candidates] == ["StoryGlow", "PageNest"]


def test_active_logo_path_falls_back_to_legacy_logo_paths() -> None:
    project = BrandProject.from_dict(
        {
            "concept": "A literacy app for kids",
            "logo_paths": ["/tmp/logo-a.png"],
        }
    )

    assert project.selected_logo == ""
    assert project.active_logo_path == "/tmp/logo-a.png"

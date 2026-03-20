from __future__ import annotations

from brand_box.evaluators.creative import NameEvaluator, VideoEvaluator
from brand_box.models.artifacts import BrandDirection, NameCandidate, StageReview, VideoStoryboard
from brand_box.planner import ContentPlanner, describe_brand
from brand_box.project import BrandIdentity, BrandProject


def test_content_planner_respects_count_and_profiles() -> None:
    project = BrandProject(concept="Reading practice app")
    planner = ContentPlanner()

    plan = planner.plan(
        project=project,
        count=5,
        formats=["teaser", "explainer"],
        profiles=["reel", "square"],
    )

    assert len(plan) == 5
    assert {job["profile"] for job in plan} == {"reel", "square"}
    assert {job["format_id"] for job in plan}.issubset({"teaser", "explainer"})
    assert all(job["output_filename"].endswith(".mp4") for job in plan)


def test_describe_brand_uses_active_selections() -> None:
    project = BrandProject(
        concept="Reading practice app",
        name="Legacy Name",
        selected_name="PageBloom",
        identity=BrandIdentity(
            primary_color="#112233",
            secondary_color="#445566",
            accent_color="#778899",
            tone="warm and trustworthy",
            tagline="Read with confidence",
        ),
        logo_paths=["/tmp/legacy.png"],
        selected_logo="/tmp/selected.png",
        brand_direction=BrandDirection(
            positioning="Warm reading coach",
            personality=["warm", "encouraging"],
            messaging_pillars=["confidence", "consistency"],
        ),
    )

    summary = describe_brand(project)

    assert summary["name"] == "PageBloom"
    assert summary["logo_path"] == "/tmp/selected.png"
    assert summary["tagline"] == "Read with confidence"
    assert summary["brand_direction_summary"]["positioning"] == "Warm reading coach"


def test_name_evaluator_flags_generic_names() -> None:
    review = NameEvaluator().evaluate(
        NameCandidate(
            name="Smart Cloud",
            rationale="Sounds modern",
            tone=["modern"],
            domain_notes="likely available",
        )
    )

    assert review.stage == "name"
    assert review.subscores["distinctiveness"] < 0.8
    assert any("generic word" in issue.lower() for issue in review.issues)


def test_video_evaluator_rewards_complete_storyboards() -> None:
    storyboard = VideoStoryboard(
        id="sb-1",
        platform="reel",
        angle="problem-first",
        hook="Reading time should feel magical, not stressful.",
        scenes=[
            {
                "scene_id": "s1",
                "index": 0,
                "purpose": "hook",
                "duration_seconds": 4,
                "shot_type": "close-up",
                "visual_description": "Child smiling with tablet",
                "motion_direction": "quick push-in",
                "on_screen_text": "Reading can feel fun",
                "voiceover": "Reading time should feel magical.",
            },
            {
                "scene_id": "s2",
                "index": 1,
                "purpose": "benefit",
                "duration_seconds": 5,
                "shot_type": "illustration",
                "visual_description": "Parent and child celebrating progress",
                "motion_direction": "gentle pan",
                "on_screen_text": "Support every session",
                "voiceover": "Guide every practice session with confidence.",
            },
        ],
        voiceover="Reading time should feel magical. Guide every practice session with confidence.",
        caption_plan=["Reading can feel fun", "Support every session"],
        review=StageReview(stage="video"),
    )

    review = VideoEvaluator().evaluate(storyboard)

    assert review.stage == "video"
    assert review.score > 0.7
    assert review.recommendation in {"approve", "revise"}

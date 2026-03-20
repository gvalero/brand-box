from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from brand_box import cli
from brand_box.models.artifacts import StageReview, WebsiteSpec, VideoStoryboard
from brand_box.project import BrandIdentity, BrandProject


def test_require_gate_outputs_json_for_missing_selections(capsys: pytest.CaptureFixture[str]) -> None:
    project = BrandProject()

    with pytest.raises(SystemExit) as exc:
        cli._require_gate(project, need_name=True, need_logo=True, json_mode=True)

    assert exc.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "gate_failed"
    assert payload["missing_selections"] == ["name", "logo"]


def test_cmd_select_name_matches_case_insensitively(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = BrandProject(name_candidates=["PageBloom", "StoryNest"])
    monkeypatch.setattr(cli, "_load_project", lambda: project)
    monkeypatch.chdir(tmp_path)

    cli.cmd_select(argparse.Namespace(target="name", value="pagebloom", json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"status": "selected", "stage": "name", "selected": "PageBloom"}
    saved = BrandProject.load(tmp_path / "brand.json")
    assert saved.selected_name == "PageBloom"
    assert saved.name == "PageBloom"


def test_cmd_select_logo_by_index_persists_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    logo_a = tmp_path / "logo_a.png"
    logo_b = tmp_path / "logo_b.png"
    logo_a.write_bytes(b"a")
    logo_b.write_bytes(b"b")
    project = BrandProject(logo_paths=[str(logo_a), str(logo_b)])
    monkeypatch.setattr(cli, "_load_project", lambda: project)
    monkeypatch.chdir(tmp_path)

    cli.cmd_select(argparse.Namespace(target="logo", value="2", json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload["stage"] == "logo"
    assert payload["selected"] == str(logo_b)
    saved = BrandProject.load(tmp_path / "brand.json")
    assert saved.selected_logo == str(logo_b)


def test_cmd_select_logo_accepts_existing_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    logo = tmp_path / "external_logo.png"
    logo.write_bytes(b"img")
    project = BrandProject()
    monkeypatch.setattr(cli, "_load_project", lambda: project)
    monkeypatch.chdir(tmp_path)

    cli.cmd_select(argparse.Namespace(target="logo", value=str(logo), json=True))

    payload = json.loads(capsys.readouterr().out)
    assert payload["selected"] == str(logo.resolve())


def test_cmd_select_name_clears_dependent_assets_when_name_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = BrandProject(
        name_candidates=["PageBloom", "StoryNest"],
        selected_name="StoryNest",
        name="StoryNest",
        selected_logo="/tmp/logo.png",
        logo_paths=["/tmp/logo.png"],
        identity=BrandIdentity(primary_color="#112233"),
        website_path="/tmp/index.html",
        website_specs=[WebsiteSpec(id="site-1", review=StageReview(stage="website", score=0.9))],
        selected_website_spec="site-1",
        storyboards=[VideoStoryboard(id="sb-1")],
        music_plans=[],
        video_paths=["/tmp/video.mp4"],
    )
    monkeypatch.setattr(cli, "_load_project", lambda: project)
    monkeypatch.chdir(tmp_path)

    cli.cmd_select(argparse.Namespace(target="name", value="PageBloom", json=False))

    assert project.selected_name == "PageBloom"
    assert project.selected_logo == ""
    assert project.logo_paths == []
    assert project.website_specs == []
    assert project.storyboards == []
    assert project.video_paths == []
    assert len(project.archived_artifacts) == 1
    archive = project.archived_artifacts[0]
    assert archive["reason"] == "selected_new_name"
    assert archive["previous_name"] == "StoryNest"
    assert archive["selected_logo"] == "/tmp/logo.png"
    assert archive["website_specs"][0]["id"] == "site-1"
    assert archive["storyboards"][0]["id"] == "sb-1"


def test_cmd_select_logo_clears_downstream_assets_when_logo_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logo_a = tmp_path / "logo_a.png"
    logo_b = tmp_path / "logo_b.png"
    logo_a.write_bytes(b"a")
    logo_b.write_bytes(b"b")
    project = BrandProject(
        selected_name="PageBloom",
        selected_logo=str(logo_a),
        logo_paths=[str(logo_a), str(logo_b)],
        identity=BrandIdentity(primary_color="#112233"),
        website_path="/tmp/index.html",
        website_specs=[WebsiteSpec(id="site-1", review=StageReview(stage="website", score=0.9))],
        selected_website_spec="site-1",
        storyboards=[VideoStoryboard(id="sb-1")],
        video_paths=["/tmp/video.mp4"],
    )
    monkeypatch.setattr(cli, "_load_project", lambda: project)
    monkeypatch.chdir(tmp_path)

    cli.cmd_select(argparse.Namespace(target="logo", value="2", json=False))

    assert project.selected_logo == str(logo_b)
    assert project.website_specs == []
    assert project.storyboards == []
    assert project.video_paths == []
    assert len(project.archived_artifacts) == 1
    archive = project.archived_artifacts[0]
    assert archive["reason"] == "selected_new_logo"
    assert archive["selected_logo"] == str(logo_a)

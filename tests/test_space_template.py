"""Tests for the ``space_template/`` renderer and the committed template itself."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from hf_space import render, render_space_files, workspaces_value

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "space_template"


def test_render_substitutes_placeholders():
    assert render("FROM __IMAGE_REF__\n", {"IMAGE_REF": "repo@sha256:abc"}) == "FROM repo@sha256:abc\n"


def test_render_substitutes_every_occurrence():
    assert render("__A__/__A__", {"A": "x"}) == "x/x"


def test_render_rejects_a_placeholder_it_was_not_given():
    # Silent pass-through is the exact failure mode that wipes a Space's config.
    with pytest.raises(KeyError):
        render("title: __TITLE__\nlicense: __LICENSE__\n", {"TITLE": "Extralit"})


def test_render_leaves_dockerfile_arg_syntax_alone():
    assert render("ENV X=${HOME}\n", {}) == "ENV X=${HOME}\n"


def test_manifest_declares_every_placeholder_used_by_the_template():
    manifest = json.loads((TEMPLATE_DIR / "manifest.json").read_text())
    declared = set(manifest["variables"])

    used = set()
    for name in manifest["files"]:
        used |= set(_placeholders((TEMPLATE_DIR / name).read_text()))

    assert used == declared


def test_manifest_carries_no_required_secrets():
    manifest = json.loads((TEMPLATE_DIR / "manifest.json").read_text())

    # That contract lives in the Hub's `deployment_templates.required_secrets`. A second
    # copy here has no seeder, and the drift shows up as a Space missing a secret.
    assert "required_secrets" not in manifest


def _placeholders(text: str) -> list[str]:
    import re

    return re.findall(r"__([A-Z0-9_]+)__", text)


def test_rendered_template_has_no_placeholders_left():
    files = render_space_files(TEMPLATE_DIR, {"IMAGE_REF": "extralit/extralit-hf-space@sha256:abc"})

    for name, text in files.items():
        assert not _placeholders(text), f"{name} still has placeholders"


def test_rendered_dockerfile_copies_the_oauth_config():
    files = render_space_files(TEMPLATE_DIR, {"IMAGE_REF": "repo@sha256:abc"})

    assert files["Dockerfile"].splitlines()[0] == "FROM repo@sha256:abc"
    assert "COPY .oauth.yaml /home/extralit/" in files["Dockerfile"]


def test_rendered_oauth_config_is_valid_yaml_with_the_requested_workspaces():
    files = render_space_files(
        TEMPLATE_DIR, {"IMAGE_REF": "r@sha256:a", "WORKSPACES": workspaces_value(["public", "test"])}
    )

    parsed = yaml.safe_load(files[".oauth.yaml"])
    assert parsed["enabled"] is True
    assert parsed["providers"] == [{"name": "huggingface"}]
    assert parsed["allowed_workspaces"] == [{"name": "public"}, {"name": "test"}]


def test_rendered_readme_frontmatter_is_valid_yaml():
    files = render_space_files(TEMPLATE_DIR, {"IMAGE_REF": "r@sha256:a", "TITLE": "Extralit PR Preview"})

    front = yaml.safe_load(files["README.md"].split("---")[1])
    assert front["title"] == "Extralit PR Preview"
    assert front["sdk"] == "docker"
    assert front["app_port"] == 6900
    assert front["hf_oauth"] is True


def test_unrendered_template_is_itself_parseable_yaml():
    # `__VAR__` is a plain scalar; `{{VAR}}` would be a flow mapping and fail pre-commit's
    # check-yaml, which runs with no path filters.
    yaml.safe_load((TEMPLATE_DIR / ".oauth.yaml").read_text())
    yaml.safe_load((TEMPLATE_DIR / "README.md").read_text().split("---")[1])

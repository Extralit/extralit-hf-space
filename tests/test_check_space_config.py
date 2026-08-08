"""Tests for ``scripts/check_space_config.py`` — the read-only template drift check."""

from __future__ import annotations

import check_space_config as check

RENDERED = {
    "README.md": "---\ntitle: Extralit\nhf_oauth: false\ntags: [b, a]\n---\n\nbody\n",
    ".oauth.yaml": "enabled: true\nallowed_workspaces: [{name: public}]\n",
    "Dockerfile": "FROM repo@sha256:aaa\n\nCOPY .oauth.yaml /home/extralit/\n",
}


def test_no_drift_when_the_live_space_matches_semantically():
    live = {
        # Block style, different key order, tags in the other order — same meaning.
        "README.md": "---\ntags:\n- a\n- b\ntitle: Extralit\n---\n\nbody\n",
        ".oauth.yaml": "enabled: true\nallowed_workspaces:\n  - name: public\n",
        "Dockerfile": "FROM repo@sha256:bbb\n\nCOPY .oauth.yaml /home/extralit/\n",
    }

    assert check.compare(RENDERED, live) == {}


def test_frontmatter_drift_is_reported_per_key():
    live = dict(RENDERED, **{"README.md": "---\ntitle: Something Else\nhf_oauth: false\ntags: [a, b]\n---\n"})

    drift = check.compare(RENDERED, live)

    assert list(drift) == ["README.md"]
    assert any("title" in line for line in drift["README.md"])


def test_allowlist_drift_is_reported():
    live = dict(RENDERED, **{".oauth.yaml": "enabled: true\nallowed_workspaces:\n  - name: extralit\n"})

    drift = check.compare(RENDERED, live)

    assert list(drift) == [".oauth.yaml"]


def test_dockerfile_drift_ignores_the_from_line():
    live = dict(RENDERED, **{"Dockerfile": "FROM other@sha256:ccc\n\nCOPY .oauth.yaml /home/extralit/\n"})

    assert check.compare(RENDERED, live) == {}


def test_dockerfile_drift_below_the_from_line_is_reported():
    live = dict(RENDERED, **{"Dockerfile": "FROM repo@sha256:aaa\n"})

    drift = check.compare(RENDERED, live)

    assert list(drift) == ["Dockerfile"]


def test_a_file_missing_from_the_live_space_is_drift():
    live = {k: v for k, v in RENDERED.items() if k != ".oauth.yaml"}

    drift = check.compare(RENDERED, live)

    assert list(drift) == [".oauth.yaml"]


def test_every_configured_space_declares_the_variables_the_template_needs():
    from pathlib import Path

    from hf_space import render_space_files

    template = Path(__file__).resolve().parent.parent / "space_template"
    for variables in check.SPACES.values():
        # Raises KeyError on any placeholder this Space has no value for.
        files = render_space_files(template, {**variables, "IMAGE_REF": "r@sha256:a"})
        assert set(files) == {"README.md", "Dockerfile", ".oauth.yaml"}

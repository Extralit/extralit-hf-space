"""Tests for ``scripts/deploy_space.py`` — the env-to-image-ref glue."""

from __future__ import annotations

import deploy_space
import pytest

DIGEST = "sha256:" + "b" * 64


def test_main_pins_the_space_to_a_digest_not_a_tag(monkeypatch):
    calls = []
    monkeypatch.setattr(deploy_space, "HfApi", lambda: "api")
    monkeypatch.setattr(deploy_space, "deploy_pinned_image", lambda *args: calls.append(args))
    monkeypatch.setenv("HF_SPACE_ID", "extralit/public-demo")
    monkeypatch.setenv("DOCKER_REPO", "extralit/extralit-hf-space")
    monkeypatch.setenv("IMAGE_DIGEST", DIGEST)

    deploy_space.main()

    assert calls == [("api", "extralit/public-demo", f"extralit/extralit-hf-space@{DIGEST}")]


def test_main_fails_loudly_on_a_missing_digest(monkeypatch):
    monkeypatch.setattr(deploy_space, "HfApi", lambda: "api")
    monkeypatch.setenv("HF_SPACE_ID", "extralit/public-demo")
    monkeypatch.setenv("DOCKER_REPO", "extralit/extralit-hf-space")
    monkeypatch.delenv("IMAGE_DIGEST", raising=False)

    with pytest.raises(KeyError):
        deploy_space.main()

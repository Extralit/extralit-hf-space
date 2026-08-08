"""Tests for ``scripts/deploy_pr_space.py`` — preview Space create-then-pin."""

from __future__ import annotations

import json

import deploy_pr_space
import pytest


class FakeApi:
    def __init__(self, exists=True):
        self._exists = exists
        self.duplicated = []
        self.uploads = []
        self.secrets = {}
        self.variables = {}

    def space_info(self, repo_id):
        if not self._exists:
            raise deploy_pr_space.RepositoryNotFoundError("404")
        return {"id": repo_id}

    def duplicate_space(self, source, to_id=None, exist_ok=False, hardware=None):
        self.duplicated.append((source, to_id))

    def upload_file(self, *, path_or_fileobj, path_in_repo, repo_id, repo_type, commit_message):
        self.uploads.append((path_in_repo, path_or_fileobj.decode()))

    def add_space_secret(self, repo_id, key, value, description=None):
        self.secrets[key] = value

    def add_space_variable(self, repo_id, key, value, description=None):
        self.variables[key] = value


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_x")
    monkeypatch.setenv("SOURCE_SPACE", "extralit-dev/develop")
    monkeypatch.setenv("PR_SPACE_SLUG", "pr-42")
    monkeypatch.setenv("DOCKER_REPO", "extralitdev/extralit-hf-space")
    monkeypatch.setenv("IMAGE_DIGEST", "sha256:" + "c" * 64)
    monkeypatch.setenv("ALL_SECRETS", "{}")
    monkeypatch.setenv("ALL_VARS", json.dumps({"EXTRALIT_S3_ENDPOINT": "https://s3", "DOCKER_REPO": "nope"}))


def _install(monkeypatch, api):
    pins = []
    monkeypatch.setattr(deploy_pr_space, "HfApi", lambda token=None: api)
    monkeypatch.setattr(deploy_pr_space, "deploy_pinned_image", lambda *args: pins.append(args))
    return pins


def test_main_pins_the_preview_by_digest_not_by_tag(env, monkeypatch):
    api = FakeApi(exists=True)
    pins = _install(monkeypatch, api)

    deploy_pr_space.main()

    assert pins == [(api, "extralit-dev/pr-42", "extralitdev/extralit-hf-space@sha256:" + "c" * 64)]


def test_main_never_overwrites_the_duplicated_dockerfile(env, monkeypatch):
    api = FakeApi(exists=True)
    _install(monkeypatch, api)

    deploy_pr_space.main()

    # A whole-file Dockerfile write drops the source Space's `COPY .oauth.yaml`, which
    # silently disables HF login on the preview. Only deploy_pinned_image may touch it.
    assert [path for path, _ in api.uploads if path == "Dockerfile"] == []


def test_main_still_propagates_only_extralit_vars(env, monkeypatch):
    api = FakeApi(exists=True)
    _install(monkeypatch, api)

    deploy_pr_space.main()

    assert api.variables == {"EXTRALIT_S3_ENDPOINT": "https://s3"}

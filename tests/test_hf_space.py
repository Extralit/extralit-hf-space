"""Tests for ``scripts/hf_space.py`` — the shared HF Space deploy helpers."""

from __future__ import annotations

import json

import pytest
from hf_space import deploy_pinned_image, filter_prefixed, pin_dockerfile
from huggingface_hub import SpaceStage

# Verbatim from https://huggingface.co/spaces/extralit/public-demo/raw/main/Dockerfile.
# Overwriting this with a bare `FROM` line is what silently disabled HF login on previews.
PUBLIC_DEMO_DOCKERFILE = """\
FROM extralit/extralit-hf-space:latest

# Copy the auth config section
COPY .oauth.yaml /home/extralit/

# Uncoment this line to remove the persistence storage warning
ENV EXTRALIT_SHOW_HUGGINGFACE_SPACE_PERSISTENT_STORAGE_WARNING=false
"""

DIGEST_PIN = "extralit/extralit-hf-space@sha256:" + "a" * 64


def test_filter_prefixed_keeps_only_the_prefix():
    raw = json.dumps(
        {
            "EXTRALIT_DATABASE_URL": "postgres://x",
            "EXTRALIT_S3_ENDPOINT": "https://s3",
            "HF_TOKEN": "hf_secret",
            "DOCKER_USERNAME": "user",
            "DOCKER_PASSWORD": "pw",
            "GITHUB_TOKEN": "ghs_secret",
            "EXTRALITX_FOO": "not-ours",
        }
    )
    assert filter_prefixed(raw, "EXTRALIT_") == {
        "EXTRALIT_DATABASE_URL": "postgres://x",
        "EXTRALIT_S3_ENDPOINT": "https://s3",
    }


def test_filter_prefixed_on_malformed_json_returns_empty():
    assert filter_prefixed("{not json", "EXTRALIT_") == {}
    assert filter_prefixed("", "EXTRALIT_") == {}


def test_pin_dockerfile_preserves_the_rest_of_the_public_demo_dockerfile():
    out = pin_dockerfile(PUBLIC_DEMO_DOCKERFILE, DIGEST_PIN)

    assert out.splitlines()[0] == f"FROM {DIGEST_PIN}"
    assert "COPY .oauth.yaml /home/extralit/" in out
    assert "ENV EXTRALIT_SHOW_HUGGINGFACE_SPACE_PERSISTENT_STORAGE_WARNING=false" in out


def test_pin_dockerfile_leaves_no_stray_tag():
    out = pin_dockerfile("FROM repo/image:v1.2.3\n", DIGEST_PIN)

    assert out == f"FROM {DIGEST_PIN}\n"


def test_pin_dockerfile_keeps_the_stage_alias():
    out = pin_dockerfile("FROM repo/image:latest AS base\nRUN true\n", DIGEST_PIN)

    assert out == f"FROM {DIGEST_PIN} AS base\nRUN true\n"


def test_pin_dockerfile_is_idempotent():
    once = pin_dockerfile(PUBLIC_DEMO_DOCKERFILE, DIGEST_PIN)

    assert pin_dockerfile(once, DIGEST_PIN) == once


def test_pin_dockerfile_on_an_already_pinned_file_changes_nothing():
    pinned = pin_dockerfile(PUBLIC_DEMO_DOCKERFILE, DIGEST_PIN)

    assert pin_dockerfile(pinned, DIGEST_PIN) == pinned


def test_pin_dockerfile_without_a_from_line_raises():
    with pytest.raises(ValueError):
        pin_dockerfile("# no FROM here\nRUN true\n", DIGEST_PIN)


class FakeRuntime:
    def __init__(self, stage):
        self.stage = stage


class FakeApi:
    """Records calls so the skip branch can be asserted without mocking libraries."""

    def __init__(self, tmp_path, dockerfile):
        self._path = tmp_path / "Dockerfile"
        self._path.write_text(dockerfile)
        self.uploads = []
        self.waits = 0

    def hf_hub_download(self, repo_id, filename, repo_type=None):
        return str(self._path)

    def upload_file(self, *, path_or_fileobj, path_in_repo, repo_id, repo_type, commit_message):
        self.uploads.append(path_or_fileobj.decode())
        self._path.write_text(path_or_fileobj.decode())

    def get_space_runtime(self, repo_id):
        return FakeRuntime(SpaceStage.RUNNING)

    def wait_for_space(self, repo_id, timeout=None, poll_interval=None):
        self.waits += 1
        return FakeRuntime(SpaceStage.RUNNING)


def test_deploy_pinned_image_skips_upload_and_wait_when_already_pinned(tmp_path):
    already = pin_dockerfile(PUBLIC_DEMO_DOCKERFILE, DIGEST_PIN)
    api = FakeApi(tmp_path, already)

    runtime = deploy_pinned_image(api, "extralit/public-demo", DIGEST_PIN)

    assert api.uploads == []
    assert api.waits == 0
    assert runtime.stage == SpaceStage.RUNNING


def test_deploy_pinned_image_uploads_and_waits_when_the_digest_changed(tmp_path, monkeypatch):
    monkeypatch.setattr("hf_space.time.sleep", lambda _seconds: None)
    api = FakeApi(tmp_path, PUBLIC_DEMO_DOCKERFILE)

    deploy_pinned_image(api, "extralit/public-demo", DIGEST_PIN)

    assert len(api.uploads) == 1
    assert api.uploads[0].startswith(f"FROM {DIGEST_PIN}\n")
    assert "COPY .oauth.yaml /home/extralit/" in api.uploads[0]
    assert api.waits == 1


def test_deploy_pinned_image_raises_when_the_space_does_not_settle_running(tmp_path, monkeypatch):
    monkeypatch.setattr("hf_space.time.sleep", lambda _seconds: None)
    api = FakeApi(tmp_path, PUBLIC_DEMO_DOCKERFILE)
    api.wait_for_space = lambda repo_id, timeout=None, poll_interval=None: FakeRuntime(SpaceStage.BUILD_ERROR)

    with pytest.raises(RuntimeError):
        deploy_pinned_image(api, "extralit/public-demo", DIGEST_PIN)

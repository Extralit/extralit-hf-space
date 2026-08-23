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
            "EXTRALIT_STORAGE_URL": "s3://extralit",
            "HF_TOKEN": "hf_secret",
            "DOCKER_USERNAME": "user",
            "DOCKER_PASSWORD": "pw",
            "GITHUB_TOKEN": "ghs_secret",
            "EXTRALITX_FOO": "not-ours",
        }
    )
    assert filter_prefixed(raw, "EXTRALIT_") == {
        "EXTRALIT_DATABASE_URL": "postgres://x",
        "EXTRALIT_STORAGE_URL": "s3://extralit",
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
    """Records calls so the branch taken can be asserted without mocking libraries.

    ``stages`` is consumed one entry per ``get_space_runtime`` poll, the last one repeating,
    which is what lets a test replay "the Hub still reports the pre-commit stage".
    """

    def __init__(self, tmp_path, dockerfile, stages=(SpaceStage.RUNNING,), settled=SpaceStage.RUNNING):
        self._path = tmp_path / "Dockerfile"
        self._path.write_text(dockerfile)
        self._stages = list(stages)
        self._settled = settled
        self.uploads = []
        self.polls = 0
        self.waits = 0

    def hf_hub_download(self, repo_id, filename, repo_type=None):
        return str(self._path)

    def upload_file(self, *, path_or_fileobj, path_in_repo, repo_id, repo_type, commit_message):
        self.uploads.append(path_or_fileobj.decode())
        self._path.write_text(path_or_fileobj.decode())

    def get_space_runtime(self, repo_id):
        self.polls += 1
        return FakeRuntime(self._stages.pop(0) if len(self._stages) > 1 else self._stages[0])

    def wait_for_space(self, repo_id, timeout=None, poll_interval=None):
        self.waits += 1
        return FakeRuntime(self._settled)


@pytest.fixture
def instant_sleep(monkeypatch):
    monkeypatch.setattr("hf_space.time.sleep", lambda _seconds: None)


def test_deploy_pinned_image_skips_upload_and_wait_when_already_pinned(tmp_path):
    already = pin_dockerfile(PUBLIC_DEMO_DOCKERFILE, DIGEST_PIN)
    api = FakeApi(tmp_path, already)

    runtime = deploy_pinned_image(api, "extralit/public-demo", DIGEST_PIN)

    assert api.uploads == []
    assert api.waits == 0
    assert runtime.stage == SpaceStage.RUNNING


def test_deploy_pinned_image_waits_when_already_pinned_but_still_building(tmp_path):
    # The create path: the rendered template pinned the digest, so the commit that triggered
    # the build was the template upload, not this one. Reporting mid-build would be a lie.
    already = pin_dockerfile(PUBLIC_DEMO_DOCKERFILE, DIGEST_PIN)
    api = FakeApi(tmp_path, already, stages=(SpaceStage.BUILDING,))

    deploy_pinned_image(api, "extralit-dev/pr-42", DIGEST_PIN)

    assert api.uploads == []
    assert api.waits == 1


def test_deploy_pinned_image_uploads_and_waits_when_the_digest_changed(tmp_path, instant_sleep):
    api = FakeApi(tmp_path, PUBLIC_DEMO_DOCKERFILE, stages=(SpaceStage.BUILDING,))

    deploy_pinned_image(api, "extralit/public-demo", DIGEST_PIN)

    assert len(api.uploads) == 1
    assert api.uploads[0].startswith(f"FROM {DIGEST_PIN}\n")
    assert "COPY .oauth.yaml /home/extralit/" in api.uploads[0]
    assert api.waits == 1


def test_deploy_pinned_image_does_not_accept_the_stage_from_before_the_commit(tmp_path, instant_sleep):
    # The Hub reports the pre-commit RUNNING for two polls before scheduling the build. Waiting
    # straight away would return that stale RUNNING and green-light the previous image.
    api = FakeApi(
        tmp_path,
        PUBLIC_DEMO_DOCKERFILE,
        stages=(SpaceStage.RUNNING, SpaceStage.RUNNING, SpaceStage.BUILDING),
    )

    deploy_pinned_image(api, "extralit/public-demo", DIGEST_PIN)

    assert api.polls == 3
    assert api.waits == 1


def test_deploy_pinned_image_raises_when_the_rebuild_never_starts(tmp_path, instant_sleep):
    api = FakeApi(tmp_path, PUBLIC_DEMO_DOCKERFILE, stages=(SpaceStage.RUNNING,))

    with pytest.raises(RuntimeError, match="never started building"):
        deploy_pinned_image(api, "extralit/public-demo", DIGEST_PIN)

    assert api.waits == 0


def test_deploy_pinned_image_raises_when_the_space_does_not_settle_running(tmp_path, instant_sleep):
    api = FakeApi(
        tmp_path,
        PUBLIC_DEMO_DOCKERFILE,
        stages=(SpaceStage.BUILDING,),
        settled=SpaceStage.BUILD_ERROR,
    )

    with pytest.raises(RuntimeError, match="settled in"):
        deploy_pinned_image(api, "extralit/public-demo", DIGEST_PIN)


def test_deploy_pinned_image_accepts_a_space_that_built_then_went_to_sleep(tmp_path, instant_sleep):
    # SLEEPING is absent from SpaceStage in huggingface_hub 1.26.0, so it arrives as a bare
    # string; extralit-dev/develop sits in it between deploys. It is a built Space, not a
    # failed one, and rejecting it would fail the deploy that just succeeded.
    api = FakeApi(tmp_path, PUBLIC_DEMO_DOCKERFILE, stages=(SpaceStage.BUILDING,), settled="SLEEPING")

    runtime = deploy_pinned_image(api, "extralit-dev/develop", DIGEST_PIN)

    assert runtime.stage == "SLEEPING"

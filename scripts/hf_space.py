"""Shared helpers for deploying a Hugging Face Space to a freshly built image.

Imported by ``deploy_space.py`` (updates an existing Space) and ``deploy_pr_space.py``
(creates then updates an ephemeral preview Space). Both run as ``python scripts/<name>.py``,
which puts this directory on ``sys.path[0]``, so a plain ``import hf_space`` resolves with no
packaging.

  Never add ``scripts/secrets.py``, ``scripts/types.py`` or ``scripts/logging.py`` — the same
  mechanism would shadow those stdlib modules for ``huggingface_hub``'s transitive deps.
"""

from __future__ import annotations

import json
import re
import time

from huggingface_hub import SpaceStage

_FROM_LINE = re.compile(r"^FROM\s+\S+", re.M)


def filter_prefixed(raw: str, prefix: str) -> dict[str, str]:
    """Parse a JSON object of env vars and keep only the keys carrying ``prefix``."""
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {}
    return {k: v for k, v in data.items() if k.startswith(prefix)}


def pin_dockerfile(text: str, image_ref: str) -> str:
    """Rewrite the first ``FROM`` line to ``image_ref``, leaving every other byte alone.

    Rewriting rather than replacing the file is what keeps a Space's own
    ``COPY .oauth.yaml`` / ``ENV`` lines — and therefore its HF login — alive.
    """
    out, found = _FROM_LINE.subn(lambda _m: f"FROM {image_ref}", text, count=1)
    if not found:
        raise ValueError("No FROM line to pin in the Dockerfile")
    return out


def deploy_pinned_image(api, space_id: str, image_ref: str):
    """Point ``space_id``'s Dockerfile at ``image_ref`` and block until it is RUNNING.

    Commit-to-rebuild, not ``restart_space``: the restart API rejects OIDC tokens with a 401.
    """
    with open(api.hf_hub_download(space_id, "Dockerfile", repo_type="space")) as fh:
        before = fh.read()
    after = pin_dockerfile(before, image_ref)

    if after == before:
        # Already serving this ref, so a no-op commit would trigger no rebuild to wait for.
        print(f"{space_id} already pinned to {image_ref}")
        runtime = api.get_space_runtime(space_id)
    else:
        print(f"Pinning {space_id} to {image_ref}")
        api.upload_file(
            path_or_fileobj=after.encode(),
            path_in_repo="Dockerfile",
            repo_id=space_id,
            repo_type="space",
            commit_message=f"Deploy {image_ref}",
        )
        # wait_for_space returns at the first non-build poll, which is the stale RUNNING.
        time.sleep(30)
        runtime = api.wait_for_space(space_id, timeout=2700, poll_interval=10)

    print(f"Stage: {runtime.stage}")
    # The rebuild is async, so without this a BUILD_ERROR still reports a green deploy.
    if runtime.stage != SpaceStage.RUNNING:
        raise RuntimeError(f"Deploy failed: {space_id} settled in {runtime.stage}")
    return runtime

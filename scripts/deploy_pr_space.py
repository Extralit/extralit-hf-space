#!/usr/bin/env python
"""Create/update an ephemeral PR preview Space and propagate its runtime config.

Invoked by the ``deploy-pr-space`` job in ``.github/workflows/build-hf-space.yml``.

Flow:
  1. Duplicate ``SOURCE_SPACE`` -> ``<org>/<PR_SPACE_SLUG>`` on first run (writing a
     minimal README), otherwise reuse the existing Space.
  2. Propagate ``EXTRALIT_*`` config from the ``staging`` GitHub environment onto the Space.
     ``duplicate_space`` copies files but NOT secrets/variables, so without this a PR
     Space has no DB/S3/auth config. GitHub env *secrets* -> Space secrets; *variables*
     -> Space variables. Strictly filtered to ``EXTRALIT_*`` so ``HF_TOKEN`` / ``DOCKER_*``
     / the GitHub token are never pushed. Done BEFORE the Dockerfile upload so the first
     build already has the env present.
  3. Upload a one-line ``Dockerfile`` pinning the Space to the PR's image tag.

Configuration is read entirely from environment variables:
  HF_TOKEN, SOURCE_SPACE, PR_SPACE_SLUG, DOCKER_REPO, IMAGE_TAG,
  ALL_SECRETS / ALL_VARS  (JSON objects, typically ``toJSON(secrets)``/``toJSON(vars)``).
"""

from __future__ import annotations

import json
import os

from huggingface_hub import HfApi
from huggingface_hub.errors import RepositoryNotFoundError

PR_README = """\
---
title: Extralit PR Preview
emoji: '\U0001f4bb'
colorFrom: purple
colorTo: red
sdk: docker
app_port: 6900
fullWidth: true
license: apache-2.0
hf_oauth: true
---
"""


def _filter_extralit(raw: str) -> dict[str, str]:
    """Parse a JSON object of env vars and keep only the ``EXTRALIT_*`` keys."""
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {}
    return {k: v for k, v in data.items() if k.startswith("EXTRALIT_")}


def main() -> None:
    api = HfApi(token=os.environ["HF_TOKEN"])
    source = os.environ["SOURCE_SPACE"]
    org = source.split("/")[0]
    target = f"{org}/{os.environ['PR_SPACE_SLUG']}"
    docker_repo = os.environ["DOCKER_REPO"]
    image_tag = os.environ["IMAGE_TAG"]

    try:
        api.space_info(target)
        print(f"Space '{target}' already exists")
    except RepositoryNotFoundError as exc:
        # RepositoryNotFoundError covers 401 as well as 404 — the Hub returns 401 for a
        # private repo rather than leak whether it exists. Only a 404 means "not created
        # yet"; a bad/expired HF_TOKEN must fail loudly here instead of silently falling
        # through to duplicate_space and failing later with a confusing error.
        response = getattr(exc, "response", None)
        if response is None or response.status_code != 404:
            raise
        print(f"Creating '{target}' from '{source}'")
        api.duplicate_space(source, to_id=target, exist_ok=True, hardware="cpu-basic")
        api.upload_file(
            path_or_fileobj=PR_README.encode(),
            path_in_repo="README.md",
            repo_id=target,
            repo_type="space",
            commit_message="Enable HF OAuth",
        )

    space_secrets = _filter_extralit(os.environ.get("ALL_SECRETS", ""))
    space_vars = _filter_extralit(os.environ.get("ALL_VARS", ""))

    for key in sorted(space_secrets):
        api.add_space_secret(repo_id=target, key=key, value=space_secrets[key], description="from CI staging env")
        print(f"  secret   -> {key}")
    for key in sorted(space_vars):
        api.add_space_variable(repo_id=target, key=key, value=space_vars[key], description="from CI staging env")
        print(f"  variable -> {key}")
    print(f"Synced {len(space_secrets)} secret(s) + {len(space_vars)} variable(s) to {target}")

    dockerfile = f"FROM {docker_repo}:{image_tag}\n"
    api.upload_file(
        path_or_fileobj=dockerfile.encode(),
        path_in_repo="Dockerfile",
        repo_id=target,
        repo_type="space",
        commit_message=f"Deploy {docker_repo}:{image_tag}",
    )
    print(f"Deployed {target} -> {docker_repo}:{image_tag}")
    print(f"URL: https://huggingface.co/spaces/{target}")


if __name__ == "__main__":
    main()

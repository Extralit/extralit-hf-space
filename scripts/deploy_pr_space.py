#!/usr/bin/env python
"""Create/update an ephemeral PR preview Space and propagate its runtime config.

Invoked by the ``deploy-pr-space`` job in ``.github/workflows/build-hf-space.yml``.

Flow:
  1. Duplicate ``SOURCE_SPACE`` -> ``<org>/<PR_SPACE_SLUG>`` on first run, then render
     ``space_template/`` over the per-Space config the copy inherited. Otherwise reuse the
     existing Space and leave its config alone.
  2. Propagate ``EXTRALIT_*`` config from the ``staging`` GitHub environment onto the Space.
     ``duplicate_space`` copies files but NOT secrets/variables, so without this a PR
     Space has no DB/S3/auth config. GitHub env *secrets* -> Space secrets; *variables*
     -> Space variables. Strictly filtered to ``EXTRALIT_*`` so ``HF_TOKEN`` / ``DOCKER_*``
     / the GitHub token are never pushed. Done BEFORE the Dockerfile upload so the first
     build already has the env present.
  3. Settle the build. On create the rendered Dockerfile already carries the digest, so this
     only waits; on later runs it rewrites the ``FROM`` line and waits for that rebuild. Only
     that line is ever rewritten — the rest of the file carries ``COPY .oauth.yaml``, without
     which the server registers no OAuth provider and ``hf_oauth: true`` is inert.

Configuration is read entirely from environment variables:
  HF_TOKEN, SOURCE_SPACE, PR_SPACE_SLUG, DOCKER_REPO, IMAGE_DIGEST,
  ALL_SECRETS / ALL_VARS  (JSON objects, typically ``toJSON(secrets)``/``toJSON(vars)``).
"""

from __future__ import annotations

import os
from pathlib import Path

from hf_space import deploy_pinned_image, filter_prefixed, render_space_files, workspaces_value
from huggingface_hub import HfApi
from huggingface_hub.errors import RepositoryNotFoundError

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "space_template"
# Mirrors SOURCE_SPACE's own allowlist; the server creates these at startup if absent.
PR_WORKSPACES = ["public", "test"]
# Every file the manifest declares: a duplicate inherits SOURCE_SPACE's, so anything left out
# here silently carries that Space's drift into the preview instead of the committed template.
CREATE_FILES = ["README.md", ".oauth.yaml", "Dockerfile"]


def main() -> None:
    api = HfApi(token=os.environ["HF_TOKEN"])
    source = os.environ["SOURCE_SPACE"]
    org = source.split("/")[0]
    target = f"{org}/{os.environ['PR_SPACE_SLUG']}"
    # A digest, not `:pr-N`: that tag is re-pushed every build, so HF can reuse a stale base.
    image_ref = f"{os.environ['DOCKER_REPO']}@{os.environ['IMAGE_DIGEST']}"

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
        # duplicate_space copies the source Space's README and allowlist verbatim, so the
        # preview would otherwise run without hf_oauth and against the source's workspaces.
        rendered = render_space_files(
            TEMPLATE_DIR,
            {
                "TITLE": "Extralit PR Preview",
                "WORKSPACES": workspaces_value(PR_WORKSPACES),
                "IMAGE_REF": image_ref,
            },
        )
        for name in CREATE_FILES:
            api.upload_file(
                path_or_fileobj=rendered[name].encode(),
                path_in_repo=name,
                repo_id=target,
                repo_type="space",
                commit_message=f"Render {name} from space_template",
            )

    space_secrets = filter_prefixed(os.environ.get("ALL_SECRETS", ""), "EXTRALIT_")
    space_vars = filter_prefixed(os.environ.get("ALL_VARS", ""), "EXTRALIT_")

    for key in sorted(space_secrets):
        api.add_space_secret(repo_id=target, key=key, value=space_secrets[key], description="from CI staging env")
        print(f"  secret   -> {key}")
    for key in sorted(space_vars):
        api.add_space_variable(repo_id=target, key=key, value=space_vars[key], description="from CI staging env")
        print(f"  variable -> {key}")
    print(f"Synced {len(space_secrets)} secret(s) + {len(space_vars)} variable(s) to {target}")

    deploy_pinned_image(api, target, image_ref)
    print(f"URL: https://huggingface.co/spaces/{target}")


if __name__ == "__main__":
    main()

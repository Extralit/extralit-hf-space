#!/usr/bin/env python
"""Pin the long-lived prod/staging Space to the image the ``build`` job just pushed.

Invoked by the ``deploy-space`` job in ``.github/workflows/build-hf-space.yml``, which
authenticates keylessly via Trusted Publishers (``HF_OIDC_RESOURCE`` + ``id-token: write``);
``HfApi()`` picks that exchange up with no token argument.

Flow:
  1. Download the Space's current ``Dockerfile``.
  2. Rewrite its ``FROM`` line to ``DOCKER_REPO@IMAGE_DIGEST`` — the *only* line touched, so
     the Space's own ``COPY .oauth.yaml`` / ``ENV`` lines and README stay as they are. This
     job updates an existing Space; it must never render a template over one.
  3. Commit if that changed anything, then wait for the rebuild to start and settle.

Configuration is read entirely from environment variables:
  HF_SPACE_ID, DOCKER_REPO, IMAGE_DIGEST
"""

from __future__ import annotations

import os

from hf_space import deploy_pinned_image
from huggingface_hub import HfApi


def main() -> None:
    space_id = os.environ["HF_SPACE_ID"]
    # A digest, not a tag: a re-pushed tag lets HF reuse a stale base and ship the wrong version.
    image_ref = f"{os.environ['DOCKER_REPO']}@{os.environ['IMAGE_DIGEST']}"
    deploy_pinned_image(HfApi(), space_id, image_ref)
    print(f"URL: https://huggingface.co/spaces/{space_id}")


if __name__ == "__main__":
    main()

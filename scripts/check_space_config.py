#!/usr/bin/env python
"""Report where the live Spaces have drifted from ``space_template/``. Never writes.

``space_template/`` is only honest if something compares it to reality: nothing else in this
repo renders it over the long-lived Spaces, and `deploy-space` deliberately never will. This
also doubles as disaster recovery — a deleted ``.oauth.yaml`` is otherwise unrecoverable,
since it exists only in the Space repos.

Read-only by construction: it downloads, diffs, and prints. Keep it out of any job holding
``id-token: write``.

Flow:
  1. Render ``space_template/`` once per Space in ``SPACES``, using that Space's variables.
  2. Download the same files from the live Space.
  3. Compare semantically — parsed YAML for ``README.md`` frontmatter and ``.oauth.yaml``,
     text for the ``Dockerfile`` below its ``FROM`` line (which is a digest CI owns).
  4. Print the drift and exit non-zero if there is any.

Configuration is read entirely from environment variables:
  HF_TOKEN (optional; the Spaces are public, so anonymous reads work)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml
from hf_space import render_space_files, workspaces_value
from huggingface_hub import HfApi
from huggingface_hub.errors import EntryNotFoundError

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "space_template"

# What each long-lived Space is *supposed* to look like. Drift is either a Space someone
# edited by hand or a stale entry here; the report does not presume which.
SPACES = {
    "extralit/public-demo": {
        "COLOR_FROM": "blue",
        "COLOR_TO": "green",
        "LICENSE": "agpl-3.0",
        "TAGS": "[data extraction]",
        "HF_OAUTH": "false",
        "WORKSPACES": workspaces_value(["itn-recalibration", "extralit"]),
    },
    "extralit-dev/develop": {
        "COLOR_FROM": "purple",
        "COLOR_TO": "red",
        "LICENSE": "apache-2.0",
        "TAGS": "[literature review, data extraction, llm]",
        "HF_OAUTH": "false",
        "WORKSPACES": workspaces_value(["public", "test"]),
    },
}


def _frontmatter(text: str) -> dict:
    parts = text.split("---")
    front = yaml.safe_load(parts[1]) if len(parts) > 2 else {}
    front = dict(front or {})
    # Absent means off for both, so an omitted key is not drift.
    front.setdefault("hf_oauth", False)
    front.setdefault("pinned", False)
    if isinstance(front.get("tags"), list):
        front["tags"] = sorted(front["tags"])
    return front


def _below_from(text: str) -> str:
    body = [line for line in text.splitlines() if not line.startswith("FROM ")]
    return "\n".join(body).strip()


def _diff_mappings(expected: dict, actual: dict) -> list[str]:
    return [
        f"{key}: expected {expected.get(key)!r}, live has {actual.get(key)!r}"
        for key in sorted(set(expected) | set(actual))
        if expected.get(key) != actual.get(key)
    ]


def compare(rendered: dict[str, str], live: dict[str, str]) -> dict[str, list[str]]:
    """Return per-file drift messages; an empty dict means the Space matches the template."""
    drift: dict[str, list[str]] = {}
    for name, expected in rendered.items():
        if name not in live:
            drift[name] = ["missing from the live Space"]
            continue
        if name == "README.md":
            messages = _diff_mappings(_frontmatter(expected), _frontmatter(live[name]))
        elif name.endswith(".yaml"):
            messages = _diff_mappings(yaml.safe_load(expected) or {}, yaml.safe_load(live[name]) or {})
        else:
            # The FROM line is a digest the deploy job owns, so it is expected to differ.
            messages = [] if _below_from(expected) == _below_from(live[name]) else ["differs below the FROM line"]
        if messages:
            drift[name] = messages
    return drift


def _fetch(api: HfApi, space_id: str, names) -> dict[str, str]:
    live = {}
    for name in names:
        try:
            live[name] = Path(api.hf_hub_download(space_id, name, repo_type="space")).read_text()
        except EntryNotFoundError:
            continue
    return live


def main() -> None:
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    drifted = False

    for space_id, variables in SPACES.items():
        rendered = render_space_files(TEMPLATE_DIR, {**variables, "IMAGE_REF": "unused"})
        drift = compare(rendered, _fetch(api, space_id, rendered))
        if not drift:
            print(f"{space_id}: matches space_template/")
            continue
        drifted = True
        print(f"{space_id}: DRIFT")
        for name in sorted(drift):
            for message in drift[name]:
                print(f"  {name}: {message}")

    if drifted:
        # Report only — reconciling means editing the Space or SPACES above, by hand.
        sys.exit(1)


if __name__ == "__main__":
    main()

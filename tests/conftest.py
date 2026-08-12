"""Make ``scripts/`` importable from tests.

Not ``[tool.pytest.ini_options] pythonpath``: that resolves against pytest's rootdir, which
moves the moment this repo is run as a submodule of the ``extralit`` monorepo.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

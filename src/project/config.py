"""Project configuration — paths and environment.

Keeps data locations out of the code so the same code runs everywhere: on your
host, inside the dev container, or on a remote machine. Point at data elsewhere
by setting the DATA_DIR environment variable (the dev container sets it for you).
"""

from __future__ import annotations

import os
from pathlib import Path

# Repo root = two levels up from this file (src/project/config.py).
ROOT = Path(__file__).resolve().parents[2]

# Where data lives. Defaults to the repo's data/ folder; override with DATA_DIR.
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))

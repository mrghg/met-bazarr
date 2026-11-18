"""Provenance of the code that writes a store: version, commit and time."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from metbazarr import __version__

_REPO = Path(__file__).resolve().parents[2]


def producer_version() -> str:
    """The installed met-bazarr version."""
    return __version__


def producer_commit() -> str:
    """The git commit of the met-bazarr checkout, with ``-dirty`` if it has
    uncommitted changes to tracked files, or ``"unknown"`` outside a checkout."""
    try:
        commit = subprocess.run(
            ["git", "-C", str(_REPO), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(_REPO), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{commit}-dirty" if dirty else commit


def utc_now() -> str:
    """The current UTC time as an ISO 8601 string, to the second."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

"""Shared pytest fixtures for palmwtc tests."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pytest

# Force a non-interactive backend so viz tests run headless on CI and macOS.
# Must be set before any ``matplotlib.pyplot`` import.
matplotlib.use("Agg")


@pytest.fixture(scope="session")
def synthetic_sample_dir() -> Path:
    """Path to the bundled synthetic sample dataset.

    Phase 3 populates this with deterministic data via
    ``scripts/make_sample_data.py``. Until then the directory is empty,
    and tests that need real fixture data should be marked
    ``@pytest.mark.requires_real_data`` or skipped.
    """
    from palmwtc.data import sample_dir

    return sample_dir("synthetic")


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Repository root, useful for tests that need adjacent fixture files."""
    return Path(__file__).resolve().parent.parent

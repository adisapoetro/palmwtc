"""Characterization tests for ``palmwtc.viz.style``.

Behaviour ported verbatim from ``flux_chamber/src/flux_visualization.py``
``set_style``. The function is side-effecting on global rcParams +
seaborn theme; we save state, call it, assert the documented mutations,
and restore.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

# ---------------------------------------------------------------------------
# Optional: load the original flux_visualization module for cross-checks
# ---------------------------------------------------------------------------

_ORIGINAL_SRC = Path("/Users/adisapoetro/flux_chamber/src/flux_visualization.py")


def _load_original_module():
    """Import the upstream ``flux_visualization`` module.

    Returns ``None`` when the upstream tree is not present on this machine.
    """
    if not _ORIGINAL_SRC.exists():
        return None
    src_root = _ORIGINAL_SRC.parent.parent  # .../flux_chamber/
    sys.path.insert(0, str(src_root))
    try:
        for mod in (
            "src",
            "src.flux_visualization",
        ):
            if mod in sys.modules:
                del sys.modules[mod]
        module = importlib.import_module("src.flux_visualization")
        return module
    except Exception:
        return None


_ORIGINAL = _load_original_module()


# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------

from palmwtc.viz import style as style_mod  # noqa: E402  (after upstream load)


@pytest.fixture
def saved_rc():
    """Save matplotlib rcParams + restore after the test."""
    saved = plt.rcParams.copy()
    yield
    plt.rcParams.update(saved)


def test_set_style_sets_default_figsize(saved_rc) -> None:
    """``set_style`` must set ``figure.figsize`` to ``(12, 6)``."""
    plt.rcParams["figure.figsize"] = (1.0, 1.0)  # poison
    style_mod.set_style()
    assert tuple(plt.rcParams["figure.figsize"]) == (12.0, 6.0)


def test_set_style_returns_none(saved_rc) -> None:
    """``set_style`` returns ``None`` (it's a side-effecting call)."""
    assert style_mod.set_style() is None


@pytest.mark.skipif(_ORIGINAL is None, reason="upstream flux_chamber not available")
def test_set_style_matches_original(saved_rc) -> None:
    """Calling our ``set_style`` produces the same figsize as the original."""
    style_mod.set_style()
    ours = tuple(plt.rcParams["figure.figsize"])

    plt.rcParams["figure.figsize"] = (1.0, 1.0)
    _ORIGINAL.set_style()
    theirs = tuple(plt.rcParams["figure.figsize"])

    assert ours == theirs

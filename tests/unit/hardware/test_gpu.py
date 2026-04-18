"""Characterization tests for ``palmwtc.hardware.gpu``.

Ported behaviour from ``flux_chamber/src/gpu_utils.py``:
- ``DEVICE`` is ``"cuda"`` when cuML is importable, else ``"cpu"``.
- ``get_isolation_forest(**kwargs)`` returns a cuML IsolationForest when
  ``DEVICE == "cuda"`` (dropping unsupported kwargs), otherwise returns an
  sklearn IsolationForest with the kwargs passed through verbatim.
- Module import must succeed without torch (torch is NOT used by this module;
  cuML is the optional heavy dep and is guarded by try/except at module top).

Tests here avoid importing torch. ``scikit-learn`` is a ``[ml]`` extra;
sklearn-dependent assertions are skipped when sklearn is not installed.
"""

from __future__ import annotations

import importlib.util

import pytest

_HAS_SKLEARN = importlib.util.find_spec("sklearn") is not None
_HAS_CUML = importlib.util.find_spec("cuml") is not None


def test_module_imports_without_torch() -> None:
    """Bare import of ``palmwtc.hardware.gpu`` must never fail.

    The module guards cuML behind try/except and does not touch torch at all,
    so this import succeeds on a core-only install.
    """
    import palmwtc.hardware.gpu  # noqa: F401


def test_device_is_expected_string() -> None:
    """``DEVICE`` is one of the documented backend strings."""
    from palmwtc.hardware.gpu import DEVICE

    assert DEVICE in {"cuda", "cpu"}


def test_device_matches_cuml_availability() -> None:
    """``DEVICE == 'cuda'`` iff cuML is importable; otherwise ``'cpu'``."""
    from palmwtc.hardware.gpu import DEVICE

    expected = "cuda" if _HAS_CUML else "cpu"
    assert expected == DEVICE


def test_detect_device_function_matches_module_constant() -> None:
    """``detect_device()`` returns the same string as the module-level ``DEVICE``."""
    from palmwtc.hardware.gpu import DEVICE, detect_device

    assert detect_device() == DEVICE


@pytest.mark.skipif(not _HAS_SKLEARN, reason="requires [ml] extra (scikit-learn)")
def test_get_isolation_forest_returns_sklearn_on_cpu() -> None:
    """On CPU path, returns an sklearn ``IsolationForest`` with kwargs passed through."""
    from sklearn.ensemble import IsolationForest

    from palmwtc.hardware.gpu import DEVICE, get_isolation_forest

    if DEVICE != "cpu":
        pytest.skip("CPU-specific assertion; DEVICE is cuda here")

    model = get_isolation_forest(
        n_estimators=200,
        max_samples=10000,
        contamination=0.05,
        random_state=42,
    )
    assert isinstance(model, IsolationForest)
    assert model.n_estimators == 200
    assert model.max_samples == 10000
    assert model.contamination == 0.05
    assert model.random_state == 42


@pytest.mark.skipif(not _HAS_SKLEARN, reason="requires [ml] extra (scikit-learn)")
def test_get_isolation_forest_accepts_sklearn_only_kwargs_on_cpu() -> None:
    """kwargs that cuML would drop (``n_jobs``, ``max_features``) are kept for sklearn."""
    from sklearn.ensemble import IsolationForest

    from palmwtc.hardware.gpu import DEVICE, get_isolation_forest

    if DEVICE != "cpu":
        pytest.skip("CPU-specific assertion; DEVICE is cuda here")

    model = get_isolation_forest(n_jobs=-1, max_features=0.8, random_state=0)
    assert isinstance(model, IsolationForest)
    assert model.n_jobs == -1
    assert model.max_features == 0.8


@pytest.mark.skipif(not _HAS_SKLEARN, reason="requires [ml] extra (scikit-learn)")
def test_isolation_forest_fits_synthetic_data() -> None:
    """Behavioural sanity: fitted model exposes sklearn's scoring API."""
    import numpy as np

    from palmwtc.hardware.gpu import get_isolation_forest

    rng = np.random.default_rng(0)
    X = rng.standard_normal((64, 3))
    model = get_isolation_forest(n_estimators=20, random_state=0)
    model.fit(X)
    scores = model.score_samples(X)
    assert scores.shape == (64,)


def test_hardware_package_reexports() -> None:
    """``palmwtc.hardware`` re-exports the two public symbols."""
    import palmwtc.hardware as hw

    assert hasattr(hw, "DEVICE")
    assert hasattr(hw, "get_isolation_forest")
    assert hw.DEVICE in {"cuda", "cpu"}

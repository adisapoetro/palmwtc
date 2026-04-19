"""Smoke tests for ``palmwtc.qc.ml``.

The module is a placeholder/bridge that re-exports the GPU-aware
IsolationForest factory from ``palmwtc.hardware.gpu``. This exists so the
``palmwtc.qc.ml`` namespace is reserved for any future ML-anchored QC
helpers that may need to live alongside the rule-based and breakpoint code.
"""

from __future__ import annotations

import importlib.util

import pytest

_HAS_SKLEARN = importlib.util.find_spec("sklearn") is not None


def test_module_imports() -> None:
    import palmwtc.qc.ml  # noqa: F401


def test_reexports_device_and_factory() -> None:
    from palmwtc.qc.ml import DEVICE, get_isolation_forest

    assert DEVICE in {"cuda", "cpu"}
    assert callable(get_isolation_forest)


def test_reexport_matches_hardware_module() -> None:
    """``palmwtc.qc.ml`` re-exports must be the same objects as the source."""
    from palmwtc.hardware.gpu import DEVICE as DEVICE_HW
    from palmwtc.hardware.gpu import get_isolation_forest as gif_hw
    from palmwtc.qc.ml import DEVICE, get_isolation_forest

    assert DEVICE == DEVICE_HW
    assert get_isolation_forest is gif_hw


@pytest.mark.skipif(not _HAS_SKLEARN, reason="requires [ml] extra (scikit-learn)")
def test_factory_returns_fittable_model() -> None:
    """Smoke: the re-exported factory still produces a fit-able sklearn IF."""
    import numpy as np

    from palmwtc.qc.ml import get_isolation_forest

    rng = np.random.default_rng(0)
    X = rng.standard_normal((50, 2))
    model = get_isolation_forest(n_estimators=10, random_state=0)
    model.fit(X)
    scores = model.score_samples(X)
    assert scores.shape == (50,)

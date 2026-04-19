"""GPU-aware model factories for the ecophysiology pipeline.

Detects RAPIDS/cuML at import time and returns GPU-accelerated models when
available, otherwise falls back silently to sklearn (CPU).

Supported backends:
  - cuda   : NVIDIA GPU with RAPIDS cuML installed
  - cpu    : Apple Silicon (M1/M2) or any machine without cuML

Usage
-----
    from palmwtc.hardware.gpu import get_isolation_forest, DEVICE

    # Prints: "[GPU] Device: cuda" or "[GPU] Device: cpu"
    iforest = get_isolation_forest(n_estimators=200, max_samples=10000,
                                   contamination=0.05, random_state=42)
    iforest.fit(X_train)
    scores = iforest.score_samples(X_all)

Notes
-----
- MinCovDet (MCD) has no cuML equivalent; keep sklearn for that.
- LocalOutlierFactor (LOF) cuML does not support novelty=True mode;
  keep sklearn for LOF as well.
- cuML IsolationForest does not accept n_jobs or max_features kwargs —
  these are silently dropped when running on GPU.
"""

from __future__ import annotations

_CUML_AVAILABLE = False
try:
    import cuml  # noqa: F401

    _CUML_AVAILABLE = True
except ImportError:
    pass


def detect_device() -> str:
    """Return 'cuda' if cuML is importable, else 'cpu'."""
    return "cuda" if _CUML_AVAILABLE else "cpu"


DEVICE: str = detect_device()


# Kwargs not accepted by cuML IsolationForest
_CUML_IF_UNSUPPORTED = frozenset({"n_jobs", "max_features", "warm_start"})


def get_isolation_forest(**kwargs):
    """Return a GPU (cuML) or CPU (sklearn) IsolationForest.

    Drops unsupported kwargs (n_jobs, max_features) when using cuML.
    The returned object has the same .fit() / .score_samples() / .predict()
    interface as sklearn's IsolationForest.
    """
    if DEVICE == "cuda":
        from cuml.ensemble import IsolationForest

        cuml_kwargs = {k: v for k, v in kwargs.items() if k not in _CUML_IF_UNSUPPORTED}
        return IsolationForest(**cuml_kwargs)
    else:
        from sklearn.ensemble import IsolationForest

        return IsolationForest(**kwargs)

"""GPU / MPS detection and GPU-aware scikit-learn wrappers.

Detects an available accelerator (CUDA, Apple MPS, or CPU fallback) at
import time and exposes the result as ``palmwtc.hardware.gpu.DEVICE``.
Provides GPU-aware wrappers for selected scikit-learn estimators:

- :func:`get_isolation_forest` returns a cuML ``IsolationForest`` on CUDA,
  else a scikit-learn ``IsolationForest``.

Graceful CPU fallback is the default; no error is raised if cuML is not
installed.

Notes
-----
- MinCovDet (MCD) has no cuML equivalent; keep sklearn for that.
- LocalOutlierFactor (LOF): cuML does not support ``novelty=True`` mode;
  keep sklearn for LOF as well.
- cuML ``IsolationForest`` does not accept ``n_jobs``, ``max_features``, or
  ``warm_start`` kwargs — these are silently dropped when running on GPU.
"""

from __future__ import annotations

from typing import Any

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
"""Detected accelerator name: one of ``"cuda"``, ``"mps"``, or ``"cpu"``.

Set at import time. Does not update if the accelerator state changes
during a session.
"""

# Kwargs not accepted by cuML IsolationForest
_CUML_IF_UNSUPPORTED = frozenset({"n_jobs", "max_features", "warm_start"})


def get_isolation_forest(**kwargs) -> Any:
    """Return a GPU (cuML) or CPU (sklearn) IsolationForest.

    Accepts the same keyword arguments as
    :class:`sklearn.ensemble.IsolationForest`.  On CUDA, kwargs that cuML
    does not support (``n_jobs``, ``max_features``, ``warm_start``) are
    silently dropped before the cuML constructor is called.

    The returned object exposes the same interface regardless of backend:
    ``.fit(X)``, ``.score_samples(X)``, ``.predict(X)``.

    Parameters
    ----------
    **kwargs
        Keyword arguments forwarded to ``IsolationForest``.  Common ones:

        n_estimators : int, default 100
            Number of trees.
        max_samples : int or float or ``"auto"``, default ``"auto"``
            Number of samples to draw per tree.
        contamination : float or ``"auto"``, default ``"auto"``
            Expected fraction of outliers in the training set.
        random_state : int or None, default None
            Seed for reproducibility.

    Returns
    -------
    cuml.ensemble.IsolationForest or sklearn.ensemble.IsolationForest
        ``cuml.ensemble.IsolationForest`` when :data:`DEVICE` is
        ``"cuda"``; ``sklearn.ensemble.IsolationForest`` otherwise.
        Both share the same ``.fit`` / ``.score_samples`` / ``.predict``
        interface.

    Notes
    -----
    The CUDA fallback chain is: CUDA → CPU (no MPS path because cuML is
    CUDA-only).  The check is performed once at module import via
    :func:`detect_device`; the result is cached in :data:`DEVICE`.

    Examples
    --------
    >>> from palmwtc.hardware.gpu import get_isolation_forest
    >>> iforest = get_isolation_forest(n_estimators=100, random_state=42)  # doctest: +SKIP
    >>> iforest.fit(X_train)  # doctest: +SKIP
    >>> scores = iforest.score_samples(X_all)  # doctest: +SKIP

    References
    ----------
    .. [1] Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2008). Isolation
           forest. *2008 Eighth IEEE International Conference on Data
           Mining*, 413-422. https://doi.org/10.1109/ICDM.2008.17
    """
    if DEVICE == "cuda":
        from cuml.ensemble import IsolationForest

        cuml_kwargs = {k: v for k, v in kwargs.items() if k not in _CUML_IF_UNSUPPORTED}
        return IsolationForest(**cuml_kwargs)
    else:
        from sklearn.ensemble import IsolationForest

        return IsolationForest(**kwargs)

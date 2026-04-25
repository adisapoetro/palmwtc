"""Hardware-detection helpers and GPU-aware estimator factories.

Safe to import on any machine: cuML is guarded by ``try/except`` at module
level and scikit-learn is imported lazily inside :func:`get_isolation_forest`.
No GPU is required — all functions fall back silently to CPU.

Public API
----------
:data:`~palmwtc.hardware.gpu.DEVICE`
    Detected accelerator name (``"cuda"`` or ``"cpu"``), set at import time.
:func:`~palmwtc.hardware.gpu.detect_device`
    Returns the accelerator string; useful for runtime checks.
:func:`~palmwtc.hardware.gpu.get_isolation_forest`
    Returns a cuML ``IsolationForest`` on CUDA, else scikit-learn's.

See :mod:`palmwtc.hardware.gpu` for full details.
"""

from palmwtc.hardware.gpu import DEVICE, detect_device, get_isolation_forest

__all__ = ["DEVICE", "detect_device", "get_isolation_forest"]

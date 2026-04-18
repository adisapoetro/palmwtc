"""palmwtc.hardware — GPU/MPS-aware optional accelerators.

Phase 2 ports from ``flux_chamber/src/gpu_utils.py``. The ``gpu`` module is
safe to import on a core-only install: cuML is guarded by try/except and
sklearn is imported lazily inside ``get_isolation_forest``.
"""

from palmwtc.hardware.gpu import DEVICE, detect_device, get_isolation_forest

__all__ = ["DEVICE", "detect_device", "get_isolation_forest"]

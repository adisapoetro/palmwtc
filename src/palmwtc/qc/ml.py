"""Reserved for ML-based QC (IsolationForest path).

The original ``flux_chamber/src/qc_functions.py`` does **not** contain any
ML-based QC helpers. The IsolationForest / sklearn helpers live in
``flux_qc_fast.py`` (now ``palmwtc.flux.cycles`` — see ``compute_ml_anomaly_flags``).

This module is kept as the canonical home for any future rule-vs-ML QC bridge
helpers (e.g. an IsolationForest-based outlier flag for raw 4 s sensor data).
The plan reserves the ``palmwtc.qc.ml`` namespace so notebooks 020/022 will
have a stable import target if/when such helpers are added.

For the GPU-aware IsolationForest factory, import directly from
``palmwtc.hardware.gpu``:

    from palmwtc.hardware.gpu import get_isolation_forest, DEVICE
"""

from __future__ import annotations

# Re-export the GPU-aware IsolationForest factory so the historical
# "import an ML helper from the QC subpackage" pattern continues to work.
from palmwtc.hardware.gpu import DEVICE, get_isolation_forest

__all__ = ["DEVICE", "get_isolation_forest"]

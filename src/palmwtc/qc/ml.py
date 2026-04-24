"""ML-based quality control via Isolation Forest anomaly flagging.

Rule-based QC (see :mod:`palmwtc.qc.rules`) flags values that violate
known physical bounds or show obvious step changes.  ML-based QC
complements this by catching *subtle distribution drift* — measurements
that are individually plausible but collectively anomalous relative to the
rest of the record.  The recommended workflow is:

1. Run rule-based QC first to remove clearly bad values.
2. Apply :func:`get_isolation_forest` on the rule-accepted values to flag
   statistical outliers that the rules did not catch.

This module re-exports the GPU-aware Isolation Forest factory from
:mod:`palmwtc.hardware.gpu` so that notebooks importing from
``palmwtc.qc.ml`` continue to work without modification.

GPU acceleration path
---------------------
:func:`get_isolation_forest` returns a ``cuml.ensemble.IsolationForest``
instance when a CUDA-capable GPU is available and the ``[gpu]`` extra is
installed.  It falls back silently to
``sklearn.ensemble.IsolationForest`` on CPU-only machines (including
Apple Silicon).  The ``DEVICE`` constant reflects the selected backend
(``'cuda'``, ``'mps'``, or ``'cpu'``).

References
----------
.. [1] Liu, F. T., Ting, K. M., & Zhou, Z.-H. (2008). Isolation
       forest. *2008 Eighth IEEE International Conference on Data
       Mining*, 413-422. https://doi.org/10.1109/ICDM.2008.17

Examples
--------
>>> from palmwtc.qc.ml import get_isolation_forest, DEVICE
>>> isinstance(DEVICE, str)
True
>>> clf = get_isolation_forest(n_estimators=100, contamination=0.05)
>>> hasattr(clf, "fit")
True
"""

from __future__ import annotations

# Re-export the GPU-aware IsolationForest factory so the historical
# "import an ML helper from the QC subpackage" pattern continues to work.
from palmwtc.hardware.gpu import DEVICE, get_isolation_forest

__all__ = ["DEVICE", "get_isolation_forest"]

palmwtc.qc.ml
=============

.. py:module:: palmwtc.qc.ml

.. autoapi-nested-parse::

   ML-based quality control via Isolation Forest anomaly flagging.

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



Attributes
----------

.. autoapisummary::

   palmwtc.qc.ml.DEVICE


Functions
---------

.. autoapisummary::

   palmwtc.qc.ml.get_isolation_forest


Module Contents
---------------

.. py:data:: DEVICE
   :type:  str
   :value: 'cuda'


   Detected accelerator name: one of ``"cuda"``, ``"mps"``, or ``"cpu"``.

   Set at import time. Does not update if the accelerator state changes
   during a session.


.. py:function:: get_isolation_forest(**kwargs) -> Any

   Return a GPU (cuML) or CPU (sklearn) IsolationForest.

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



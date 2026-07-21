palmwtc.hardware.gpu
====================

.. py:module:: palmwtc.hardware.gpu

.. autoapi-nested-parse::

   GPU / MPS detection and GPU-aware scikit-learn wrappers.

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



Attributes
----------

.. autoapisummary::

   palmwtc.hardware.gpu._CUML_AVAILABLE
   palmwtc.hardware.gpu._CUML_AVAILABLE
   palmwtc.hardware.gpu.DEVICE
   palmwtc.hardware.gpu._CUML_IF_UNSUPPORTED


Functions
---------

.. autoapisummary::

   palmwtc.hardware.gpu.detect_device
   palmwtc.hardware.gpu.get_isolation_forest


Module Contents
---------------

.. py:data:: _CUML_AVAILABLE
   :value: False


.. py:data:: _CUML_AVAILABLE
   :value: True


.. py:function:: detect_device() -> str

   Return 'cuda' if cuML is importable, else 'cpu'.


.. py:data:: DEVICE
   :type:  str
   :value: 'cuda'


   Detected accelerator name: one of ``"cuda"``, ``"mps"``, or ``"cpu"``.

   Set at import time. Does not update if the accelerator state changes
   during a session.


.. py:data:: _CUML_IF_UNSUPPORTED

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



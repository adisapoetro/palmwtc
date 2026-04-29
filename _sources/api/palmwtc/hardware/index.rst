palmwtc.hardware
================

.. py:module:: palmwtc.hardware

.. autoapi-nested-parse::

   Hardware-detection helpers and GPU-aware estimator factories.

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



Submodules
----------

.. toctree::
   :maxdepth: 1

   /api/palmwtc/hardware/gpu/index


Attributes
----------

.. autoapisummary::

   palmwtc.hardware.DEVICE


Functions
---------

.. autoapisummary::

   palmwtc.hardware.detect_device
   palmwtc.hardware.get_isolation_forest


Package Contents
----------------

.. py:data:: DEVICE
   :type:  str
   :value: 'cuda'


   Detected accelerator name: one of ``"cuda"``, ``"mps"``, or ``"cpu"``.

   Set at import time. Does not update if the accelerator state changes
   during a session.


.. py:function:: detect_device() -> str

   Return 'cuda' if cuML is importable, else 'cpu'.


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



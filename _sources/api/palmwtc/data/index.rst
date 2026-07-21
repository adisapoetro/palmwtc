palmwtc.data
============

.. py:module:: palmwtc.data

.. autoapi-nested-parse::

   palmwtc.data — bundled sample datasets.

   ``sample/synthetic/`` holds deterministic synthetic chamber cycles (~5 MB) used
   by CI and the zero-config first-run experience. ``sample/real/`` is fetched
   on demand from Zenodo via ``palmwtc sample fetch`` (~10-50 MB, anonymized
   LIBZ data).



Functions
---------

.. autoapisummary::

   palmwtc.data.sample_dir


Package Contents
----------------

.. py:function:: sample_dir(kind: str = 'synthetic') -> pathlib.Path

   Return the on-disk path to a bundled sample dataset.

   Parameters
   ----------
   kind : {"synthetic", "real"}
       ``"synthetic"`` is bundled with the package wheel and always present.
       ``"real"`` is fetched on-demand via ``palmwtc sample fetch`` and may
       not exist until then.



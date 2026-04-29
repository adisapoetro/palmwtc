palmwtc.notebooks_runner
========================

.. py:module:: palmwtc.notebooks_runner

.. autoapi-nested-parse::

   palmwtc.notebooks_runner — Papermill-mode pipeline orchestrator.

   Ported from ``flux_chamber/scripts/run_notebooks.py`` with these changes:

   - Notebook directory is now resolved via ``DataPaths.extras['notebooks_dir']``
     rather than walking up from the script location.
   - Output directory mirrors that resolution.
   - Spine/parallel split preserved exactly.
   - Thread-saturation env vars set as before.
   - ``BATCH_MODE=1`` set by default so widget cells gracefully skip.

   The library-mode equivalent (no papermill, faster, headless) lives in
   ``palmwtc.pipeline``. Use this module when you want the full executed
   HTML reports as documentation of a run.



Attributes
----------

.. autoapisummary::

   palmwtc.notebooks_runner._DEFAULT_THREADS
   palmwtc.notebooks_runner.SPINE_PREFIXES


Classes
-------

.. autoapisummary::

   palmwtc.notebooks_runner.NotebookResult


Functions
---------

.. autoapisummary::

   palmwtc.notebooks_runner.discover_notebooks
   palmwtc.notebooks_runner._convert_to_html
   palmwtc.notebooks_runner._run_with_papermill
   palmwtc.notebooks_runner.run_notebooks


Module Contents
---------------

.. py:data:: _DEFAULT_THREADS
   :value: ''


.. py:data:: SPINE_PREFIXES

.. py:class:: NotebookResult

   Outcome of executing one notebook.


   .. py:attribute:: name
      :type:  str


   .. py:attribute:: ok
      :type:  bool


   .. py:attribute:: elapsed_seconds
      :type:  float


   .. py:attribute:: error
      :type:  str
      :value: ''



.. py:function:: discover_notebooks(notebooks_dir: pathlib.Path) -> list[dict]

   Find .ipynb files in ``notebooks_dir`` root (no subdirs), return sorted metadata.


.. py:function:: _convert_to_html(nb_path: pathlib.Path, html_path: pathlib.Path) -> None

   Convert an executed .ipynb to a clean HTML report (no code cells).


.. py:function:: _run_with_papermill(nb_path: pathlib.Path, output_path: pathlib.Path, timeout: int) -> tuple[bool, float, str]

   Execute a notebook via papermill. Returns (success, elapsed, error_msg).


.. py:function:: run_notebooks(notebooks_dir: pathlib.Path, output_dir: pathlib.Path | None = None, *, start: int | None = None, only: list[int] | None = None, skip: list[int] | None = None, timeout: int = 1800, inplace: bool = False, keep_going: bool = False, parallel: int = 1) -> list[NotebookResult]

   Run all notebooks in ``notebooks_dir``, sorted by numeric prefix.

   See ``flux_chamber/scripts/run_notebooks.py`` for the original CLI shape.
   The behaviour here is byte-equivalent: spine notebooks (010/020/030/040)
   run sequentially first, then non-spine notebooks run with ``parallel``
   workers (default 1 = sequential).



palmwtc.pipeline
================

.. py:module:: palmwtc.pipeline

.. autoapi-nested-parse::

   palmwtc.pipeline — Library-mode pipeline orchestrator (no papermill).

   A faster, headless alternative to ``palmwtc.notebooks_runner``. Calls the
   ported library functions directly, in the same logical order as the
   notebook spine (010 → 020 → 030 → 035), but without the notebook
   execution overhead.

   Use ``palmwtc.pipeline.run_pipeline()`` from a Python script or
   ``palmwtc run`` from the CLI.

   Steps (each is independently runnable):

   - ``"qc"`` — load QC parquet (or ingest raw if ``raw_dir`` points at TOA5)
   - ``"flux"`` — compute CO2 + H2O flux cycles, score them, identify days
   - ``"windows"`` — select high-confidence calibration windows
   - ``"validation"`` — science validation against literature ecophysiology bounds

   The current implementation runs end-to-end against the bundled synthetic
   sample with thin step bodies; production callers will typically replace
   :func:`step_qc` and :func:`step_flux` with calls into the algorithm-rich
   helpers under :mod:`palmwtc.qc` and :mod:`palmwtc.flux` directly.



Attributes
----------

.. autoapisummary::

   palmwtc.pipeline.STEPS_IN_ORDER
   palmwtc.pipeline._DEFAULT_CHAMBER_TREE_MAP
   palmwtc.pipeline._STEP_FUNCTIONS


Classes
-------

.. autoapisummary::

   palmwtc.pipeline.StepResult
   palmwtc.pipeline.PipelineResult


Functions
---------

.. autoapisummary::

   palmwtc.pipeline._find_qc_parquet
   palmwtc.pipeline._apply_tree_volume_correction
   palmwtc.pipeline.step_qc
   palmwtc.pipeline.step_flux
   palmwtc.pipeline.step_windows
   palmwtc.pipeline.step_validation
   palmwtc.pipeline.run_pipeline
   palmwtc.pipeline.run_step


Module Contents
---------------

.. py:data:: STEPS_IN_ORDER
   :type:  tuple[str, Ellipsis]
   :value: ('qc', 'flux', 'windows', 'validation')


.. py:class:: StepResult

   Outcome of one pipeline step.


   .. py:attribute:: name
      :type:  str


   .. py:attribute:: ok
      :type:  bool


   .. py:attribute:: elapsed_seconds
      :type:  float


   .. py:attribute:: rows_in
      :type:  int
      :value: 0



   .. py:attribute:: rows_out
      :type:  int
      :value: 0



   .. py:attribute:: artefacts
      :type:  list[pathlib.Path]
      :value: []



   .. py:attribute:: metrics
      :type:  dict[str, Any]


   .. py:attribute:: error
      :type:  str
      :value: ''



.. py:class:: PipelineResult

   Aggregate of all pipeline step results.


   .. py:attribute:: paths
      :type:  palmwtc.config.DataPaths


   .. py:attribute:: steps
      :type:  list[StepResult]
      :value: []



   .. py:attribute:: total_seconds
      :type:  float
      :value: 0.0



   .. py:property:: ok
      :type: bool



   .. py:method:: summary() -> str


.. py:function:: _find_qc_parquet(paths: palmwtc.config.DataPaths) -> pathlib.Path

   Locate the QC parquet in either the user's processed_dir or the bundled sample.


.. py:data:: _DEFAULT_CHAMBER_TREE_MAP

.. py:function:: _apply_tree_volume_correction(cycles_df: pandas.DataFrame, paths: palmwtc.config.DataPaths) -> pandas.DataFrame

   Re-compute `flux_absolute` per cycle with tree-volume correction.

   Mirrors flux_chamber/notebooks/030 cell 18:
       chamber_flux_df["tree_volume"] = chamber_flux_df["flux_date"].apply(
           lambda d: get_tree_volume_at_date(df_vigor, tree_id, d)
       )
       chamber_flux_df["flux_absolute"] = chamber_flux_df.apply(calculate_absolute_flux, axis=1)

   Opt-in via ``paths.extras["correct_tree_volume"] = True`` in palmwtc.yaml.
   Default OFF (matches the post-cutover flux_chamber baseline). When opted-in
   and biophysics fail to load, emits a warning rather than silently no-op'ing
   so users know why ``tree_volume`` is missing from the cycles output.


.. py:function:: step_qc(paths: palmwtc.config.DataPaths) -> StepResult

   Load QC parquet and verify the artefact is loadable; no rule re-application.


.. py:function:: step_flux(paths: palmwtc.config.DataPaths, qc_df: pandas.DataFrame | None = None) -> StepResult

   Compute CO2 + H2O flux cycles from QC'd data, looping over chambers.

   Detects which chambers are present (C1, C2) by scanning column names for
   ``CO2_C<n>``. For each chamber: prepare, run cycles, tag, concatenate.
   Writes the unified cycles CSV to ``exports_dir/digital_twin/``.


.. py:function:: step_windows(paths: palmwtc.config.DataPaths, cycles_df: pandas.DataFrame | None = None) -> StepResult

   Select high-confidence calibration windows from cycle output.


.. py:function:: step_validation(paths: palmwtc.config.DataPaths, cycles_df: pandas.DataFrame | None = None) -> StepResult

   Run science validation against literature ecophysiology bounds.


.. py:data:: _STEP_FUNCTIONS

.. py:function:: run_pipeline(paths: palmwtc.config.DataPaths, *, steps: list[str] | None = None, skip: list[str] | None = None, keep_going: bool = False) -> PipelineResult

   Run the library-mode pipeline against ``paths``.

   Parameters
   ----------
   paths : DataPaths
       Resolved I/O paths (use ``DataPaths.resolve()``).
   steps : list[str], optional
       Explicit list of steps to run, in the order given. Defaults to the
       full ordered spine ``("qc", "flux", "windows", "validation")``.
   skip : list[str], optional
       Step names to skip. Applied after ``steps`` filter.
   keep_going : bool, default False
       If False, stops at the first failed step. If True, runs all steps
       regardless of upstream failures.


.. py:function:: run_step(name: str, paths: palmwtc.config.DataPaths) -> StepResult

   Run a single pipeline step by name. Convenience for notebook cells.



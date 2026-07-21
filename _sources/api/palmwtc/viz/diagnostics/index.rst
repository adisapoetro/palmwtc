palmwtc.viz.diagnostics
=======================

.. py:module:: palmwtc.viz.diagnostics

.. autoapi-nested-parse::

   Cycle-level diagnostic plots for chamber flux QC review.

   Provides functions to inspect individual measurement cycles from the
   whole-tree chamber flux pipeline.  Each function creates a matplotlib
   figure showing CO₂ concentration traces, regression fits, and residuals
   so that flux quality can be reviewed visually.

   Public functions
   ----------------
   :func:`plot_chamber_resizing_validation`
       Time-series scatter around the chamber resizing event with a
       rolling-mean trend and a vertical marker at the resize date.
   :func:`plot_cycle_diagnostics`
       Fit + residual panels for a single cycle, with optional WPL
       correction labelling.
   :func:`plot_specific_cycle`
       Locate a cycle by chamber name and datetime string, then call
       :func:`plot_cycle_diagnostics`.
   :func:`plot_cycle_by_id`
       Locate a cycle by chamber name and integer cycle ID, then call
       :func:`plot_cycle_diagnostics`.
   :func:`show_sample_cycles`
       Draw ``n`` random cycles from a QC tier and plot each one.



Functions
---------

.. autoapisummary::

   palmwtc.viz.diagnostics.plot_chamber_resizing_validation
   palmwtc.viz.diagnostics.plot_cycle_diagnostics
   palmwtc.viz.diagnostics.plot_specific_cycle
   palmwtc.viz.diagnostics.plot_cycle_by_id
   palmwtc.viz.diagnostics.show_sample_cycles


Module Contents
---------------

.. py:function:: plot_chamber_resizing_validation(flux_df: pandas.DataFrame, resize_date: str = '2025-07-01', variable: str = 'flux_absolute') -> matplotlib.pyplot.Figure | None

   Plot the flux signal in a ±60-day window around the chamber resizing date.

   Creates one subplot per chamber (stacked vertically) showing the chosen
   flux variable as a scatter plot, a 50-point centred rolling-mean trend
   line, and a vertical dashed line marking the resize date.  Use this to
   check for artefacts (step changes, drift) introduced by the physical
   chamber adjustment.

   Parameters
   ----------
   flux_df : pandas.DataFrame
       Flux results table.  Must contain columns:

       - ``flux_date`` (datetime64) — timestamp of each flux cycle.
       - ``Source_Chamber`` (str) — chamber identifier
         (e.g. ``"Chamber 1"``).
       - ``<variable>`` (float) — the flux column to plot.

   resize_date : str, default ``"2025-07-01"``
       ISO-format date string for the chamber resizing event.  Passed to
       :func:`pandas.to_datetime`.
   variable : str, default ``"flux_absolute"``
       Name of the column in *flux_df* to plot on the y-axis.

   Returns
   -------
   matplotlib.figure.Figure or None
       The figure object, or ``None`` if *flux_df* is empty or no data
       falls within the ±60-day window.

   Notes
   -----
   The rolling trend uses a window of 50 cycles centred on each point.
   This smooths noise without over-fitting at the edges of the window.

   Examples
   --------
   >>> from palmwtc.viz.diagnostics import plot_chamber_resizing_validation
   >>> fig = plot_chamber_resizing_validation(flux_df, resize_date="2025-07-01")  # doctest: +SKIP


.. py:function:: plot_cycle_diagnostics(raw_df: pandas.DataFrame, flux_row: pandas.Series, apply_wpl: bool = False) -> None

   Plot a single flux cycle with its fit line, residuals, and QC metadata.

   Produces a 1x2 figure:

   - **Left panel** — CO₂ concentration vs. time.  Shows the raw wet CO₂
     signal (gray, if available), the dry (or WPL-corrected) CO₂ used for
     fitting (blue), the fitting window subset (orange), and the regression
     fit line (red dashed).
   - **Right panel** — Residuals of the fit within the fitting window.

   After displaying the figure, prints the QC reason string and, when
   *apply_wpl* is ``True`` and ``wpl_delta_ppm`` is present in *raw_df*,
   also prints the median WPL delta and 95th-percentile relative change.

   Parameters
   ----------
   raw_df : pandas.DataFrame
       Raw chamber time-series.  Must contain columns:

       - ``TIMESTAMP`` (datetime64) — measurement time.
       - ``CO2`` (float) — dry (or WPL-corrected) CO₂ concentration (ppm).
       - ``CO2_raw`` (float, optional) — uncorrected wet CO₂ concentration
         (ppm).  Plotted in gray if present.
       - ``wpl_delta_ppm`` (float, optional) — WPL correction magnitude.
         Printed if *apply_wpl* is ``True``.
       - ``wpl_rel_change`` (float, optional) — relative WPL change.
         Printed if *apply_wpl* is ``True``.

   flux_row : pandas.Series
       Single row from a flux results DataFrame.  Must contain:

       - ``flux_date`` (datetime64) — cycle start time.
       - ``cycle_duration_sec`` (float) — cycle length in seconds.
       - ``window_start_sec`` (float) — fit window start offset (s).
       - ``window_end_sec`` (float) — fit window end offset (s).
       - ``flux_slope`` (float) — regression slope (ppm s⁻¹).
       - ``flux_intercept`` (float) — regression intercept (ppm).
       - ``flux_qc_label`` (str) — QC tier label.
       - ``cycle_id`` (int or float) — unique cycle identifier.
       - ``Source_Chamber`` (str) — chamber name.
       - ``qc_reason`` (str, optional) — human-readable QC reason.

   apply_wpl : bool, default False
       If ``True``, label the CO₂ trace as WPL-corrected and print WPL
       summary statistics after the plot.

   Returns
   -------
   None
       Displays the figure inline (calls :func:`matplotlib.pyplot.show`)
       and prints QC metadata to stdout.  Does not return the figure object.

   Notes
   -----
   The function returns early (prints a message, no figure) if no raw data
   falls within the cycle window, or if the fitting window subset is empty.

   Examples
   --------
   >>> from palmwtc.viz.diagnostics import plot_cycle_diagnostics
   >>> plot_cycle_diagnostics(raw_df, flux_row)  # doctest: +SKIP


.. py:function:: plot_specific_cycle(data: pandas.DataFrame, raw_lookup: dict, chamber: str, date_str: str, apply_wpl: bool = False) -> None

   Plot diagnostics for a cycle identified by chamber name and datetime string.

   Finds the cycle in *data* whose ``flux_date`` is closest to *date_str*
   (within 2 seconds), then delegates to :func:`plot_cycle_diagnostics`.

   Parameters
   ----------
   data : pandas.DataFrame
       Flux results table.  Must contain ``Source_Chamber`` (str) and
       ``flux_date`` (datetime64) columns.
   raw_lookup : dict[str, pandas.DataFrame]
       Mapping from chamber name to the corresponding raw time-series
       DataFrame.  Same structure as the *raw_df* argument of
       :func:`plot_cycle_diagnostics`.
   chamber : str
       Chamber name to filter on (e.g. ``"Chamber 1"``).
   date_str : str
       Target datetime in ``"DD/MM/YY HH:MM:SS"`` format (day-first).
   apply_wpl : bool, default False
       Forwarded to :func:`plot_cycle_diagnostics`.

   Returns
   -------
   None
       Calls :func:`plot_cycle_diagnostics` and returns nothing.  Prints
       an informative message if the cycle or raw data cannot be found.

   Notes
   -----
   The 2-second tolerance on ``flux_date`` matching covers the rounding
   that may occur when timestamps are stored at 1 Hz resolution.

   Examples
   --------
   >>> from palmwtc.viz.diagnostics import plot_specific_cycle
   >>> plot_specific_cycle(data, raw_lookup, "Chamber 1", "01/07/25 08:30:00")  # doctest: +SKIP


.. py:function:: plot_cycle_by_id(data: pandas.DataFrame, raw_lookup: dict, chamber: str, cycle_id: int | float, apply_wpl: bool = False) -> None

   Plot diagnostics for a cycle identified by chamber name and cycle ID.

   Finds the row in *data* matching *chamber* and *cycle_id*, then
   delegates to :func:`plot_cycle_diagnostics`.

   Parameters
   ----------
   data : pandas.DataFrame
       Flux results table.  Must contain ``Source_Chamber`` (str) and
       ``cycle_id`` (int or float) columns.
   raw_lookup : dict[str, pandas.DataFrame]
       Mapping from chamber name to raw time-series DataFrame.
   chamber : str
       Chamber name (e.g. ``"Chamber 1"``).
   cycle_id : int or float
       Numeric cycle identifier.  Compared with
       :func:`numpy.isclose` to handle floating-point IDs.
   apply_wpl : bool, default False
       Forwarded to :func:`plot_cycle_diagnostics`.

   Returns
   -------
   None
       Calls :func:`plot_cycle_diagnostics` and returns nothing.  Prints
       an informative message if the cycle or raw data cannot be found.

   Examples
   --------
   >>> from palmwtc.viz.diagnostics import plot_cycle_by_id
   >>> plot_cycle_by_id(data, raw_lookup, "Chamber 1", cycle_id=1042)  # doctest: +SKIP


.. py:function:: show_sample_cycles(data: pandas.DataFrame, raw_lookup: dict, tier: int | str, n: int = 5, seed: int = 42, label: str | None = None, apply_wpl: bool = False) -> None

   Plot a random sample of cycles from a given QC tier.

   Randomly draws up to *n* cycles from the rows where ``flux_qc == tier``
   and calls :func:`plot_cycle_diagnostics` for each one.

   Parameters
   ----------
   data : pandas.DataFrame
       Flux results table.  Must contain ``flux_qc`` (int or str) and
       ``Source_Chamber`` (str) columns, plus all columns required by
       :func:`plot_cycle_diagnostics`.
   raw_lookup : dict[str, pandas.DataFrame]
       Mapping from chamber name to raw time-series DataFrame.
   tier : int or str
       QC tier value to filter on (e.g. ``1``, ``2``, ``"HQ"``).
   n : int, default 5
       Maximum number of cycles to plot.  If fewer than *n* cycles exist
       in the tier, all available cycles are shown.
   seed : int, default 42
       Random seed passed to :meth:`pandas.DataFrame.sample` for
       reproducible sampling.
   label : str or None, default None
       Display label for the printed header.  Defaults to
       ``"QC tier <tier>"`` when ``None``.
   apply_wpl : bool, default False
       Forwarded to :func:`plot_cycle_diagnostics` for each cycle.

   Returns
   -------
   None
       Calls :func:`plot_cycle_diagnostics` for each sampled cycle.
       Prints a header line and skips chambers with no raw data loaded.

   Examples
   --------
   >>> from palmwtc.viz.diagnostics import show_sample_cycles
   >>> show_sample_cycles(data, raw_lookup, tier=1, n=3, seed=0)  # doctest: +SKIP



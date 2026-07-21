palmwtc.viz
===========

.. py:module:: palmwtc.viz

.. autoapi-nested-parse::

   Visualization helpers — static (matplotlib) and interactive (plotly).

   Five families:

   - :mod:`~palmwtc.viz.style` — rcParams defaults for consistent look.
   - :mod:`~palmwtc.viz.timeseries` — seasonal / diurnal / tree-age patterns, flux heatmaps.
   - :mod:`~palmwtc.viz.diagnostics` — per-cycle inspection plots.
   - :mod:`~palmwtc.viz.qc_plots` — QC flag visualisations.
   - :mod:`~palmwtc.viz.interactive` — Plotly-based interactive dashboards (use inside Jupyter only).

   All static helpers (``style``, ``diagnostics``, ``timeseries``, ``qc_plots``) work
   on a core install.  Interactive helpers require ``palmwtc[interactive]`` for
   ipywidgets / anywidget; bare imports succeed without the extra, but calling
   the dashboard raises an informative error at runtime.



Submodules
----------

.. toctree::
   :maxdepth: 1

   /api/palmwtc/viz/diagnostics/index
   /api/palmwtc/viz/interactive/index
   /api/palmwtc/viz/qc_plots/index
   /api/palmwtc/viz/style/index
   /api/palmwtc/viz/timeseries/index


Functions
---------

.. autoapisummary::

   palmwtc.viz.plot_chamber_resizing_validation
   palmwtc.viz.plot_cycle_by_id
   palmwtc.viz.plot_cycle_diagnostics
   palmwtc.viz.plot_specific_cycle
   palmwtc.viz.show_sample_cycles
   palmwtc.viz.interactive_flux_dashboard
   palmwtc.viz.filter_plot
   palmwtc.viz.plot_breakpoints_analysis
   palmwtc.viz.plot_drift_and_hq_timeseries
   palmwtc.viz.plot_qc_comparison
   palmwtc.viz.plot_qc_summary_heatmap
   palmwtc.viz.plot_soil_var
   palmwtc.viz.visualize_breakpoints
   palmwtc.viz.visualize_missing_data
   palmwtc.viz.visualize_qc_flags
   palmwtc.viz.set_style
   palmwtc.viz.plot_concentration_slope_vs_tree_age
   palmwtc.viz.plot_flux_heatmap
   palmwtc.viz.plot_flux_vs_tree_age
   palmwtc.viz.plot_tropical_seasonal_diurnal


Package Contents
----------------

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


.. py:function:: interactive_flux_dashboard(flux_df: pandas.DataFrame, chamber_raw: dict[str, pandas.DataFrame], stride: int = 15, renderer: str = 'plotly_mimetype', replace_previous: bool = True, debug: bool = True, enable_detail: bool = True, detail_max_points_overview: int = 80000, detail_max_points_zoom: int = 400000, detail_debounce_s: float = 0.25) -> None

   Multi-chamber flux dashboard with QC filters and zoom-to-reveal detail.

   Renders an ipywidgets-based dashboard in Jupyter with two sections:

   1. **Overview panel** — all chambers stacked, measured CO2 (thinned by
      *stride*) above and flux scatter below, coloured per chamber.
   2. **Detail panel** (when *enable_detail* is ``True``) — one chamber at
      a time, starting from the full overview density; as you zoom in,
      more raw points are loaded from the full dataset up to
      *detail_max_points_zoom*.

   Widget controls:

   * *Measured CO2 QC* dropdown — filter the raw CO2 scatter by flag
     (All / Flag 0 only / Flags 0+1).
   * *Flux Data QC* dropdown — filter the flux scatter by ``qc_flag``.
   * *Detail Chamber* dropdown — select which chamber to show in the
     detail panel.
   * *Show detail* checkbox — toggle the detail panel on/off.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Cycle-level flux results. Must contain:

       ``Source_Chamber`` : str
           Chamber identifier (e.g. ``"Chamber 1"``). Matched against
           keys in *chamber_raw*.
       ``flux_date`` : datetime-like
           Cycle timestamp. Plotted on the x-axis of flux sub-panels.
       ``flux_absolute`` : float
           Flux value shown in the overview and detail flux sub-panels.
       ``qc_flag`` : int
           Quality flag used by the flux filter dropdown.
       ``cycle_id`` : int or str, optional
           Shown in the hover tooltip. A placeholder column is used if
           absent.
   chamber_raw : dict[str, pd.DataFrame]
       Mapping from chamber name to raw logger data. Each value must
       contain:

       ``TIMESTAMP`` : datetime-like
           Logger timestamp. Converted to datetime in place on first call.
       ``CO2`` : float
           Raw CO2 concentration (ppm). Plotted in the measured CO2
           sub-panels.
       ``Flag`` : int, optional
           Used by the *Measured CO2 QC* filter dropdown.
   stride : int
       Downsample step applied to raw CO2 data in the overview.
       Every *stride*-th row is kept. Default ``15``.
   renderer : str
       Plotly renderer string passed to ``pio.renderers.default`` and
       ``fig.show()``. Default ``"plotly_mimetype"`` (standard Jupyter).
   replace_previous : bool
       If ``True``, close any widgets from a previous call in the same
       kernel and clear output before rendering. Default ``True``.
   debug : bool
       Print diagnostic lines (renderer name, chamber list) to stdout.
       Default ``True``.
   enable_detail : bool
       Whether to build and show the detail panel with its extra widgets.
       Set to ``False`` to show only the overview. Default ``True``.
   detail_max_points_overview : int
       Maximum raw CO2 points shown in the detail panel at full zoom-out.
       Default ``80_000``.
   detail_max_points_zoom : int
       Maximum raw CO2 points loaded into the detail panel when zoomed in.
       Default ``400_000``.
   detail_debounce_s : float
       Minimum seconds between successive zoom-triggered data refreshes
       in the detail panel. Prevents excessive updates while panning.
       Default ``0.25``.

   Returns
   -------
   None
       Renders directly into the Jupyter output cell via
       ``IPython.display.display``. No figure object is returned.

   Notes
   -----
   **Requires Jupyter notebook or lab** and the ``palmwtc[interactive]``
   extra (``ipywidgets`` + ``IPython``).  Both packages are imported
   inside the function body so the module stays importable in a
   core-only install, but calling this function without them will raise
   ``ImportError``.

   Outside Jupyter the ``display()`` call silently produces no output.
   Use the ``plot_*_interactive`` helpers above for environments that
   support plain ``fig.show()``.

   The detail panel uses a ``go.FigureWidget`` so that Python callbacks
   (``fig.observe``) can update trace data reactively when the user
   zooms. The overview uses a static ``go.Figure`` re-rendered on each
   filter change.

   Examples
   --------
   >>> from palmwtc.viz.interactive import interactive_flux_dashboard
   >>> interactive_flux_dashboard(  # doctest: +SKIP
   ...     flux_df,
   ...     chamber_raw={"Chamber 1": raw1_df, "Chamber 2": raw2_df},
   ... )

   See Also
   --------
   plot_flux_timeseries_tiers_interactive : Simpler static tiered
       timeseries figure (no widgets, returns a Figure).
   palmwtc.viz.diagnostics.plot_cycle_diagnostics : Static matplotlib
       diagnostic panels for individual cycles.


.. py:function:: filter_plot(ax: matplotlib.axes.Axes, df_: pandas.DataFrame, col_c1: str, col_c2: str, var_key: str, var_config: dict, use_physical_limits: bool = True, ylim_padding_frac: float = 0.06) -> None

   Draw a two-chamber overlay for one variable onto an existing axis.

   Plots the Chamber 1 series (blue) and Chamber 2 series (red) for the
   variable ``var_key``.  When ``use_physical_limits=True``, points outside
   the hard bounds are removed before plotting, and hard/soft threshold
   lines are drawn as dashed/dotted horizontal lines.

   The y-axis is locked to the range of the *plotted* data plus
   ``ylim_padding_frac`` padding on each side, so threshold lines never
   expand the visible range beyond the data.

   Parameters
   ----------
   ax : matplotlib.axes.Axes
       Axes to draw on.  The function modifies ``ax`` in place and
       returns ``None``.
   df_ : pd.DataFrame
       DataFrame with a ``TIMESTAMP`` column and the sensor columns.
       Must contain:

       ``TIMESTAMP`` : pd.Timestamp
           Datetime column used for the x-axis.
       ``{col_c1}`` : numeric, optional
           Chamber 1 values.
       ``{col_c2}`` : numeric, optional
           Chamber 2 values.
   col_c1 : str
       Column name for Chamber 1 data in ``df_``.
   col_c2 : str
       Column name for Chamber 2 data in ``df_``.
   var_key : str
       Key used to look up the variable's configuration inside
       ``var_config``.
   var_config : dict
       Mapping ``{var_key: config_dict}``.  The ``config_dict`` may
       contain:

       ``"hard"`` : tuple of (float, float)
           (min, max) hard bounds.  Points outside are removed when
           ``use_physical_limits=True``.  Drawn as red dashed lines.
       ``"soft"`` : tuple of (float, float)
           (min, max) soft bounds.  Drawn as orange dotted lines.
       ``"label"`` : str
           Y-axis label.
       ``"title"`` : str
           Axis title.
   use_physical_limits : bool, optional
       If ``True``, remove values outside hard bounds before plotting and
       draw threshold lines.  Default: ``True``.
   ylim_padding_frac : float, optional
       Fraction of data range added as padding above and below the
       y-axis limits.  Default: 0.06.

   Returns
   -------
   None
       The axis is modified in place.

   Notes
   -----
   If ``var_key`` is not found in ``var_config``, the function sets a
   plain title and grid, then returns without plotting.

   If neither chamber column contains any valid (non-NaN, in-bounds) data,
   the function likewise returns after setting the title.

   Examples
   --------
   >>> import matplotlib.pyplot as plt
   >>> from palmwtc.viz.qc_plots import filter_plot
   >>> fig, ax = plt.subplots()
   >>> filter_plot(ax, df, "C1_CO2", "C2_CO2", "CO2", var_config)  # doctest: +SKIP

   See Also
   --------
   plot_soil_var : Similar helper for multi-depth soil variables.


.. py:function:: plot_breakpoints_analysis(df: pandas.DataFrame, var_name: str, breakpoint_result: dict | None, qc_flag_col: str | None = None, figsize: tuple[float, float] = (16, 10), max_table_rows: int = 15, min_confidence: float = 0.0, show_all_breakpoints: bool = False) -> tuple[matplotlib.figure.Figure, matplotlib.figure.Figure] | tuple[None, None]

   Two-figure breakpoint analysis: annotated timeseries + breakpoint table.

   **Figure 1 -- Analysis plot** (2x2 grid):

   - **Panel 1 (top, full width)**: Flag-0 sensor timeseries (green)
     with vertical dashed lines at each breakpoint, coloured by index
     using the ``Set1`` colormap.  A diamond marker is placed on the
     series at each breakpoint timestamp.  Horizontal red lines show the
     segment mean for each interval between breakpoints.  Downsampled to
     50 000 points for performance when the dataset is larger.
   - **Panel 2 (bottom-left)**: Bar chart of segment means with +/-1 SD
     error bars.
   - **Panel 3 (bottom-right)**: Bar chart of breakpoint confidence
     scores (0-1).  An orange dashed line at 0.5 marks a rough
     "moderate confidence" threshold.

   **Figure 2 -- Table plot**: plain matplotlib table listing breakpoint
   number, timestamp (``YYYY-MM-DD HH:MM``), and confidence with a
   "Robust / Moderate / Weak" label (>= 0.7 / >= 0.4 / < 0.4).  Up to
   ``max_table_rows`` rows; additional rows replaced with ``"..."`` if
   the list is truncated.  The table always shows all raw breakpoints
   (ignoring ``min_confidence``).

   Parameters
   ----------
   df : pd.DataFrame
       QC-flagged DataFrame indexed by datetime.  Must contain:

       ``{var_name}`` : numeric
           Sensor values.
       ``{qc_flag_col}`` : int in {0, 1, 2}, optional
           QC flag column.  Only Flag-0 rows are plotted.  If absent,
           all non-NaN values are used.
   var_name : str
       Name of the sensor variable column.
   breakpoint_result : dict or None
       Breakpoint detection output from
       :func:`palmwtc.qc.breakpoints.detect_breakpoints_ruptures`.
       Expected keys:

       ``"breakpoints"`` : list of pd.Timestamp
           Detected breakpoint timestamps.
       ``"confidence_scores"`` : list of float
           Confidence score (0-1) per breakpoint.
       ``"segment_info"`` : list of dict
           Each dict has keys ``"mean"``, ``"std"``, ``"start"``,
           ``"end"``.
       ``"n_breakpoints"`` : int
           Total breakpoint count (used when ``show_all_breakpoints``
           is ``True``).

       Pass ``None`` to get ``(None, None)`` back.
   qc_flag_col : str, optional
       QC flag column name.  Default: ``f"{var_name}_qc_flag"``.
   figsize : tuple of (float, float), optional
       Size of Figure 1 (the analysis plot).  Default: ``(16, 10)``.
   max_table_rows : int, optional
       Maximum rows in the table figure.  Default: 15.
   min_confidence : float, optional
       Minimum confidence score for breakpoints shown in Figure 1.
       Ignored when ``show_all_breakpoints=True``.  Default: 0.0
       (show all).
   show_all_breakpoints : bool, optional
       If ``True``, ignore ``min_confidence`` and plot every breakpoint
       in Figure 1.  Default: ``False``.

   Returns
   -------
   tuple of (matplotlib.figure.Figure, matplotlib.figure.Figure)
       ``(fig_analysis, fig_table)`` -- the two figures.
   tuple of (None, None)
       Returned when ``breakpoint_result`` is ``None`` or no data are
       available for the variable.

   Notes
   -----
   Confidence score thresholds used in the table label:

   - >= 0.7 = "Robust"
   - >= 0.4 = "Moderate"
   - < 0.4  = "Weak"

   Breakpoint detection uses the ``ruptures`` library (L2 cost, PELT
   algorithm).  See :func:`palmwtc.qc.breakpoints.detect_breakpoints_ruptures`
   for details.

   Examples
   --------
   >>> from palmwtc.viz.qc_plots import plot_breakpoints_analysis
   >>> fig1, fig2 = plot_breakpoints_analysis(df, "CO2_Avg", bp_result)  # doctest: +SKIP

   See Also
   --------
   visualize_breakpoints : Three-panel overview with kept/ignored
       distinction, intended for interactive inspection.
   palmwtc.qc.breakpoints.detect_breakpoints_ruptures : Produces the
       ``breakpoint_result`` dict.


.. py:function:: plot_drift_and_hq_timeseries(df: pandas.DataFrame, var_name: str, drift_result: dict | pandas.DataFrame | None, qc_flag_col: str | None = None) -> None

   Two-panel figure: drift score (top) and Flag-0 timeseries (bottom).

   Both panels share the same x-axis (time).  Calls
   :func:`matplotlib.pyplot.show` before returning.

   - **Top panel**: drift score line (purple) from ``drift_result``.
     A horizontal line at y=0 is drawn for reference.
   - **Bottom panel**: Flag-0 sensor values (green) from ``df``.

   If either panel has no data, a text annotation ("No Drift Data" /
   "No High Quality Data Found") is shown instead.

   Parameters
   ----------
   df : pd.DataFrame
       QC-flagged DataFrame indexed by datetime.  Must contain:

       ``{var_name}`` : numeric
           Sensor values.
       ``{qc_flag_col}`` : int in {0, 1, 2}, optional
           QC flag column.  If absent, all non-NaN data are used for
           the bottom panel.
   var_name : str
       Name of the sensor variable column.
   drift_result : dict or pd.DataFrame or None
       Drift detection output from
       :func:`palmwtc.qc.drift.detect_drift_windstats`.  Accepted
       forms:

       - ``dict`` with a ``"scores"`` key whose value is a DataFrame,
         a Series with a ``.to_pd()`` method, or a plain DataFrame.
       - A ``pd.DataFrame`` used directly as the drift score table.

       The expected column in the resolved DataFrame is
       ``f"{var_name}_drift_score"``.  Pass ``None`` to skip drift panel.
   qc_flag_col : str, optional
       QC flag column name.  Default: ``f"{var_name}_qc_flag"``.

   Returns
   -------
   None
       The figure is displayed via :func:`matplotlib.pyplot.show`.

   Notes
   -----
   Flag value 0 = Good (the only data shown in the bottom panel).

   Drift scores are produced by the windowed-statistics drift detector
   in :mod:`palmwtc.qc.drift`.  A score near 0 indicates stable sensor
   baseline; large deviations suggest drift.

   Examples
   --------
   >>> from palmwtc.viz.qc_plots import plot_drift_and_hq_timeseries
   >>> plot_drift_and_hq_timeseries(df, "CO2_Avg", drift_res)  # doctest: +SKIP

   See Also
   --------
   plot_baseline_drift : Daily-minimum view for long-term baseline drift.
   plot_high_quality_timeseries : Flag-0 only, no drift panel.


.. py:function:: plot_qc_comparison(df: pandas.DataFrame, var_names: list[str], qc_results: dict, figsize: tuple[float, float] | None = None) -> matplotlib.figure.Figure

   2x2 panel comparison of QC flag percentages across multiple variables.

   Creates a 2x2 figure with horizontal bar charts:

   - **Panel 1 (top-left)**: Flag 0 (Good) percentage per variable.
     A vertical red dashed line marks 50 %.
   - **Panel 2 (top-right)**: Flag 1 (Suspect) percentage per variable.
   - **Panel 3 (bottom-left)**: Flag 2 (Bad) percentage per variable.
     A vertical orange dashed line marks 10 % as a reference threshold.
   - **Panel 4 (bottom-right)**: Stacked horizontal bar chart showing
     Good + Suspect + Bad as proportions of 100 % for each variable.

   Variables appear in reversed order on the y-axis so the first variable
   in ``var_names`` is at the top of each panel.

   Parameters
   ----------
   df : pd.DataFrame
       QC-flagged DataFrame.  Not directly read inside this function;
       passed for API consistency with other QC plot functions.
   var_names : list of str
       Variable names to include.  Only variables that exist in
       ``qc_results`` are shown.
   qc_results : dict
       Mapping ``{var_name: result_dict}``.  Each ``result_dict`` must
       contain either:

       - A nested ``"summary"`` dict with keys ``"flag_0_percent"``,
         ``"flag_1_percent"``, ``"flag_2_percent"``  (V1 structure), or
       - Those same keys at the top level (V2 flat structure).
   figsize : tuple of (float, float), optional
       Figure width and height in inches.  Default: ``(18, height)``
       where height scales with the number of variables
       (minimum 12 inches).

   Returns
   -------
   matplotlib.figure.Figure
       The 2x2 figure.

   Notes
   -----
   All four panels share the same y-axis variable list.  The x-axis is
   fixed to 0-105 % in all panels so the eye can compare across panels
   without re-scaling.

   Examples
   --------
   >>> from palmwtc.viz.qc_plots import plot_qc_comparison
   >>> fig = plot_qc_comparison(df, ["CO2_Avg", "H2O_Avg"], qc_results)  # doctest: +SKIP

   See Also
   --------
   visualize_qc_flags : Single-variable multi-method breakdown.
   plot_qc_summary_heatmap : Heatmap view of the same percentages.


.. py:function:: plot_qc_summary_heatmap(qc_results: dict, figsize: tuple[float, float] = (14, 10)) -> matplotlib.figure.Figure

   Heatmap of QC pass/suspect/fail percentages for all variables.

   Rows = variables (in the order of ``qc_results`` keys).
   Columns = Flag 0 (Good), Flag 1 (Suspect), Flag 2 (Bad).
   Cell colour uses the ``RdYlGn`` colormap (green = high percentage,
   red = low percentage), anchored at 0-100 %.
   Each cell is annotated with the numeric value ``"XX.X%"``.
   A colourbar on the right shows the percentage scale.

   Parameters
   ----------
   qc_results : dict
       Mapping ``{var_name: result_dict}``.  Each ``result_dict`` must
       contain either a nested ``"summary"`` sub-dict or the summary keys
       at the top level.  Required keys inside the summary:

       ``"flag_0_percent"`` : float
           Percentage of timestamps with Flag 0 (Good).
       ``"flag_1_percent"`` : float
           Percentage of timestamps with Flag 1 (Suspect).
       ``"flag_2_percent"`` : float
           Percentage of timestamps with Flag 2 (Bad).
   figsize : tuple of (float, float), optional
       Figure width and height in inches.

   Returns
   -------
   matplotlib.figure.Figure
       The heatmap figure.

   Notes
   -----
   The three percentage columns for a given variable should sum to
   approximately 100 %.  Small deviations are possible due to rounding.

   Examples
   --------
   >>> from palmwtc.viz.qc_plots import plot_qc_summary_heatmap
   >>> fig = plot_qc_summary_heatmap(qc_results)  # doctest: +SKIP

   See Also
   --------
   plot_qc_comparison : Same percentages as horizontal bar charts.
   visualize_qc_flags : Per-variable, per-method scatter breakdown.


.. py:function:: plot_soil_var(ax: matplotlib.axes.Axes, var_key: str, title_prefix: str, plot_df: pandas.DataFrame, var_config: dict, use_physical_limits: bool = True, ylim_padding_frac: float = 0.06) -> bool

   Draw multi-depth soil sensor profiles onto an existing axis.

   Looks up the column pattern from ``var_config[var_key]["pattern"]``
   and plots each depth as a separate line:

   - 15 cm  (blue)
   - 48 cm  (orange)
   - 80 cm  (green)
   - 200 cm (red)
   - 350 cm (purple)

   Expected column name format: ``{pattern}_{depth}_Avg_Soil``
   (e.g. ``SWC_15_Avg_Soil``).  Missing depths are silently skipped.

   Hard/soft threshold lines are drawn when ``use_physical_limits=True``.
   The y-axis is locked to the range of plotted data plus padding.

   Parameters
   ----------
   ax : matplotlib.axes.Axes
       Axes to draw on.  Modified in place; returns a status boolean.
   var_key : str
       Key used to look up the variable's configuration in ``var_config``.
   title_prefix : str
       String prepended to the axis title (e.g. the site name or
       measurement period).
   plot_df : pd.DataFrame
       Data to plot.  Must contain:

       ``TIMESTAMP`` : pd.Timestamp
           Datetime column used for the x-axis.
       ``{pattern}_{depth}_Avg_Soil`` : numeric
           One column per depth that should be shown.
   var_config : dict
       Mapping ``{var_key: config_dict}``.  The ``config_dict`` may
       contain:

       ``"pattern"`` : str
           Column-name prefix (e.g. ``"SWC"``).
       ``"hard"`` : tuple of (float, float)
           Hard bounds; points outside are removed when
           ``use_physical_limits=True``.  Drawn as red dashed lines.
       ``"soft"`` : tuple of (float, float)
           Soft bounds drawn as orange dotted lines.
       ``"label"`` : str
           Y-axis label.
   use_physical_limits : bool, optional
       If ``True``, filter values outside hard bounds and draw threshold
       lines.  Default: ``True``.
   ylim_padding_frac : float, optional
       Fraction of data range added as padding.  Default: 0.06.

   Returns
   -------
   bool
       ``True`` if at least one depth was plotted; ``False`` if no data
       were available or ``var_key`` was not found in ``var_config``.

   Notes
   -----
   The legend uses up to 5 entries (one per depth) plus threshold lines,
   arranged in a single row with ``ncol=5`` to keep the axis compact.

   Examples
   --------
   >>> import matplotlib.pyplot as plt
   >>> from palmwtc.viz.qc_plots import plot_soil_var
   >>> fig, ax = plt.subplots()
   >>> has_data = plot_soil_var(ax, "SWC", "Soil Water Content", df, var_config)  # doctest: +SKIP

   See Also
   --------
   filter_plot : Two-chamber overlay for non-soil variables.


.. py:function:: visualize_breakpoints(df: pandas.DataFrame, var_name: str, bp_result: dict, filtered_bps: list | None = None, title_suffix: str = '') -> None

   Three-panel overview of breakpoints with kept/ignored distinction.

   Plots a 3x1 figure (shared x-axis, monthly tick marks) and prints a
   summary table to stdout.  Calls :func:`matplotlib.pyplot.show` before
   returning.

   - **Panel 1 (top)**: hourly-resampled sensor timeseries (blue line)
     with vertical lines at each breakpoint.  Breakpoints in
     ``filtered_bps`` are drawn solid green (kept); all others are drawn
     dashed red (ignored).
   - **Panel 2 (middle)**: segment means as horizontal coloured lines,
     one colour per segment (``Set3`` colormap).  Mean values are
     annotated above each line.
   - **Panel 3 (bottom)**: bar chart of confidence scores, one orange
     bar per breakpoint.

   After showing the plot, a text table is printed to stdout with columns:
   ``#``, ``Date``, ``Confidence``, ``Prev Mean``, ``New Mean``,
   ``Shift``.  Shows up to 20 breakpoints.

   Parameters
   ----------
   df : pd.DataFrame
       DataFrame indexed by datetime.  Must contain:

       ``{var_name}`` : numeric
           Raw sensor values.  Resampled to 1-hour mean for plotting.
   var_name : str
       Name of the sensor variable column.
   bp_result : dict
       Breakpoint detection output from
       :func:`palmwtc.qc.breakpoints.detect_breakpoints_ruptures`.
       Expected keys:

       ``"n_breakpoints"`` : int
           Total number of detected breakpoints.
       ``"breakpoints"`` : list of pd.Timestamp
           Breakpoint timestamps.
       ``"segment_info"`` : list of dict
           Each dict has keys ``"mean"``, ``"std"``, ``"start"``,
           ``"end"``.
       ``"confidence_scores"`` : list of float
           Confidence score per breakpoint.
   filtered_bps : list of pd.Timestamp, optional
       Subset of breakpoints to mark as "kept" (green solid lines).
       Breakpoints not in this list are drawn red dashed.  If ``None``,
       all breakpoints are drawn red dashed.
   title_suffix : str, optional
       Extra text appended to Panel 1's title (e.g. a date range or
       site label).

   Returns
   -------
   None
       The figure is displayed via :func:`matplotlib.pyplot.show` and
       a summary table is printed to stdout.

   Notes
   -----
   The data is resampled to 1-hour means before plotting so that very
   high-frequency streams (e.g. 4-second LI-850 data) render in a
   reasonable time without explicit downsampling.

   The ``{var_name} (ppm)`` label is used literally on the y-axis of
   Panel 1, so it is most appropriate for CO2 and H2O concentration
   variables.

   Examples
   --------
   >>> from palmwtc.viz.qc_plots import visualize_breakpoints
   >>> visualize_breakpoints(df, "CO2_Avg", bp_result, filtered_bps=kept)  # doctest: +SKIP

   See Also
   --------
   plot_breakpoints_analysis : Two-figure version with a table figure and
       confidence-filtered plotting.
   palmwtc.qc.breakpoints.detect_breakpoints_ruptures : Produces the
       ``bp_result`` dict.


.. py:function:: visualize_missing_data(df: pandas.DataFrame, var_name: str, frequency_seconds: float | None = None, config: dict | None = None, figsize: tuple[float, float] = (15, 8)) -> matplotlib.figure.Figure | None

   Two-panel figure showing data availability and gap distribution.

   Identifies timestamps where the interval between consecutive valid
   readings exceeds ``2.5 * frequency_seconds`` (a "gap") and plots:

   - **Top panel** (3:1 height ratio): raw sensor timeseries (blue line)
     with the title showing the sampling frequency, data coverage, and
     missing-data percentage.  Downsampled to 50 000 points when the
     series is longer.
   - **Bottom panel**: bar chart of gap duration in hours vs time, one
     bar per detected gap.  Uses log scale on the y-axis when any gap
     exceeds 1 hour.

   Parameters
   ----------
   df : pd.DataFrame
       DataFrame with a datetime index.  Must contain:

       ``{var_name}`` : numeric
           Sensor values.  NaN rows are treated as missing.
   var_name : str
       Name of the sensor variable column.
   frequency_seconds : float, optional
       Expected sampling interval in seconds (e.g. 4.0 for a 4 s LI-850
       stream).  If ``None``, the function looks up
       ``config[key]["measurement_frequency"]``; if still not found,
       defaults to 4.0 seconds with a warning printed to stdout.
   config : dict, optional
       Variable configuration dict (same structure as ``var_config``
       used elsewhere).  Searched for ``var_name`` by direct key match,
       ``"columns"`` list membership, or ``"pattern"`` prefix.
   figsize : tuple of (float, float), optional
       Figure width and height in inches.

   Returns
   -------
   matplotlib.figure.Figure or None
       The figure, or ``None`` if ``var_name`` is not in ``df`` or no
       valid data points exist.

   Notes
   -----
   Gap detection threshold: a gap is counted when the time between two
   consecutive non-NaN records exceeds ``2.5 * frequency_seconds``.
   This allows for small timing jitter without false positives.

   The missing-data percentage shown in the title is estimated as::

       missing_pct = (expected_points - actual_points) / expected_points * 100

   where ``expected_points = total_duration_sec / frequency_seconds``.

   Examples
   --------
   >>> from palmwtc.viz.qc_plots import visualize_missing_data
   >>> fig = visualize_missing_data(df, "CO2_Avg", frequency_seconds=4.0)  # doctest: +SKIP

   See Also
   --------
   visualize_qc_flags : Per-rule flag scatter, useful after gaps are
       already filled or excluded.


.. py:function:: visualize_qc_flags(df: pandas.DataFrame, var_name: str, qc_results: dict, config: dict | None = None, figsize: tuple[float, float] = (15, 20)) -> matplotlib.figure.Figure | None

   Multi-panel scatter plot of QC flags with per-method breakdown.

   Produces a figure whose row count adapts to how many QC methods fired:

   - **Row 1** (combined): scatter plot of ``var_name`` coloured by the
     combined ``{var_name}_qc_flag`` column.  Green = Flag 0, orange =
     Flag 1, red x = Flag 2.  Hard/soft bound lines added when ``config``
     is supplied.
   - **Rows 2..N** (one per active method): the raw timeseries in grey
     with flagged points coloured orange (Suspect) or red-x (Bad).
     Active methods checked: Physical Bounds, Persistence, Rate of Change,
     IQR Outliers.
   - **Last row** (summary): left panel = bar chart of flag counts (Good /
     Suspect / Bad); right panel = horizontal bar chart of flag counts by
     method (Bounds / IQR / RoC / Persist).

   Parameters
   ----------
   df : pd.DataFrame
       QC-flagged DataFrame.  Must contain:

       ``{var_name}`` : numeric
           Raw sensor values.
       ``{var_name}_qc_flag`` : int in {0, 1, 2}
           Combined QC flag column.  May be absent if
           ``qc_results["final_flags"]`` is provided instead.
   var_name : str
       Name of the sensor variable column to plot.
   qc_results : dict
       Per-variable QC result dict from
       :func:`palmwtc.qc.process_variable_qc`.  Expected keys:

       ``"final_flags"`` : pd.Series
           Combined flag series (used as fallback if the flag column is
           absent from ``df``).
       ``"bounds_flags"`` : pd.Series or None
           Flags from the Physical Bounds rule.
       ``"persistence_flags"`` : pd.Series or None
           Flags from the Persistence rule.
       ``"roc_flags"`` : pd.Series or None
           Flags from the Rate-of-Change rule.
       ``"iqr_flags"`` : pd.Series or None
           Flags from the IQR Outlier rule.
       ``"summary"`` : dict
           Keys ``"flag_0_count"``, ``"flag_1_count"``, ``"flag_2_count"``.
   config : dict, optional
       Variable configuration used for axis labels and threshold lines.
       Expected keys (all optional):

       ``"label"`` : str
           Y-axis label.
       ``"soft"`` : tuple of (float, float)
           (min, max) soft bounds drawn as orange dashed lines.
       ``"hard"`` : tuple of (float, float)
           (min, max) hard bounds drawn as red dashed lines.
   figsize : tuple of (float, float), optional
       Figure width and height in inches.  Height is overridden upward
       when many method panels are present (4 rows per extra method).

   Returns
   -------
   matplotlib.figure.Figure or None
       The figure, or ``None`` if ``var_name`` is not found in ``df``.

   Notes
   -----
   Flag values:

   - ``0`` = Good (green scatter, small points).
   - ``1`` = Suspect (orange scatter, medium points).
   - ``2`` = Bad (red x scatter, slightly larger points).

   The summary row reads counts from ``qc_results["summary"]``, which
   reflects the full (unfiltered) dataset.

   Examples
   --------
   >>> from palmwtc.viz.qc_plots import visualize_qc_flags
   >>> fig = visualize_qc_flags(df, "CO2_Avg", qc_results["CO2_Avg"])  # doctest: +SKIP

   See Also
   --------
   palmwtc.qc.process_variable_qc : Produces the ``qc_results`` dict
       consumed here.
   plot_qc_comparison : Compare flag percentages across many variables.
   plot_qc_summary_heatmap : Heatmap view across all variables.


.. py:function:: set_style() -> None

   Apply the standard palmwtc matplotlib/seaborn theme.

   Sets the seaborn ``"whitegrid"`` theme and fixes the default figure size
   to ``(12, 6)`` inches.  Call this once at the top of a notebook or script
   before producing any plots.

   Returns
   -------
   None
       This function returns nothing.  It modifies global matplotlib
       rcParams and the seaborn theme as a side effect.

   Notes
   -----
   This function is **side-effecting**: it changes ``matplotlib.rcParams``
   and the active seaborn theme for the entire Python session.  Any plots
   created after calling this function will use the new settings.  To undo,
   call ``matplotlib.rcdefaults()`` or ``seaborn.reset_defaults()``.

   The function is idempotent — calling it multiple times has the same
   result as calling it once.

   Examples
   --------
   >>> from palmwtc.viz.style import set_style
   >>> set_style()  # doctest: +SKIP


.. py:function:: plot_concentration_slope_vs_tree_age(flux_df: pandas.DataFrame, variable: str = 'flux_slope', birth_date_str: str = '2022-07-12') -> matplotlib.pyplot.Figure | None

   Plot raw concentration slope vs tree age, faceted by chamber.

   Plots ppm/s slope (before chamber volume/area correction) against
   tree age in years. Produces one subplot per chamber with a scatter
   layer and a black rolling-mean trend line. This is a sanity check
   for :func:`plot_flux_vs_tree_age`: if the corrected-flux trend
   matches the raw-slope trend, the chamber-size correction is not
   introducing artefacts.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Cycle-level flux data. Must contain:

       ``flux_date`` : datetime-like
           Timestamp of each cycle; used to compute tree age.
       ``Source_Chamber`` : str
           Chamber identifier; one subplot per unique value.
       ``<variable>`` : float
           Raw concentration slope in ppm/s (no chamber-size
           correction applied).
   variable : str, optional
       Column in ``flux_df`` to plot on the y-axis.
       Default is ``"flux_slope"``.
   birth_date_str : str, optional
       ISO-format planting date (``"YYYY-MM-DD"``) for tree-age
       calculation. Default is ``"2022-07-12"``.

   Returns
   -------
   matplotlib.figure.Figure or None
       The figure with one subplot per chamber, or ``None`` if
       ``flux_df`` is empty.

   Notes
   -----
   Tree age is computed the same way as in
   :func:`plot_flux_vs_tree_age` (seconds / 31,557,600). The rolling
   mean uses ``window=200, center=True``.

   Examples
   --------
   >>> from palmwtc.viz.timeseries import plot_concentration_slope_vs_tree_age
   >>> fig = plot_concentration_slope_vs_tree_age(cycles_df)  # doctest: +SKIP


.. py:function:: plot_flux_heatmap(flux_df: pandas.DataFrame, variable: str = 'flux_absolute', title: str = 'Flux Heatmap (Hour vs Month)') -> matplotlib.pyplot.Figure | None

   Heatmap of mean flux by hour-of-day and month-year.

   Produces three vertically stacked subplots:

   1. Overall (all chambers combined).
   2. Chamber 1 only.
   3. Chamber 2 only.

   Each subplot has hour of day (0-23) on the y-axis and month-year
   periods on the x-axis. Cell colour encodes mean flux, centred at
   zero (``RdBu_r`` palette: red = positive efflux, blue = uptake).

   Parameters
   ----------
   flux_df : pd.DataFrame
       Cycle-level flux data. Must contain:

       ``flux_date`` : datetime-like
           Timestamp; hour and month-year are extracted from this column.
       ``Source_Chamber`` : str
           Chamber identifier. Subplots 2 and 3 filter on
           ``"Chamber 1"`` and ``"Chamber 2"`` exactly.
       ``<variable>`` : float
           Flux column used for heatmap cell values.
   variable : str, optional
       Column in ``flux_df`` to aggregate. Default is
       ``"flux_absolute"``.
   title : str, optional
       Base title; each subplot appends its own suffix
       (e.g. ``"- Chamber 1"``). Default is
       ``"Flux Heatmap (Hour vs Month)"``.

   Returns
   -------
   matplotlib.figure.Figure or None
       The figure with three heatmap subplots, or ``None`` if
       ``flux_df`` is empty.

   Notes
   -----
   Subplots where the filtered data is empty show a ``"No Data"``
   label instead of a heatmap. Month-year periods on the x-axis
   are sorted chronologically by pandas ``Period`` ordering.

   Examples
   --------
   >>> from palmwtc.viz.timeseries import plot_flux_heatmap
   >>> fig = plot_flux_heatmap(cycles_df)  # doctest: +SKIP


.. py:function:: plot_flux_vs_tree_age(flux_df: pandas.DataFrame, variable: str = 'flux_absolute', birth_date_str: str = '2022-07-12') -> matplotlib.pyplot.Figure | None

   Plot flux against tree age in years, with a rolling-mean trend.

   Produces one subplot per chamber (stacked vertically, shared x-axis).
   Each subplot shows raw flux values as a semi-transparent scatter and
   a black rolling-mean line (window = 200 observations) as the trend.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Cycle-level flux data. Must contain:

       ``flux_date`` : datetime-like
           Timestamp of each measurement cycle; used to compute tree
           age relative to ``birth_date_str``.
       ``Source_Chamber`` : str
           Chamber identifier; one subplot is created per unique value.
       ``<variable>`` : float
           Flux column plotted on the y-axis.
   variable : str, optional
       Column in ``flux_df`` to plot. Default is ``"flux_absolute"``.
   birth_date_str : str, optional
       ISO-format planting date (``"YYYY-MM-DD"``) used as the zero
       point for tree age. Default is ``"2022-07-12"``.

   Returns
   -------
   matplotlib.figure.Figure or None
       The figure with one subplot per chamber, or ``None`` if
       ``flux_df`` is empty.

   Notes
   -----
   Tree age in years is computed as::

       (flux_date - birth_date).total_seconds() / (3600 * 24 * 365.25)

   so fractional years are preserved. The rolling mean uses
   ``window=200, center=True`` and will produce NaN near the edges of
   the series; those NaN values are silently dropped by matplotlib.

   Examples
   --------
   >>> from palmwtc.viz.timeseries import plot_flux_vs_tree_age
   >>> fig = plot_flux_vs_tree_age(cycles_df, birth_date_str="2022-07-12")  # doctest: +SKIP


.. py:function:: plot_tropical_seasonal_diurnal(flux_df: pandas.DataFrame, variable: str = 'flux_absolute', estimator: str = 'mean', title_suffix: str = '') -> matplotlib.pyplot.Figure | None

   Overlay diurnal flux pattern per tropical season on a single axis.

   Draws one line per season (Wet and Dry) and per chamber. The x-axis
   is hour of day (0-23), the y-axis is the flux value aggregated
   across all dates in that season-hour combination.

   Season assignment follows the standard SE-Asia rule:

   - **Dry Season**: May to September (months 5-9).
   - **Wet Season**: October to April (months 10-4).

   Useful for spotting shifts in CO2 uptake phase (morning vs afternoon
   activity) between seasons.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Cycle-level flux data. Must contain:

       ``flux_date`` : datetime-like
           Timestamp of each measurement cycle; month and hour are
           extracted from this column.
       ``Source_Chamber`` : str
           Chamber identifier used to differentiate line styles.
       ``<variable>`` : float
           Flux column plotted on the y-axis.
   variable : str, optional
       Column in ``flux_df`` to use as the y-axis value.
       Default is ``"flux_absolute"``.
   estimator : str, optional
       Aggregation function passed to ``seaborn.lineplot``
       (e.g. ``"mean"``, ``"median"``). Default is ``"mean"``.
   title_suffix : str, optional
       Extra text appended to the figure title, useful for adding
       a date range or site label. Default is ``""``.

   Returns
   -------
   matplotlib.figure.Figure or None
       The figure containing the diurnal plot, or ``None`` if
       ``flux_df`` is empty.

   Notes
   -----
   Shaded bands around each line represent one standard deviation
   (``errorbar="sd"``). Lines are coloured orange (Dry) and blue (Wet);
   line style differentiates chambers.

   Examples
   --------
   >>> from palmwtc.viz.timeseries import plot_tropical_seasonal_diurnal
   >>> fig = plot_tropical_seasonal_diurnal(cycles_df)  # doctest: +SKIP



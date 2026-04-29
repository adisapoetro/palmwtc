palmwtc.viz.qc_plots
====================

.. py:module:: palmwtc.viz.qc_plots

.. autoapi-nested-parse::

   QC flag visualisation for chamber sensor streams.

   Static matplotlib plots that turn the QC output of
   :mod:`palmwtc.qc.rules` and :mod:`palmwtc.qc.processor` into
   human-readable diagnostics:

   - :func:`visualize_qc_flags` -- multi-panel scatter coloured by flag value,
     with per-method breakdown panels and a summary row.
   - :func:`plot_qc_comparison` -- 2x2 horizontal-bar + stacked-bar comparison
     of flag percentages across multiple variables.
   - :func:`plot_qc_summary_heatmap` -- heatmap of flag percentages, one row per
     variable, three columns (Flag 0 / 1 / 2).
   - :func:`filter_plot` -- two-chamber overlay for one variable with hard/soft
     threshold lines drawn on the axes.
   - :func:`plot_soil_var` -- multi-depth soil sensor profile drawn on a single
     axis (depths 15, 48, 80, 200, 350 cm).
   - :func:`plot_high_quality_timeseries` -- line plot of Flag-0 data only.
   - :func:`plot_drift_and_hq_timeseries` -- two-panel figure: drift score (top)
     and Flag-0 timeseries (bottom), sharing the x-axis.
   - :func:`plot_baseline_drift` -- daily minimum/mean overlay with an expected
     baseline value and tolerance band.
   - :func:`plot_breakpoints_analysis` -- two-figure set: (1) timeseries with
     breakpoint lines and segment means; (2) breakpoint table.
   - :func:`visualize_breakpoints` -- three-panel overview: timeseries with
     kept/ignored breakpoint lines, segment means, and confidence-score bars.
   - :func:`visualize_missing_data` -- two-panel figure showing the raw
     timeseries (top) and gap-duration bars over time (bottom).
   - :func:`visualize_drift` -- deprecated stub; prints a notice and returns.

   Flag value semantics used throughout this module:

   - ``0`` = Good (green).
   - ``1`` = Suspect / soft warning (orange).
   - ``2`` = Bad / hard fail (red).

   All plots use :func:`matplotlib.pyplot` defaults. No custom style is applied
   inside this module; call :func:`palmwtc.viz.set_style` before plotting if you
   want the package-wide appearance.

   Notes
   -----
   Visualization functions are deterministic and do not require random seeds.



Functions
---------

.. autoapisummary::

   palmwtc.viz.qc_plots.visualize_qc_flags
   palmwtc.viz.qc_plots.plot_qc_comparison
   palmwtc.viz.qc_plots.plot_qc_summary_heatmap
   palmwtc.viz.qc_plots.filter_plot
   palmwtc.viz.qc_plots.plot_soil_var
   palmwtc.viz.qc_plots.plot_high_quality_timeseries
   palmwtc.viz.qc_plots.plot_drift_and_hq_timeseries
   palmwtc.viz.qc_plots.visualize_drift
   palmwtc.viz.qc_plots.plot_baseline_drift
   palmwtc.viz.qc_plots.plot_breakpoints_analysis
   palmwtc.viz.qc_plots.visualize_missing_data
   palmwtc.viz.qc_plots.visualize_breakpoints


Module Contents
---------------

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


.. py:function:: plot_high_quality_timeseries(df: pandas.DataFrame, var_name: str, qc_flag_col: str | None = None, title: str | None = None) -> None

   Line plot of Flag-0 (high-quality) data for one variable.

   Filters ``df`` to rows where the QC flag equals 0 and draws a single
   green line.  Calls :func:`matplotlib.pyplot.show` before returning.

   If the QC flag column is absent, all non-NaN data are plotted and a
   warning is printed.  If no Flag-0 data exist, a message is printed
   and the function returns without plotting.

   Parameters
   ----------
   df : pd.DataFrame
       QC-flagged DataFrame indexed by datetime.  Must contain:

       ``{var_name}`` : numeric
           Sensor values.
       ``{qc_flag_col}`` : int in {0, 1, 2}, optional
           QC flag column.  Falls back to all data if absent.
   var_name : str
       Name of the sensor variable column to plot.
   qc_flag_col : str, optional
       Name of the QC flag column.  Default: ``f"{var_name}_qc_flag"``.
   title : str, optional
       Axis title.  Default: ``f"High Quality Time Series: {var_name}"``.

   Returns
   -------
   None
       The figure is displayed via :func:`matplotlib.pyplot.show`.

   Notes
   -----
   Flag value 0 = Good (the only data shown in this plot).

   This function creates a new :func:`matplotlib.pyplot.figure` on each
   call; it does not return the figure object.  Use
   :func:`plot_drift_and_hq_timeseries` if you need a figure you can
   embed in a larger layout.

   Examples
   --------
   >>> from palmwtc.viz.qc_plots import plot_high_quality_timeseries
   >>> plot_high_quality_timeseries(df, "CO2_Avg")  # doctest: +SKIP

   See Also
   --------
   plot_drift_and_hq_timeseries : Two-panel version that also shows drift
       scores above the Flag-0 timeseries.


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


.. py:function:: visualize_drift(df: pandas.DataFrame, drift_result: object, var_name: str) -> None

   Deprecated -- drift visualisation stub.

   This function previously visualised Merlion-based drift detection
   results.  The Merlion dependency was removed; calling this function
   prints a notice and returns immediately.

   Parameters
   ----------
   df : pd.DataFrame
       Ignored.
   drift_result : object
       Ignored.
   var_name : str
       Ignored.

   Returns
   -------
   None

   .. deprecated::
       Use :func:`plot_drift_and_hq_timeseries` with the windowed-statistics
       drift result from :mod:`palmwtc.qc.drift` instead.


.. py:function:: plot_baseline_drift(baseline_df: pandas.DataFrame, column: str, expected: float) -> None

   Line plot of daily minimum and mean values to check sensor baseline drift.

   Draws three elements on a single axis:

   1. **Daily minimum** (blue solid line): ``f"{column}_daily_min"`` column.
   2. **Daily mean** (green dashed line): ``f"{column}_daily_mean"`` column.
   3. **Expected baseline** (red dotted horizontal line) at ``expected`` with
      a shaded tolerance band of +/-50 ppm around it.

   Calls :func:`matplotlib.pyplot.show` before returning.

   Parameters
   ----------
   baseline_df : pd.DataFrame
       DataFrame indexed by date.  Must contain:

       ``{column}_daily_min`` : float
           Daily minimum values of the sensor.
       ``{column}_daily_mean`` : float
           Daily mean values of the sensor.
   column : str
       Sensor column base name (e.g. ``"CO2_Avg"``).  Used for axis
       labels and the title.
   expected : float
       Expected baseline concentration in ppm (e.g. 400 for ambient CO2).
       The tolerance band spans ``expected - 50`` to ``expected + 50``.

   Returns
   -------
   None
       The figure is displayed via :func:`matplotlib.pyplot.show`.

   Notes
   -----
   The +/-50 ppm tolerance band is hard-coded and is intended for CO2
   sensors (LI-COR LI-850).  For other variables the band width may not
   be meaningful.

   If ``{column}_daily_min`` is not present in ``baseline_df``, the plot
   is created but remains empty (no error is raised).

   Examples
   --------
   >>> from palmwtc.viz.qc_plots import plot_baseline_drift
   >>> plot_baseline_drift(baseline_df, "CO2_Avg", expected=400.0)  # doctest: +SKIP

   See Also
   --------
   plot_drift_and_hq_timeseries : Raw-resolution drift score + Flag-0 data.


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



palmwtc.viz.interactive
=======================

.. py:module:: palmwtc.viz.interactive

.. autoapi-nested-parse::

   Interactive Plotly dashboards for chamber flux data.

   Dashboards are designed to run **inside Jupyter** (notebook or lab):
   they return ``plotly.graph_objects.Figure`` instances or render directly
   via ``IPython.display``. They will not render correctly when called from
   a plain Python script; redirect those workflows to the static matplotlib
   equivalents in :mod:`palmwtc.viz.timeseries` and
   :mod:`palmwtc.viz.diagnostics`.

   Two families of helpers live here:

   * ``plot_*_interactive`` — pure Plotly figure builders that return a
     ``plotly.graph_objects.Figure``. Plotly is a core dependency of
     ``palmwtc``, so these work in any install. Call ``fig.show()`` or
     display the return value in a notebook cell to render.
   * :func:`interactive_flux_dashboard` — a Jupyter dashboard combining
     ipywidgets controls (dropdowns, checkboxes) with a zoom-to-reveal
     detail view. Requires the ``palmwtc[interactive]`` extra
     (``ipywidgets`` + ``IPython``), which are imported inside the function
     body so this module remains importable in a core-only install.



Functions
---------

.. autoapisummary::

   palmwtc.viz.interactive._add_trendline
   palmwtc.viz.interactive.plot_flux_timeseries_tiers_interactive
   palmwtc.viz.interactive.plot_tropical_seasonal_diurnal_interactive
   palmwtc.viz.interactive.plot_flux_heatmap_interactive
   palmwtc.viz.interactive.plot_flux_vs_tree_age_interactive
   palmwtc.viz.interactive.plot_chamber_resizing_validation_interactive
   palmwtc.viz.interactive.plot_cumulative_flux_with_gaps_interactive
   palmwtc.viz.interactive.plot_concentration_slope_vs_tree_age_interactive
   palmwtc.viz.interactive.plot_flux_boxplot_vs_tree_age_interactive
   palmwtc.viz.interactive.plot_concentration_slope_boxplot_vs_tree_age_interactive
   palmwtc.viz.interactive.plot_flux_monthly_boxplot_interactive
   palmwtc.viz.interactive._natural_key
   palmwtc.viz.interactive._downsample_uniform
   palmwtc.viz.interactive._extract_relayout_payload
   palmwtc.viz.interactive._extract_xrange_from_relayout
   palmwtc.viz.interactive.interactive_flux_dashboard


Module Contents
---------------

.. py:function:: _add_trendline(fig, df, x_col, y_col, trend_window=200)

   Helper to add a rolling mean trendline to a figure.


.. py:function:: plot_flux_timeseries_tiers_interactive(flux_df: pandas.DataFrame, variable: str = 'flux_absolute', title: str = 'CO2 Flux Timeseries by QC Tier') -> plotly.graph_objects.Figure | None

   Flux timeseries split into three QC-tier panels per chamber.

   Produces a Plotly figure with 3 rows x N-chamber columns.  Each row
   shows one quality tier:

   * Tier 1 — all data (QC flags 0, 1, 2), coloured by flag value.
   * Tier 2 — high + medium quality only (flags 0 and 1), coloured by flag.
   * Tier 3 — high quality only (flag 0), displayed in green.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Flux results table. Must contain:

       ``Source_Chamber`` : str
           Chamber identifier used to split columns (e.g. ``"Chamber 1"``).
       ``flux_date`` : datetime-like
           Timestamp of each flux estimate. Plotted on the x-axis.
       ``qc_flag`` : int
           Quality flag (0 = high quality, 1 = medium, 2 = low).
       *variable* column : float
           Column named by the *variable* argument (default
           ``"flux_absolute"``). Plotted on the y-axis.
   variable : str
       Name of the column to plot on the y-axis.
       Default ``"flux_absolute"``.
   title : str
       Figure title. Default ``"CO2 Flux Timeseries by QC Tier"``.

   Returns
   -------
   plotly.graph_objects.Figure or None
       Multi-panel Plotly figure (3 rows x N chambers, 1200 px tall).
       Returns ``None`` if *flux_df* is empty.

   Notes
   -----
   Designed for Jupyter notebook / lab. In a notebook cell the figure
   renders inline when the cell output is a ``Figure`` object.  Outside
   Jupyter, call ``fig.show()`` or save with ``fig.write_html(path)``.

   The shared x-axis across rows allows aligning date ranges visually
   across all three tiers at the same time.

   Examples
   --------
   >>> from palmwtc.viz.interactive import plot_flux_timeseries_tiers_interactive
   >>> fig = plot_flux_timeseries_tiers_interactive(flux_df)  # doctest: +SKIP
   >>> fig.show()  # doctest: +SKIP

   See Also
   --------
   palmwtc.viz.diagnostics.plot_cycle_diagnostics : Static matplotlib
       equivalent for single-cycle inspection.
   palmwtc.viz.timeseries.plot_flux_timeseries : Static matplotlib
       timeseries for all chambers.


.. py:function:: plot_tropical_seasonal_diurnal_interactive(flux_df: pandas.DataFrame, variable: str = 'flux_absolute') -> plotly.graph_objects.Figure | None

   Mean diurnal flux cycle split by tropical wet and dry seasons.

   Groups hourly data into two tropical seasons (dry: May-September,
   wet: all other months) and plots mean +/- standard deviation lines
   for each chamber x season combination.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Flux results table. Must contain:

       ``Source_Chamber`` : str
           Chamber identifier used as a plot symbol series.
       ``flux_date`` : datetime-like
           Timestamp; the hour-of-day component drives the x-axis.
       *variable* column : float
           Column named by the *variable* argument (default
           ``"flux_absolute"``). Mean and std are computed per hour.
   variable : str
       Name of the flux column to aggregate. Default ``"flux_absolute"``.

   Returns
   -------
   plotly.graph_objects.Figure or None
       Line figure with error bars. Returns ``None`` if *flux_df* is empty.

   Notes
   -----
   Designed for Jupyter notebook / lab. Call ``fig.show()`` or save with
   ``fig.write_html(path)`` when running outside Jupyter.

   Season boundaries are fixed: dry season = months 5 to 9 (May to
   September), wet season = all remaining months. These reflect the
   typical Riau (Sumatra) bimodal rainfall pattern.

   Examples
   --------
   >>> from palmwtc.viz.interactive import plot_tropical_seasonal_diurnal_interactive
   >>> fig = plot_tropical_seasonal_diurnal_interactive(flux_df)  # doctest: +SKIP
   >>> fig.show()  # doctest: +SKIP

   See Also
   --------
   palmwtc.viz.timeseries.plot_diurnal_cycle : Static matplotlib
       equivalent.


.. py:function:: plot_flux_heatmap_interactive(flux_df: pandas.DataFrame, variable: str = 'flux_absolute', title: str = 'Flux Heatmap (Hour vs Month)') -> plotly.graph_objects.Figure | None

   Heatmap of mean flux by hour-of-day vs month-year for each chamber.

   Builds a three-panel stacked heatmap (overall, Chamber 1, Chamber 2).
   Each cell shows the mean value of *variable* for a given hour and
   calendar month. Colour scale is diverging (RdBu_r) centred at zero.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Flux results table. Must contain:

       ``Source_Chamber`` : str
           Chamber identifier. The function expects values ``"Chamber 1"``
           and ``"Chamber 2"`` for the per-chamber panels.
       ``flux_date`` : datetime-like
           Timestamp; hour-of-day and year-month are extracted from this.
       *variable* column : float
           Column named by the *variable* argument (default
           ``"flux_absolute"``). Mean is computed per hour x month cell.
   variable : str
       Name of the flux column to aggregate. Default ``"flux_absolute"``.
   title : str
       Figure title. Default ``"Flux Heatmap (Hour vs Month)"``.

   Returns
   -------
   plotly.graph_objects.Figure or None
       Stacked heatmap figure (3 rows x 1 col, 1200 px tall).
       Returns ``None`` if *flux_df* is empty.

   Notes
   -----
   Designed for Jupyter notebook / lab. Call ``fig.show()`` or save with
   ``fig.write_html(path)`` when running outside Jupyter.

   Examples
   --------
   >>> from palmwtc.viz.interactive import plot_flux_heatmap_interactive
   >>> fig = plot_flux_heatmap_interactive(flux_df)  # doctest: +SKIP
   >>> fig.show()  # doctest: +SKIP

   See Also
   --------
   palmwtc.viz.diagnostics.plot_r2_heatmap : Static matplotlib R2
       heatmap by chamber x month.


.. py:function:: plot_flux_vs_tree_age_interactive(flux_df: pandas.DataFrame, variable: str = 'flux_absolute', birth_date_str: str = '2022-07-12') -> plotly.graph_objects.Figure | None

   Scatter plot of flux versus tree age with a rolling-mean trendline.

   Computes tree age in years from *birth_date_str* and plots each flux
   measurement as a scatter point. A rolling-mean trendline (window = 200
   points) is overlaid per chamber. Uses ``go.Scattergl`` (WebGL) for
   fast rendering of large datasets.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Flux results table. Must contain:

       ``Source_Chamber`` : str
           Chamber identifier used to split subplot rows.
       ``flux_date`` : datetime-like
           Measurement timestamp. Tree age is computed relative to
           *birth_date_str*.
       *variable* column : float
           Column named by the *variable* argument (default
           ``"flux_absolute"``). Plotted on the y-axis.
   variable : str
       Name of the flux column to plot. Default ``"flux_absolute"``.
   birth_date_str : str
       ISO-format date string for the tree planting date used to compute
       age (years). Default ``"2022-07-12"``.

   Returns
   -------
   plotly.graph_objects.Figure or None
       Multi-panel scatter figure (N-chamber rows, 400 px per row).
       Returns ``None`` if *flux_df* is empty.

   Notes
   -----
   Designed for Jupyter notebook / lab. Call ``fig.show()`` or save with
   ``fig.write_html(path)`` when running outside Jupyter.

   The trendline is a centred rolling mean with window = 200.  It only
   appears when the chamber has at least 200 data points.

   Examples
   --------
   >>> from palmwtc.viz.interactive import plot_flux_vs_tree_age_interactive
   >>> fig = plot_flux_vs_tree_age_interactive(flux_df)  # doctest: +SKIP
   >>> fig.show()  # doctest: +SKIP


.. py:function:: plot_chamber_resizing_validation_interactive(flux_df: pandas.DataFrame, resize_date: str = '2025-07-01', variable: str = 'flux_absolute') -> plotly.graph_objects.Figure | None

   Flux scatter in a +/- 60-day window around a chamber resizing event.

   Plots raw flux measurements in the 60-day window before and after
   *resize_date* for each chamber, with a rolling-mean trendline and a
   vertical dashed red line marking the resize event.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Flux results table. Must contain:

       ``Source_Chamber`` : str
           Chamber identifier used to split subplot rows.
       ``flux_date`` : datetime-like
           Measurement timestamp. Only rows within 60 days of
           *resize_date* are shown.
       *variable* column : float
           Column named by the *variable* argument (default
           ``"flux_absolute"``). Plotted on the y-axis.
   resize_date : str
       ISO-format date string for the chamber resizing event.
       Default ``"2025-07-01"``.
   variable : str
       Name of the flux column to plot. Default ``"flux_absolute"``.

   Returns
   -------
   plotly.graph_objects.Figure or None
       Multi-panel scatter figure (N-chamber rows, 400 px per row).
       Returns ``None`` if *flux_df* is empty or if no data falls in
       the resizing window.

   Notes
   -----
   Designed for Jupyter notebook / lab. Call ``fig.show()`` or save with
   ``fig.write_html(path)`` when running outside Jupyter.

   The rolling-mean trendline uses a window of 50 points.  The vertical
   line is drawn at *resize_date* using ``fig.add_vline``.

   Examples
   --------
   >>> from palmwtc.viz.interactive import plot_chamber_resizing_validation_interactive
   >>> fig = plot_chamber_resizing_validation_interactive(flux_df)  # doctest: +SKIP
   >>> fig.show()  # doctest: +SKIP


.. py:function:: plot_cumulative_flux_with_gaps_interactive(flux_df: pandas.DataFrame, gap_filled_df: pandas.DataFrame | None = None, birth_date_str: str = '2024-04-01') -> plotly.graph_objects.Figure | None

   Cumulative CO2 flux over time since planting, using gap-filled data.

   Computes the running cumulative sum of the ``flux_filled`` column from
   *gap_filled_df* and plots it against months after planting (MAP) for
   each chamber.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Not used directly in the plot, but required as the positional first
       argument for API consistency with other helpers in this module.
   gap_filled_df : pd.DataFrame or None
       Gap-filled flux table. Must contain:

       ``Source_Chamber`` : str
           Chamber identifier; one line per chamber is drawn.
       ``flux_date`` : datetime-like, optional
           If present, used as the date column; otherwise the DataFrame
           index is used as dates.
       ``flux_filled`` : float
           Gap-filled flux values. Cumulative sum is computed and plotted.

       Returns ``None`` if *gap_filled_df* is ``None`` or empty.
   birth_date_str : str
       ISO-format date string for the planting date. Used to compute
       months after planting (MAP = days / 30.44). Default ``"2024-04-01"``.

   Returns
   -------
   plotly.graph_objects.Figure or None
       Line figure with one trace per chamber on a MAP x-axis.
       Returns ``None`` if *gap_filled_df* is ``None`` or empty.

   Notes
   -----
   Designed for Jupyter notebook / lab. Call ``fig.show()`` or save with
   ``fig.write_html(path)`` when running outside Jupyter.

   The hover mode is ``"x unified"`` so all chamber values appear when
   hovering over a shared x-position.

   Examples
   --------
   >>> from palmwtc.viz.interactive import plot_cumulative_flux_with_gaps_interactive
   >>> fig = plot_cumulative_flux_with_gaps_interactive(  # doctest: +SKIP
   ...     flux_df, gap_filled_df=gapfill_df
   ... )
   >>> fig.show()  # doctest: +SKIP


.. py:function:: plot_concentration_slope_vs_tree_age_interactive(flux_df: pandas.DataFrame, variable: str = 'flux_slope', birth_date_str: str = '2022-07-12') -> plotly.graph_objects.Figure | None

   Scatter plot of CO2 concentration slope versus tree age.

   Plots the raw CO2 linear-regression slope (ppm/s) for every cycle
   against tree age in years. A rolling-mean trendline (window = 200)
   is overlaid per chamber. Uses ``go.Scattergl`` (WebGL) for fast
   rendering.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Flux results table. Must contain:

       ``Source_Chamber`` : str
           Chamber identifier used to split subplot rows.
       ``flux_date`` : datetime-like
           Measurement timestamp. Tree age is computed relative to
           *birth_date_str*.
       *variable* column : float
           Column named by the *variable* argument (default
           ``"flux_slope"``). Expected to hold the raw ppm/s slope.
   variable : str
       Name of the slope column. Default ``"flux_slope"``.
   birth_date_str : str
       ISO-format date string for the tree planting date. Default
       ``"2022-07-12"``.

   Returns
   -------
   plotly.graph_objects.Figure or None
       Multi-panel scatter figure (N-chamber rows, 400 px per row).
       Returns ``None`` if *flux_df* is empty.

   Notes
   -----
   Designed for Jupyter notebook / lab. Call ``fig.show()`` or save with
   ``fig.write_html(path)`` when running outside Jupyter.

   Examples
   --------
   >>> from palmwtc.viz.interactive import plot_concentration_slope_vs_tree_age_interactive
   >>> fig = plot_concentration_slope_vs_tree_age_interactive(flux_df)  # doctest: +SKIP
   >>> fig.show()  # doctest: +SKIP

   See Also
   --------
   plot_flux_vs_tree_age_interactive : Same layout for flux values.


.. py:function:: plot_flux_boxplot_vs_tree_age_interactive(flux_df: pandas.DataFrame, variable: str = 'flux_absolute', birth_date_str: str = '2022-07-12', bin_size_days: int = 30) -> plotly.graph_objects.Figure | None

   Flux boxplots binned by tree-age intervals, one facet per chamber.

   Groups flux values into fixed-width age bins (default 30 days) and
   draws one boxplot per bin. Chambers are faceted as separate rows.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Flux results table. Must contain:

       ``Source_Chamber`` : str
           Chamber identifier used to facet rows.
       ``flux_date`` : datetime-like
           Measurement timestamp. Age bins are computed relative to
           *birth_date_str*.
       *variable* column : float
           Column named by the *variable* argument (default
           ``"flux_absolute"``). Distribution per bin is shown as
           a box.
   variable : str
       Name of the flux column. Default ``"flux_absolute"``.
   birth_date_str : str
       ISO-format date string for the tree planting date. Default
       ``"2022-07-12"``.
   bin_size_days : int
       Width of each age bin in days. Default ``30`` (roughly monthly).

   Returns
   -------
   plotly.graph_objects.Figure or None
       Faceted box figure (one row per chamber). Returns ``None`` if
       *flux_df* is empty.

   Notes
   -----
   Designed for Jupyter notebook / lab. Call ``fig.show()`` or save with
   ``fig.write_html(path)`` when running outside Jupyter.

   Each facet's y-axis is independent (``matches=None``) so chambers
   with very different flux magnitudes are both readable.

   Examples
   --------
   >>> from palmwtc.viz.interactive import plot_flux_boxplot_vs_tree_age_interactive
   >>> fig = plot_flux_boxplot_vs_tree_age_interactive(flux_df)  # doctest: +SKIP
   >>> fig.show()  # doctest: +SKIP

   See Also
   --------
   plot_concentration_slope_boxplot_vs_tree_age_interactive : Same layout
       for the raw ppm/s slope column.
   plot_flux_monthly_boxplot_interactive : Calendar-month boxplots.


.. py:function:: plot_concentration_slope_boxplot_vs_tree_age_interactive(flux_df: pandas.DataFrame, variable: str = 'flux_slope', birth_date_str: str = '2022-07-12', bin_size_days: int = 30) -> plotly.graph_objects.Figure | None

   CO2 slope boxplots binned by tree-age intervals, one facet per chamber.

   Same layout as :func:`plot_flux_boxplot_vs_tree_age_interactive` but
   uses the raw CO2 linear-regression slope (ppm/s) column instead of
   the converted flux. Groups values into fixed-width age bins (default
   30 days) with one box per bin and one facet row per chamber.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Flux results table. Must contain:

       ``Source_Chamber`` : str
           Chamber identifier used to facet rows.
       ``flux_date`` : datetime-like
           Measurement timestamp. Age bins are computed relative to
           *birth_date_str*.
       *variable* column : float
           Column named by the *variable* argument (default
           ``"flux_slope"``). Raw ppm/s regression slope.
   variable : str
       Name of the slope column. Default ``"flux_slope"``.
   birth_date_str : str
       ISO-format date string for the tree planting date. Default
       ``"2022-07-12"``.
   bin_size_days : int
       Width of each age bin in days. Default ``30``.

   Returns
   -------
   plotly.graph_objects.Figure or None
       Faceted box figure (one row per chamber). Returns ``None`` if
       *flux_df* is empty.

   Notes
   -----
   Designed for Jupyter notebook / lab. Call ``fig.show()`` or save with
   ``fig.write_html(path)`` when running outside Jupyter.

   Examples
   --------
   >>> from palmwtc.viz.interactive import plot_concentration_slope_boxplot_vs_tree_age_interactive
   >>> fig = plot_concentration_slope_boxplot_vs_tree_age_interactive(  # doctest: +SKIP
   ...     flux_df
   ... )
   >>> fig.show()  # doctest: +SKIP

   See Also
   --------
   plot_flux_boxplot_vs_tree_age_interactive : Same layout for flux values.


.. py:function:: plot_flux_monthly_boxplot_interactive(flux_df: pandas.DataFrame, variable: str = 'flux_absolute') -> plotly.graph_objects.Figure | None

   Flux distribution by calendar month-year, one facet per chamber.

   Groups flux values by calendar month (``YYYY-MM`` string) and draws
   one box per month. Chambers are faceted as separate rows. This is the
   calendar-time complement of the tree-age boxplot helpers.

   Parameters
   ----------
   flux_df : pd.DataFrame
       Flux results table. Must contain:

       ``Source_Chamber`` : str
           Chamber identifier used to facet rows.
       ``flux_date`` : datetime-like
           Measurement timestamp. Month-year string is extracted and
           used as the x-axis category.
       *variable* column : float
           Column named by the *variable* argument (default
           ``"flux_absolute"``). Distribution per month is shown as
           a box.
   variable : str
       Name of the flux column. Default ``"flux_absolute"``.

   Returns
   -------
   plotly.graph_objects.Figure or None
       Faceted box figure (one row per chamber, months on x-axis).
       Returns ``None`` if *flux_df* is empty.

   Notes
   -----
   Designed for Jupyter notebook / lab. Call ``fig.show()`` or save with
   ``fig.write_html(path)`` when running outside Jupyter.

   Each facet's y-axis is independent (``matches=None``) so chambers
   with very different flux magnitudes are both readable.

   Examples
   --------
   >>> from palmwtc.viz.interactive import plot_flux_monthly_boxplot_interactive
   >>> fig = plot_flux_monthly_boxplot_interactive(flux_df)  # doctest: +SKIP
   >>> fig.show()  # doctest: +SKIP

   See Also
   --------
   plot_flux_boxplot_vs_tree_age_interactive : Same layout binned by
       tree age instead of calendar month.


.. py:function:: _natural_key(s)

.. py:function:: _downsample_uniform(df, max_points)

   Uniform downsample to at most *max_points* (keeps order).


.. py:function:: _extract_relayout_payload(change)

   Robustly extract relayout payload in VS Code / Jupyter.


.. py:function:: _extract_xrange_from_relayout(rd)

   Return ``(x0, x1, autorange)`` if possible.


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



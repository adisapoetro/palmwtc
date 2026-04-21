"""Interactive Plotly + ipywidgets visualisation helpers.

Behaviour-preserving port of ``flux_chamber/src/flux_visualization_interactive.py``.

Two flavours of public helpers live here:

* ``plot_*_interactive`` — pure Plotly figure builders. Plotly is a core
  dependency of ``palmwtc``, so these work in any install.
* ``interactive_flux_dashboard`` — a Jupyter dashboard built on
  ``ipywidgets`` and ``IPython.display``. Both are only installed via the
  ``palmwtc[interactive]`` extra; they are imported *inside* the function body
  to keep this module importable in a core-only install.

No internal palmwtc imports are required: the upstream module is fully
self-contained on top of pandas / numpy / plotly / ipywidgets / IPython.
"""

import re
import time as _time

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots


def _add_trendline(fig, df, x_col, y_col, trend_window=200):
    """Helper to add a rolling mean trendline to a figure."""
    if df.empty or len(df) < trend_window:
        return

    # Sort for rolling calculation
    df_sorted = df.sort_values(x_col)
    rolling = df_sorted[y_col].rolling(window=trend_window, center=True).mean()

    fig.add_trace(
        go.Scatter(
            x=df_sorted[x_col],
            y=rolling,
            mode="lines",
            name="Trend",
            line=dict(color="black", width=2),
            opacity=0.8,
        )
    )


def plot_flux_timeseries_tiers_interactive(
    flux_df, variable="flux_absolute", title="CO2 Flux Timeseries by QC Tier"
):
    """
    Interactive flux timeseries with 3 filtered views (Tier 1, Tier 2, Tier 3).
    """
    if flux_df.empty:
        return None

    chambers = sorted(flux_df["Source_Chamber"].unique())

    # Tier definitions
    tiers = [
        ("Tier 1: All Data (Flags 0, 1, 2)", lambda df: df),
        ("Tier 2: High + Medium Quality (Flags 0, 1)", lambda df: df[df["qc_flag"] <= 1]),
        ("Tier 3: High Quality Only (Flag 0)", lambda df: df[df["qc_flag"] == 0]),
    ]

    fig = make_subplots(
        rows=3,
        cols=len(chambers),
        shared_xaxes=True,
        shared_yaxes=False,
        subplot_titles=[f"{c} - {t[0]}" for t in tiers for c in chambers],
        vertical_spacing=0.08,
    )

    for col_idx, chamber in enumerate(chambers):
        chamber_data = flux_df[flux_df["Source_Chamber"] == chamber]

        for row_idx, (tier_name, tier_func) in enumerate(tiers):  # noqa: B007 (preserved from original)
            tier_data = tier_func(chamber_data)

            if tier_data.empty:
                continue

            # For Tier 1 & 2, color by qc_flag
            if row_idx < 2:
                # Use a discrete color map for flags
                for flag in sorted(tier_data["qc_flag"].unique()):
                    flag_data = tier_data[tier_data["qc_flag"] == flag]
                    fig.add_trace(
                        go.Scatter(
                            x=flag_data["flux_date"],
                            y=flag_data[variable],
                            mode="markers",
                            marker=dict(size=4),
                            name=f"Flag {flag}",
                            legendgroup=f"Flag {flag}",
                            showlegend=(row_idx == 0 and col_idx == 0),  # Only show legend once
                        ),
                        row=row_idx + 1,
                        col=col_idx + 1,
                    )
            else:
                # Tier 3 (only flag 0) - Green
                fig.add_trace(
                    go.Scatter(
                        x=tier_data["flux_date"],
                        y=tier_data[variable],
                        mode="markers",
                        marker=dict(size=4, color="green"),
                        name="High Quality",
                        showlegend=False,
                    ),
                    row=row_idx + 1,
                    col=col_idx + 1,
                )

    fig.update_layout(height=1200, width=1000, title_text=title, showlegend=True)
    fig.update_yaxes(title_text="CO2 Flux (umol m-2 s-1)", col=1)
    return fig


def plot_tropical_seasonal_diurnal_interactive(flux_df, variable="flux_absolute"):
    """Interactive diurnal cycles separated by Tropical Seasons."""
    if flux_df.empty:
        return None

    df = flux_df.copy()
    df["Month"] = df["flux_date"].dt.month

    def get_season(month):
        return "Dry Season" if 5 <= month <= 9 else "Wet Season"

    df["Season"] = df["Month"].apply(get_season)
    df["Hour"] = df["flux_date"].dt.hour

    # Aggregation for line plot
    agg_df = (
        df.groupby(["Hour", "Season", "Source_Chamber"])[variable]
        .agg(["mean", "std"])
        .reset_index()
    )

    fig = px.line(
        agg_df,
        x="Hour",
        y="mean",
        color="Season",
        symbol="Source_Chamber",
        title="Diurnal Flux Cycle: Wet vs Dry Season",
        labels={"mean": "CO2 Flux (umol m-2 s-1)", "Hour": "Hour of Day"},
        error_y="std",
    )  # Adding error bars

    fig.update_layout(xaxis=dict(tickmode="linear", dtick=2))
    return fig


def plot_flux_heatmap_interactive(
    flux_df, variable="flux_absolute", title="Flux Heatmap (Hour vs Month)"
):
    """Interactive heatmaps (Overall, Chamber 1, Chamber 2)."""
    if flux_df.empty:
        return None

    df = flux_df.copy()
    df["Hour"] = df["flux_date"].dt.hour
    df["MonthYear"] = df["flux_date"].dt.to_period("M").astype(str)

    # helper for pivoting
    def get_pivot(data):
        if data.empty:
            return None
        return data.pivot_table(index="Hour", columns="MonthYear", values=variable, aggfunc="mean")

    fig = make_subplots(
        rows=3, cols=1, subplot_titles=["Overall", "Chamber 1", "Chamber 2"], vertical_spacing=0.1
    )

    # 1. Overall
    pivot_all = get_pivot(df)
    if pivot_all is not None:
        fig.add_trace(
            go.Heatmap(
                z=pivot_all.values,
                x=pivot_all.columns,
                y=pivot_all.index,
                colorscale="RdBu_r",
                zmid=0,
                colorbar=dict(len=0.3, y=0.85),
            ),
            row=1,
            col=1,
        )

    # 2. Chamber 1
    pivot_c1 = get_pivot(df[df["Source_Chamber"] == "Chamber 1"])
    if pivot_c1 is not None:
        fig.add_trace(
            go.Heatmap(
                z=pivot_c1.values,
                x=pivot_c1.columns,
                y=pivot_c1.index,
                colorscale="RdBu_r",
                zmid=0,
                colorbar=dict(len=0.3, y=0.5),
            ),
            row=2,
            col=1,
        )

    # 3. Chamber 2
    pivot_c2 = get_pivot(df[df["Source_Chamber"] == "Chamber 2"])
    if pivot_c2 is not None:
        fig.add_trace(
            go.Heatmap(
                z=pivot_c2.values,
                x=pivot_c2.columns,
                y=pivot_c2.index,
                colorscale="RdBu_r",
                zmid=0,
                colorbar=dict(len=0.3, y=0.15),
            ),
            row=3,
            col=1,
        )

    fig.update_layout(height=1200, title_text=title)
    fig.update_yaxes(title_text="Hour of Day")
    return fig


def plot_flux_vs_tree_age_interactive(
    flux_df, variable="flux_absolute", birth_date_str="2022-07-12"
):
    """Interactive Flux vs Tree Age."""
    if flux_df.empty:
        return None

    birth_date = pd.to_datetime(birth_date_str)
    df = flux_df.copy()
    df["Tree_Age_Years"] = (df["flux_date"] - birth_date).dt.total_seconds() / (3600 * 24 * 365.25)

    chambers = sorted(df["Source_Chamber"].unique())
    fig = make_subplots(
        rows=len(chambers), cols=1, subplot_titles=[f"CO2 Flux vs Tree Age: {c}" for c in chambers]
    )

    for i, chamber in enumerate(chambers):
        group = df[df["Source_Chamber"] == chamber]

        # Scatter
        fig.add_trace(
            go.Scattergl(
                x=group["Tree_Age_Years"],
                y=group[variable],
                mode="markers",
                name=chamber,
                marker=dict(size=4, opacity=0.3),
            ),
            row=i + 1,
            col=1,
        )

        # Trend
        _add_trendline(fig, group, "Tree_Age_Years", variable, trend_window=200)

    fig.update_layout(height=400 * len(chambers), title_text="CO2 Flux vs Tree Age")
    fig.update_xaxes(title_text="Tree Age (Years)")
    fig.update_yaxes(title_text="CO2 Flux (umol m-2 s-1)")
    return fig


def plot_chamber_resizing_validation_interactive(
    flux_df, resize_date="2025-07-01", variable="flux_absolute"
):
    """Interactive Chamber Resizing Validation."""
    if flux_df.empty:
        return None

    resize_dt = pd.to_datetime(resize_date)
    start_window = resize_dt - pd.Timedelta(days=60)
    end_window = resize_dt + pd.Timedelta(days=60)

    df_window = flux_df[
        (flux_df["flux_date"] >= start_window) & (flux_df["flux_date"] <= end_window)
    ].copy()
    if df_window.empty:
        return None

    chambers = sorted(df_window["Source_Chamber"].unique())
    fig = make_subplots(
        rows=len(chambers), cols=1, subplot_titles=[f"Resizing Validation: {c}" for c in chambers]
    )

    for i, chamber in enumerate(chambers):
        group = df_window[df_window["Source_Chamber"] == chamber]

        fig.add_trace(
            go.Scatter(
                x=group["flux_date"],
                y=group[variable],
                mode="markers",
                name=chamber,
                marker=dict(size=5, opacity=0.5),
            ),
            row=i + 1,
            col=1,
        )

        # Trend
        _add_trendline(fig, group, "flux_date", variable, trend_window=50)

        # Vertical line for resize
        fig.add_vline(
            x=resize_dt.timestamp() * 1000, line_dash="dash", line_color="red", row=i + 1, col=1
        )

    fig.update_layout(height=400 * len(chambers), title_text="Chamber Resizing Validation")
    return fig


def plot_cumulative_flux_with_gaps_interactive(
    flux_df, gap_filled_df=None, birth_date_str="2024-04-01"
):
    """Interactive Cumulative Flux."""
    if gap_filled_df is None or gap_filled_df.empty:
        return None

    birth_date = pd.to_datetime(birth_date_str)

    fig = go.Figure()

    for chamber, group in gap_filled_df.groupby("Source_Chamber"):
        # Use flux_date column if available, else index
        if "flux_date" in group.columns:
            group = group.sort_values("flux_date")
            dates = group["flux_date"]
        else:
            group = group.sort_index()
            dates = group.index

        # Calculate MAP
        # Ensure dates is datetime-like
        if not pd.api.types.is_datetime64_any_dtype(dates):
            dates = pd.to_datetime(dates)

        # Calculate days difference
        if hasattr(dates, "dt"):
            days_diff = (dates - birth_date).dt.days
        else:
            days_diff = (dates - birth_date).days

        group["MAP"] = days_diff / 30.44
        cumulative = group["flux_filled"].cumsum()

        fig.add_trace(
            go.Scatter(x=group["MAP"], y=cumulative, mode="lines", name=f"{chamber} (Gap Filled)")
        )

    fig.update_layout(
        title="Cumulative CO2 Flux (Gap-Filled)",
        xaxis_title="Months After Planting (MAP)",
        yaxis_title="Cumulative Flux (Arbitrary Units / Sum)",
        hovermode="x unified",
    )
    return fig


def plot_concentration_slope_vs_tree_age_interactive(
    flux_df, variable="flux_slope", birth_date_str="2022-07-12"
):
    """Interactive Concentration Slope vs Tree Age."""
    if flux_df.empty:
        return None

    birth_date = pd.to_datetime(birth_date_str)
    df = flux_df.copy()
    df["Tree_Age_Years"] = (df["flux_date"] - birth_date).dt.total_seconds() / (3600 * 24 * 365.25)

    chambers = sorted(df["Source_Chamber"].unique())
    fig = make_subplots(
        rows=len(chambers), cols=1, subplot_titles=[f"Slope vs Tree Age: {c}" for c in chambers]
    )

    for i, chamber in enumerate(chambers):
        group = df[df["Source_Chamber"] == chamber]

        fig.add_trace(
            go.Scattergl(
                x=group["Tree_Age_Years"],
                y=group[variable],
                mode="markers",
                name=chamber,
                marker=dict(size=4, opacity=0.3),
            ),
            row=i + 1,
            col=1,
        )

        _add_trendline(fig, group, "Tree_Age_Years", variable, trend_window=200)

    fig.update_layout(height=400 * len(chambers), title_text="Concentration Slope vs Tree Age")
    fig.update_yaxes(title_text="Slope (ppm/s)")
    fig.update_xaxes(title_text="Tree Age (Years)")
    return fig


def plot_flux_boxplot_vs_tree_age_interactive(
    flux_df, variable="flux_absolute", birth_date_str="2022-07-12", bin_size_days=30
):
    """Interactive Flux Boxplots (Monthly Bins)."""
    if flux_df.empty:
        return None

    birth_date = pd.to_datetime(birth_date_str)
    df = flux_df.copy()
    df["Age_Bin"] = ((df["flux_date"] - birth_date).dt.days // bin_size_days) * bin_size_days
    df["Age_Bin_Years"] = df["Age_Bin"] / 365.25

    fig = px.box(
        df,
        x="Age_Bin_Years",
        y=variable,
        facet_row="Source_Chamber",
        color="Source_Chamber",
        title="CO2 Flux Boxplots (Monthly Bins)",
        labels={"Age_Bin_Years": "Tree Age (Years)", variable: "CO2 Flux (umol m-2 s-1)"},
    )

    # Ensure facets share x axis but have independent y ranges if needed (usually sharey is good for comparison)
    fig.update_yaxes(matches=None)
    return fig


def plot_concentration_slope_boxplot_vs_tree_age_interactive(
    flux_df, variable="flux_slope", birth_date_str="2022-07-12", bin_size_days=30
):
    """Interactive Slope Boxplots."""
    if flux_df.empty:
        return None

    birth_date = pd.to_datetime(birth_date_str)
    df = flux_df.copy()
    df["Age_Bin"] = ((df["flux_date"] - birth_date).dt.days // bin_size_days) * bin_size_days
    df["Age_Bin_Years"] = df["Age_Bin"] / 365.25

    fig = px.box(
        df,
        x="Age_Bin_Years",
        y=variable,
        facet_row="Source_Chamber",
        color="Source_Chamber",
        title="Concentration Slope Boxplots (Monthly Bins)",
        labels={"Age_Bin_Years": "Tree Age (Years)", variable: "Slope (ppm/s)"},
    )

    fig.update_yaxes(matches=None)
    return fig


def plot_flux_monthly_boxplot_interactive(flux_df, variable="flux_absolute"):
    """Interactive Monthly Boxplots."""
    if flux_df.empty:
        return None

    df = flux_df.copy().sort_values("flux_date")
    df["MonthYear"] = df["flux_date"].dt.to_period("M").astype(str)

    fig = px.box(
        df,
        x="MonthYear",
        y=variable,
        facet_row="Source_Chamber",
        color="Source_Chamber",
        title="Monthly CO2 Flux Distribution",
        labels={variable: "CO2 Flux (umol m-2 s-1)"},
    )

    # Improve x-axis tick readability
    # fig.update_xaxes(tickangle=45)
    return fig


# ---------------------------------------------------------------------------
# Interactive Flux Dashboard (Overview + Detail zoom-to-reveal)
# ---------------------------------------------------------------------------


def _natural_key(s):
    s = str(s)
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _downsample_uniform(df, max_points):
    """Uniform downsample to at most *max_points* (keeps order)."""
    if df is None or df.empty:
        return df
    n = len(df)
    if n <= max_points:
        return df
    step = int(np.ceil(n / max_points))
    return df.iloc[::step]


def _extract_relayout_payload(change):
    """Robustly extract relayout payload in VS Code / Jupyter."""
    if not isinstance(change, dict):
        return {}
    new = change.get("new", {})
    if not isinstance(new, dict):
        return {}
    rd = new.get("_js2py_relayout", {})
    if isinstance(rd, dict):  # noqa: SIM108 (preserved from original)
        rd = rd.get("relayout_data", {})
    else:
        rd = {}
    if isinstance(rd, dict) and rd:
        return rd
    rd2 = new.get("_js2py_layoutDelta", {})
    return rd2 if isinstance(rd2, dict) else {}


def _extract_xrange_from_relayout(rd):
    """Return ``(x0, x1, autorange)`` if possible."""
    if rd.get("xaxis.autorange", False) or rd.get("xaxis2.autorange", False):
        return (None, None, True)
    for axis in ("xaxis", "xaxis2"):
        k0, k1 = f"{axis}.range[0]", f"{axis}.range[1]"
        if k0 in rd and k1 in rd:
            x0 = pd.to_datetime(rd[k0], errors="coerce")
            x1 = pd.to_datetime(rd[k1], errors="coerce")
            if pd.isna(x0) or pd.isna(x1):
                return (None, None, False)
            return (x0, x1, False)
        kr = f"{axis}.range"
        if kr in rd and isinstance(rd[kr], (list, tuple)) and len(rd[kr]) == 2:
            x0 = pd.to_datetime(rd[kr][0], errors="coerce")
            x1 = pd.to_datetime(rd[kr][1], errors="coerce")
            if pd.isna(x0) or pd.isna(x1):
                return (None, None, False)
            return (x0, x1, False)
    return (None, None, False)


def interactive_flux_dashboard(
    flux_df,
    chamber_raw,
    stride=15,
    renderer="plotly_mimetype",
    replace_previous=True,
    debug=True,
    enable_detail=True,
    detail_max_points_overview=80_000,
    detail_max_points_zoom=400_000,
    detail_debounce_s=0.25,
):
    """
    Interactive multi-chamber flux dashboard with zoom-to-reveal detail view.

    Parameters
    ----------
    flux_df : pd.DataFrame
        Flux results with flux_date, flux_absolute, qc_flag, Source_Chamber, cycle_id.
    chamber_raw : dict
        ``{chamber_name: raw_data_df}`` for detail view.
    stride : int
        Downsample factor for overview (permanently thins raw data).
    renderer : str
        Plotly renderer.
    enable_detail : bool
        Enable detail view with zoom-based point density.
    """
    import ipywidgets as widgets
    from IPython.display import clear_output, display

    if renderer:
        pio.renderers.default = renderer

    FLUX_HOVER_TEMPLATE = (
        "cycle_id=%{customdata[0]}<br>date=%{x|%Y-%m-%d %H:%M:%S}<br>flux=%{y:.6g}<extra></extra>"
    )

    # Close previous widgets
    if replace_previous and hasattr(interactive_flux_dashboard, "_widgets"):
        try:
            for w in interactive_flux_dashboard._widgets:
                w.close()
        except Exception:
            pass
        clear_output(wait=True)

    # Identify chambers
    chambers_raw = set(chamber_raw.keys()) if isinstance(chamber_raw, dict) else set()
    chambers_flux = set()
    has_flux = hasattr(flux_df, "columns") and ("Source_Chamber" in flux_df.columns)
    if has_flux:
        try:  # noqa: SIM105 (preserved from original)
            chambers_flux = set(flux_df["Source_Chamber"].dropna().unique())
        except Exception:
            pass
    all_chambers = sorted(list(chambers_raw | chambers_flux), key=_natural_key)

    if debug:
        print(f"DEBUG: plotly renderer = {pio.renderers.default}")
        print(f"DEBUG: Found {len(all_chambers)} Chambers: {all_chambers}")

    if not all_chambers:
        print("No chamber data found to plot.")
        return

    # Cache datetime conversion
    if not getattr(interactive_flux_dashboard, "_raw_dt_cached", False):
        if isinstance(chamber_raw, dict):
            for k, df in chamber_raw.items():
                try:
                    if hasattr(df, "columns") and "TIMESTAMP" in df.columns:  # noqa: SIM102 (preserved from original)
                        if not np.issubdtype(df["TIMESTAMP"].dtype, np.datetime64):
                            chamber_raw[k] = df.copy()
                            chamber_raw[k]["TIMESTAMP"] = pd.to_datetime(
                                chamber_raw[k]["TIMESTAMP"], errors="coerce"
                            )
                except Exception:
                    pass
        interactive_flux_dashboard._raw_dt_cached = True

    if has_flux and "flux_date" in flux_df.columns:  # noqa: SIM102 (preserved from original)
        if not getattr(interactive_flux_dashboard, "_flux_dt_cached", False):
            try:
                if not np.issubdtype(flux_df["flux_date"].dtype, np.datetime64):
                    flux_df["flux_date"] = pd.to_datetime(flux_df["flux_date"], errors="coerce")
            except Exception:
                pass
            interactive_flux_dashboard._flux_dt_cached = True

    # Pre-split flux by chamber
    flux_by_chamber = {}
    has_flux_date = has_flux and "flux_date" in flux_df.columns
    has_flux_val = has_flux and "flux_absolute" in flux_df.columns
    has_flux_qc = has_flux and "qc_flag" in flux_df.columns
    if has_flux and has_flux_date and has_flux_val:
        try:
            for ch, sub in flux_df.groupby("Source_Chamber", sort=False):
                flux_by_chamber[ch] = sub
        except Exception:
            pass

    # Controls
    style = {"description_width": "initial"}
    raw_filter_dropdown = widgets.Dropdown(
        options=[("All Flags", "All"), ("Flag 0 Only", "0"), ("Flag 0 + 1", "0+1")],
        value="All",
        description="Measured CO2 QC:",
        style=style,
    )
    flux_filter_dropdown = widgets.Dropdown(
        options=[("All Flags", "All"), ("Flag 0 Only", "0"), ("Flag 0 + 1", "0+1")],
        value="All",
        description="Flux Data QC:",
        style=style,
    )

    if enable_detail:
        detail_chamber_dropdown = widgets.Dropdown(
            options=[(c, c) for c in all_chambers],
            value=all_chambers[0],
            description="Detail Chamber:",
            style=style,
        )
        detail_toggle = widgets.Checkbox(
            value=True, description="Show detail (zoom reveals more points)"
        )
    else:
        detail_chamber_dropdown = detail_toggle = None

    ui_left = widgets.HBox([raw_filter_dropdown, flux_filter_dropdown])
    if enable_detail:
        ui_right = widgets.HBox([detail_chamber_dropdown, detail_toggle])
        ui = widgets.VBox([ui_left, ui_right])
    else:
        ui = ui_left

    output_overview = widgets.Output()
    output_detail = widgets.Output()

    def filter_data(df, col, val):
        if df is None or not hasattr(df, "columns") or col not in df.columns:
            return df
        if val == "0":
            return df[df[col] == 0]
        elif val == "0+1":
            return df[df[col].isin([0, 1])]
        return df

    # OVERVIEW
    def render_overview():
        raw_val = raw_filter_dropdown.value
        flux_val = flux_filter_dropdown.value
        with output_overview:
            output_overview.clear_output(wait=True)
            n_chambers = len(all_chambers)
            total_rows = n_chambers * 2
            titles = []
            for c in all_chambers:
                titles.append(f"{c}: Measured CO2 (overview)")
                titles.append(f"{c}: Flux")
            fig = make_subplots(
                rows=total_rows,
                cols=1,
                shared_xaxes=True,
                vertical_spacing=0.03 / max(1, n_chambers * 0.5),
                subplot_titles=tuple(titles),
            )
            colors = [
                ("blue", "darkblue"),
                ("orange", "darkorange"),
                ("green", "darkgreen"),
                ("red", "darkred"),
                ("purple", "indigo"),
                ("brown", "saddlebrown"),
            ]
            for i, chamber in enumerate(all_chambers):
                row_raw = i * 2 + 1
                row_flux = i * 2 + 2
                c_raw_color, c_flux_color = colors[i % len(colors)]
                if isinstance(chamber_raw, dict) and chamber in chamber_raw:
                    c_raw = chamber_raw[chamber]
                    c_filt = filter_data(c_raw, "Flag", raw_val)
                    if c_filt is not None and not c_filt.empty:
                        c_filt = c_filt.iloc[:: max(1, int(stride))]
                        if "TIMESTAMP" in c_filt.columns and "CO2" in c_filt.columns:
                            fig.add_trace(
                                go.Scattergl(
                                    x=c_filt["TIMESTAMP"],
                                    y=c_filt["CO2"],
                                    mode="markers",
                                    marker=dict(size=2, color=c_raw_color),
                                    name=f"{chamber} Measured",
                                    showlegend=(i == 0),
                                ),
                                row=row_raw,
                                col=1,
                            )
                if chamber in flux_by_chamber and has_flux_qc:
                    c_flux = flux_by_chamber[chamber]
                    c_flux_filt = filter_data(c_flux, "qc_flag", flux_val)
                    if c_flux_filt is not None and not c_flux_filt.empty:
                        customdata = (
                            c_flux_filt[["cycle_id"]].to_numpy()
                            if "cycle_id" in c_flux_filt.columns
                            else np.empty((len(c_flux_filt), 1), dtype=object)
                        )
                        fig.add_trace(
                            go.Scatter(
                                x=c_flux_filt["flux_date"],
                                y=c_flux_filt["flux_absolute"],
                                mode="markers",
                                marker=dict(size=6, color=c_flux_color),
                                name=f"{chamber} Flux",
                                showlegend=(i == 0),
                                customdata=customdata,
                                hovertemplate=FLUX_HOVER_TEMPLATE,
                            ),
                            row=row_flux,
                            col=1,
                        )
            fig.update_layout(
                height=500 * n_chambers,
                title_text=(
                    f"Integrated Flux QC (Overview) — {n_chambers} Chambers"
                    f"  |  stride={stride} (measured CO2 is thinned)"
                ),
                margin=dict(t=50, b=20, l=40, r=20),
            )
            fig.show(renderer=renderer)

    # DETAIL
    def render_detail():
        if not enable_detail or not detail_toggle.value:
            with output_detail:
                output_detail.clear_output(wait=True)
            return

        raw_val = raw_filter_dropdown.value
        flux_val = flux_filter_dropdown.value
        chamber = detail_chamber_dropdown.value

        raw_full = None
        if isinstance(chamber_raw, dict) and chamber in chamber_raw:
            raw_full = filter_data(chamber_raw[chamber], "Flag", raw_val)
            if raw_full is not None and not raw_full.empty:
                raw_full = raw_full.dropna(subset=["TIMESTAMP", "CO2"]).sort_values("TIMESTAMP")

        flux_full = None
        if chamber in flux_by_chamber and has_flux_qc:
            flux_full = filter_data(flux_by_chamber[chamber], "qc_flag", flux_val)
            if flux_full is not None and not flux_full.empty:
                flux_full = flux_full.dropna(subset=["flux_date", "flux_absolute"]).sort_values(
                    "flux_date"
                )

        with output_detail:
            output_detail.clear_output(wait=True)
            base = make_subplots(
                rows=2,
                cols=1,
                shared_xaxes=True,
                vertical_spacing=0.08,
                subplot_titles=(f"{chamber}: Measured CO2 (detail)", f"{chamber}: Flux (detail)"),
            )
            fig = go.FigureWidget(base)

            if raw_full is not None and not raw_full.empty:
                raw0 = _downsample_uniform(raw_full, detail_max_points_overview)
                fig.add_trace(
                    go.Scattergl(
                        x=raw0["TIMESTAMP"],
                        y=raw0["CO2"],
                        mode="markers",
                        marker=dict(size=2),
                        name="Measured",
                    ),
                    row=1,
                    col=1,
                )
            else:
                fig.add_trace(
                    go.Scattergl(x=[], y=[], mode="markers", name="Measured"), row=1, col=1
                )

            if flux_full is not None and not flux_full.empty:
                flux0 = _downsample_uniform(flux_full, min(detail_max_points_overview, 200_000))
                flux_custom0 = (
                    flux0[["cycle_id"]].to_numpy()
                    if "cycle_id" in flux0.columns
                    else np.empty((len(flux0), 1), dtype=object)
                )
                fig.add_trace(
                    go.Scatter(
                        x=flux0["flux_date"],
                        y=flux0["flux_absolute"],
                        mode="markers",
                        marker=dict(size=6),
                        name="Flux",
                        customdata=flux_custom0,
                        hovertemplate=FLUX_HOVER_TEMPLATE,
                    ),
                    row=2,
                    col=1,
                )
            else:
                fig.add_trace(go.Scatter(x=[], y=[], mode="markers", name="Flux"), row=2, col=1)

            fig.update_layout(
                height=650,
                title=f"Detail view (zoom/pan loads more points) — {chamber}",
                margin=dict(t=50, b=20, l=40, r=20),
            )
            fig.update_xaxes(type="date")

            state = {"last_t": 0.0, "last_key": None}

            def _on_fig_change(change):
                rd = _extract_relayout_payload(change)
                if not rd:
                    return
                x0, x1, autorange = _extract_xrange_from_relayout(rd)
                if not autorange and (x0 is None or x1 is None or pd.isna(x0) or pd.isna(x1)):
                    return
                if not autorange and x1 < x0:
                    x0, x1 = x1, x0

                now = _time.time()
                key = ("auto",) if autorange else ("range", str(x0), str(x1))
                if key == state["last_key"] or (now - state["last_t"]) < detail_debounce_s:
                    return
                state["last_t"] = now
                state["last_key"] = key

                if autorange:
                    raw_win = (
                        _downsample_uniform(raw_full, detail_max_points_overview)
                        if raw_full is not None and not raw_full.empty
                        else raw_full
                    )
                    flux_win = (
                        _downsample_uniform(flux_full, min(detail_max_points_overview, 200_000))
                        if flux_full is not None and not flux_full.empty
                        else flux_full
                    )
                else:
                    raw_win = None
                    if raw_full is not None and not raw_full.empty:
                        raw_win = raw_full[
                            (raw_full["TIMESTAMP"] >= x0) & (raw_full["TIMESTAMP"] <= x1)
                        ]
                        raw_win = _downsample_uniform(raw_win, detail_max_points_zoom)
                    flux_win = None
                    if flux_full is not None and not flux_full.empty:
                        flux_win = flux_full[
                            (flux_full["flux_date"] >= x0) & (flux_full["flux_date"] <= x1)
                        ]
                        flux_win = _downsample_uniform(
                            flux_win, min(detail_max_points_zoom, 300_000)
                        )

                with fig.batch_update():
                    if raw_win is not None and not raw_win.empty:
                        fig.data[0].x = raw_win["TIMESTAMP"]
                        fig.data[0].y = raw_win["CO2"]
                    else:
                        fig.data[0].x = []
                        fig.data[0].y = []
                    if flux_win is not None and not flux_win.empty:
                        fig.data[1].x = flux_win["flux_date"]
                        fig.data[1].y = flux_win["flux_absolute"]
                        fig.data[1].customdata = (
                            flux_win[["cycle_id"]].to_numpy()
                            if "cycle_id" in flux_win.columns
                            else np.empty((len(flux_win), 1), dtype=object)
                        )
                    else:
                        fig.data[1].x = []
                        fig.data[1].y = []
                        fig.data[1].customdata = np.empty((0, 1), dtype=object)

            fig.observe(_on_fig_change)
            display(fig)

    def update_all(_change=None):
        render_overview()
        if enable_detail:
            render_detail()

    raw_filter_dropdown.observe(update_all, names="value")
    flux_filter_dropdown.observe(update_all, names="value")
    if enable_detail:
        detail_chamber_dropdown.observe(update_all, names="value")
        detail_toggle.observe(update_all, names="value")

    interactive_flux_dashboard._widgets = (ui, output_overview, output_detail)
    display(ui, output_overview, output_detail)
    update_all()

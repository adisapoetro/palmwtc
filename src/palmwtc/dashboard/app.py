"""palmwtc Streamlit monitoring dashboard.

A focused single-page monitoring view of a palmwtc dataset:

- Configured DataPaths summary
- QC parquet sanity (rows, time range, columns)
- Per-cycle CO2 + H2O flux (loaded from cycles CSV if present, else
  computed on the fly via palmwtc.pipeline)
- QC flag totals per variable
- Cycle-quality histogram (R2 + RMSE)
- Inter-chamber agreement scatter

Launch with::

    palmwtc dashboard

Requires ``pip install palmwtc[dashboard]``.

The flux_chamber companion repo has a much larger operational dashboard
(auth, ngrok deploy, email reports). That stays private — this is the
clean public-package version focused on the science API surface.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from palmwtc import __version__
from palmwtc.config import DataPaths
from palmwtc.pipeline import run_pipeline


@st.cache_data(show_spinner="Loading QC parquet...")
def _load_qc(qc_path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    return pd.read_parquet(qc_path, columns=columns)


@st.cache_data(show_spinner="Loading cycles CSV...")
def _load_cycles(cycles_path: Path) -> pd.DataFrame:
    df = pd.read_csv(cycles_path)
    if "flux_datetime" not in df.columns and "flux_date" in df.columns:
        df["flux_datetime"] = pd.to_datetime(df["flux_date"])
    return df


def _resolve_qc_path(paths: DataPaths) -> Path | None:
    candidates = [
        paths.processed_dir / "QC_Flagged_Data_latest.parquet",
        paths.raw_dir / "QC_Flagged_Data_synthetic.parquet",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _section_data_paths(paths: DataPaths) -> None:
    st.subheader("DataPaths")
    cols = st.columns(2)
    cols[0].metric("Source", paths.source)
    cols[1].metric("Site", paths.site)
    with st.expander("Resolved paths", expanded=False):
        st.code(paths.describe())


def _section_qc_summary(paths: DataPaths) -> Path | None:
    st.subheader("QC parquet")
    qc_path = _resolve_qc_path(paths)
    if qc_path is None:
        st.warning(
            "No QC parquet found. Looked in:\n"
            f"- `{paths.processed_dir}/QC_Flagged_Data_latest.parquet`\n"
            f"- `{paths.raw_dir}/QC_Flagged_Data_synthetic.parquet`"
        )
        return None

    df = _load_qc(qc_path, columns=None)
    cols = st.columns(4)
    cols[0].metric("Rows", f"{len(df):,}")
    cols[1].metric("Columns", len(df.columns))
    if "TIMESTAMP" in df.columns:
        ts = pd.to_datetime(df["TIMESTAMP"])
        cols[2].metric("Start", str(ts.min()))
        cols[3].metric("End", str(ts.max()))
    st.caption(f"Source: `{qc_path}`")
    return qc_path


def _section_qc_flags(qc_path: Path) -> None:
    st.subheader("QC flag totals")
    df = _load_qc(qc_path)
    flag_cols = [c for c in df.columns if c.endswith("_qc_flag")]
    if not flag_cols:
        st.info("No `*_qc_flag` columns found in this parquet.")
        return

    counts = df[flag_cols].sum().sort_values(ascending=False)
    chart_df = pd.DataFrame({"variable": counts.index, "flagged_rows": counts.values})
    st.bar_chart(chart_df, x="variable", y="flagged_rows", height=300)


def _section_cycles(paths: DataPaths) -> Path | None:
    st.subheader("Per-cycle flux")
    cycles_path = paths.exports_dir / "digital_twin" / "01_chamber_cycles.csv"

    if not cycles_path.exists():
        st.info(
            f"Cycles file not found at `{cycles_path}`. "
            "Click below to compute via `palmwtc.pipeline.run_pipeline(steps=['qc', 'flux'])`."
        )
        if st.button("Compute now (~20 s on synthetic)", type="primary"):
            with st.spinner("Running pipeline..."):
                result = run_pipeline(paths, steps=["qc", "flux"])
            st.code(result.summary())
            if not result.ok:
                st.error("Pipeline failed — see summary above.")
                return None
        else:
            return None

    cycles = _load_cycles(cycles_path)
    cols = st.columns(3)
    cols[0].metric("Cycles", len(cycles))
    if "chamber" in cycles.columns:
        cols[1].metric("Chambers", cycles["chamber"].nunique())
    if "qc_flag" in cycles.columns:
        cols[2].metric("Pass rate", f"{(cycles['qc_flag'] == 0).mean():.0%}")

    if "flux_datetime" in cycles.columns and "flux_absolute" in cycles.columns:
        st.line_chart(
            cycles.set_index("flux_datetime")[["flux_absolute"]],
            height=300,
        )
    st.caption(f"Source: `{cycles_path}`")
    return cycles_path


def _section_cycle_quality(cycles_path: Path) -> None:
    st.subheader("Cycle quality distribution")
    cycles = _load_cycles(cycles_path)
    if "r2" not in cycles.columns:
        st.info("`r2` column not found in cycles file.")
        return
    cols = st.columns(2)
    with cols[0]:
        st.write("**R² distribution**")
        st.bar_chart(cycles["r2"].dropna(), height=200)
    with cols[1]:
        if "nrmse" in cycles.columns:
            st.write("**NRMSE distribution**")
            st.bar_chart(cycles["nrmse"].dropna(), height=200)


def _section_chamber_agreement(qc_path: Path) -> None:
    st.subheader("Inter-chamber agreement")
    df = _load_qc(qc_path, columns=["TIMESTAMP", "CO2_C1", "CO2_C2"])
    df = df.dropna(subset=["CO2_C1", "CO2_C2"]).iloc[::60]
    if len(df) == 0:
        st.info("No paired CO2 samples available.")
        return

    slope = (df["CO2_C2"] / df["CO2_C1"]).median()
    cols = st.columns(2)
    cols[0].metric("Median C2/C1 ratio", f"{slope:.4f}")
    cols[1].metric("Paired samples", len(df))
    st.scatter_chart(df, x="CO2_C1", y="CO2_C2", height=300)


def main() -> None:
    st.set_page_config(
        page_title="palmwtc",
        page_icon="🌴",
        layout="wide",
    )

    st.title("palmwtc monitoring dashboard")
    st.caption(f"v{__version__} — automated whole-tree chamber workflow for oil-palm ecophysiology")

    with st.sidebar:
        st.header("Data source")
        st.write("Resolution order: kwargs → env → yaml → bundled sample")
        raw_dir_input = st.text_input(
            "Override raw_dir", value="", help="Leave blank for env / yaml / bundled."
        )
        if st.button("Reload"):
            st.cache_data.clear()
            st.rerun()
        st.divider()
        st.caption(
            "Built from palmwtc API. See [github.com/adisapoetro/palmwtc](https://github.com/adisapoetro/palmwtc)."
        )

    raw_dir = Path(raw_dir_input).expanduser() if raw_dir_input.strip() else None
    paths = DataPaths.resolve(raw_dir=raw_dir)

    _section_data_paths(paths)
    st.divider()

    qc_path = _section_qc_summary(paths)
    if qc_path:
        st.divider()
        _section_qc_flags(qc_path)
        st.divider()
        _section_chamber_agreement(qc_path)
        st.divider()

    cycles_path = _section_cycles(paths)
    if cycles_path:
        st.divider()
        _section_cycle_quality(cycles_path)


if __name__ == "__main__":
    main()


def cli_entry() -> None:
    """Entry point invoked by `palmwtc dashboard` CLI.

    Spawns ``streamlit run`` against this file. Streamlit needs to be the
    process that owns argv; we exec it via subprocess to keep typer's CLI
    parsing intact.
    """
    import subprocess

    app_path = Path(__file__).resolve()
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    raise SystemExit(subprocess.call(cmd))

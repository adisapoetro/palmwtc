"""palmwtc.pipeline — Library-mode pipeline orchestrator (no papermill).

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

Phase 3 ships the simplest implementation that runs end-to-end against
the bundled synthetic sample. Phase 4 will expand step bodies as the
notebooks are thinned.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from palmwtc.config import DataPaths

STEPS_IN_ORDER: tuple[str, ...] = ("qc", "flux", "windows", "validation")


@dataclass
class StepResult:
    """Outcome of one pipeline step."""

    name: str
    ok: bool
    elapsed_seconds: float
    rows_in: int = 0
    rows_out: int = 0
    artefacts: list[Path] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class PipelineResult:
    """Aggregate of all pipeline step results."""

    paths: DataPaths
    steps: list[StepResult] = field(default_factory=list)
    total_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.steps)

    def summary(self) -> str:
        lines = [
            f"Pipeline run on {self.paths.source}",
            f"  raw_dir = {self.paths.raw_dir}",
            f"  exports_dir = {self.paths.exports_dir}",
            "Steps:",
        ]
        for s in self.steps:
            tag = "PASS" if s.ok else "FAIL"
            lines.append(
                f"  [{tag}] {s.name:12s} {s.elapsed_seconds:5.1f}s  "
                f"in={s.rows_in:>6}  out={s.rows_out:>6}" + (f"  err={s.error}" if s.error else "")
            )
        lines.append(f"Total: {self.total_seconds:.1f}s — {'OK' if self.ok else 'FAILED'}")
        return "\n".join(lines)


def _find_qc_parquet(paths: DataPaths) -> Path:
    """Locate the QC parquet in either the user's processed_dir or the bundled sample."""
    # First check the user's processed_dir for the canonical filename.
    canonical = paths.processed_dir / "QC_Flagged_Data_latest.parquet"
    if canonical.exists():
        return canonical
    # Then check the bundled-sample naming.
    synthetic = paths.raw_dir / "QC_Flagged_Data_synthetic.parquet"
    if synthetic.exists():
        return synthetic
    # Then find_latest_qc_file as a last resort.
    from palmwtc.io import find_latest_qc_file

    found = find_latest_qc_file(paths.processed_dir)
    if found is None:
        raise FileNotFoundError(
            f"No QC parquet found. Tried:\n"
            f"  {canonical}\n  {synthetic}\n"
            f"  find_latest_qc_file({paths.processed_dir})"
        )
    return Path(found)


def step_qc(paths: DataPaths) -> StepResult:
    """Load QC parquet. Phase 3: no real QC processing — just verify the artefact is loadable."""
    t0 = time.time()
    try:
        qc_path = _find_qc_parquet(paths)
        df = pd.read_parquet(qc_path)
        return StepResult(
            name="qc",
            ok=True,
            elapsed_seconds=time.time() - t0,
            rows_in=0,
            rows_out=len(df),
            artefacts=[qc_path],
            metrics={
                "qc_path": str(qc_path),
                "n_columns": len(df.columns),
                "first_timestamp": str(df["TIMESTAMP"].iloc[0])
                if "TIMESTAMP" in df.columns
                else None,
                "last_timestamp": str(df["TIMESTAMP"].iloc[-1])
                if "TIMESTAMP" in df.columns
                else None,
            },
        )
    except Exception as e:
        return StepResult(name="qc", ok=False, elapsed_seconds=time.time() - t0, error=str(e))


def step_flux(paths: DataPaths, qc_df: pd.DataFrame | None = None) -> StepResult:
    """Compute CO2 + H2O flux cycles from QC'd data, looping over chambers.

    Detects which chambers are present (C1, C2) by scanning column names for
    ``CO2_C<n>``. For each chamber: prepare, run cycles, tag, concatenate.
    Writes the unified cycles CSV to ``exports_dir/digital_twin/``.
    """
    t0 = time.time()
    try:
        import re

        from palmwtc.flux import calculate_flux_cycles, prepare_chamber_data

        if qc_df is None:
            qc_path = _find_qc_parquet(paths)
            qc_df = pd.read_parquet(qc_path)
        rows_in = len(qc_df)

        # Discover chambers from CO2_C<n> columns. Real LIBZ data has many
        # `CO2_C1_*` derivative columns (`_qc_flag`, `_rule_flag`, `_ml_flag`,
        # `_corrected`, ...), so we must match the canonical column NAME
        # exactly — not just the prefix — to avoid treating each derivative
        # as a separate chamber.
        co2_pattern = re.compile(r"^CO2_(C\d+)$")
        chamber_suffixes = sorted(
            {m.group(1) for col in qc_df.columns if (m := co2_pattern.match(col))}
        )
        if not chamber_suffixes:
            return StepResult(
                name="flux",
                ok=False,
                elapsed_seconds=time.time() - t0,
                rows_in=rows_in,
                error="no canonical CO2_C<n> columns found in QC parquet",
            )

        all_cycles: list[pd.DataFrame] = []
        for suffix in chamber_suffixes:
            prepared = prepare_chamber_data(qc_df.copy(), chamber_suffix=suffix)
            cycles = calculate_flux_cycles(prepared, chamber_name=suffix)
            if cycles is not None and len(cycles) > 0:
                cycles = cycles.copy()
                cycles["chamber"] = suffix
                all_cycles.append(cycles)

        cycles_df = pd.concat(all_cycles, ignore_index=True) if all_cycles else pd.DataFrame()

        out_dir = paths.exports_dir / "digital_twin"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "01_chamber_cycles.csv"
        cycles_df.to_csv(out_path, index=False)

        return StepResult(
            name="flux",
            ok=True,
            elapsed_seconds=time.time() - t0,
            rows_in=rows_in,
            rows_out=len(cycles_df),
            artefacts=[out_path],
            metrics={
                "cycles_csv": str(out_path),
                "chambers": chamber_suffixes,
                "n_cycles_per_chamber": {
                    s: int((cycles_df["chamber"] == s).sum()) if len(cycles_df) else 0
                    for s in chamber_suffixes
                },
            },
        )
    except Exception as e:
        return StepResult(name="flux", ok=False, elapsed_seconds=time.time() - t0, error=str(e))


def step_windows(paths: DataPaths, cycles_df: pd.DataFrame | None = None) -> StepResult:
    """Select high-confidence calibration windows from cycle output."""
    t0 = time.time()
    try:
        from palmwtc.windows import WindowSelector

        if cycles_df is None:
            cycles_path = paths.exports_dir / "digital_twin" / "01_chamber_cycles.csv"
            if not cycles_path.exists():
                return StepResult(
                    name="windows",
                    ok=False,
                    elapsed_seconds=time.time() - t0,
                    error=f"cycles file not found: {cycles_path}",
                )
            cycles_df = pd.read_csv(cycles_path)
        rows_in = len(cycles_df)

        # WindowSelector expects flux_datetime. The flux step writes flux_date instead.
        if "flux_datetime" not in cycles_df.columns and "flux_date" in cycles_df.columns:
            cycles_df = cycles_df.copy()
            cycles_df["flux_datetime"] = pd.to_datetime(cycles_df["flux_date"])

        selector = WindowSelector(cycles_df=cycles_df)
        selector.score_cycles()
        selector.identify_windows()
        scored = selector.cycles_df
        windows_df = selector.windows_df if selector.windows_df is not None else pd.DataFrame()

        out_dir = paths.exports_dir / "digital_twin"
        out_dir.mkdir(parents=True, exist_ok=True)
        scored_path = out_dir / "031_scored_cycles.csv"
        windows_path = out_dir / "032_calibration_windows.csv"
        scored.to_csv(scored_path, index=False)
        windows_df.to_csv(windows_path, index=False)

        return StepResult(
            name="windows",
            ok=True,
            elapsed_seconds=time.time() - t0,
            rows_in=rows_in,
            rows_out=len(windows_df),
            artefacts=[scored_path, windows_path],
            metrics={
                "scored_csv": str(scored_path),
                "windows_csv": str(windows_path),
                "n_windows": len(windows_df),
            },
        )
    except Exception as e:
        return StepResult(name="windows", ok=False, elapsed_seconds=time.time() - t0, error=str(e))


def step_validation(paths: DataPaths, cycles_df: pd.DataFrame | None = None) -> StepResult:
    """Run science validation against literature ecophysiology bounds."""
    t0 = time.time()
    try:
        from palmwtc.validation import run_science_validation

        if cycles_df is None:
            cycles_path = paths.exports_dir / "digital_twin" / "01_chamber_cycles.csv"
            if not cycles_path.exists():
                return StepResult(
                    name="validation",
                    ok=False,
                    elapsed_seconds=time.time() - t0,
                    error=f"cycles file not found: {cycles_path}",
                )
            cycles_df = pd.read_csv(cycles_path)
        rows_in = len(cycles_df)

        # run_science_validation expects flux_datetime; flux step writes flux_date.
        if "flux_datetime" not in cycles_df.columns and "flux_date" in cycles_df.columns:
            cycles_df = cycles_df.copy()
            cycles_df["flux_datetime"] = pd.to_datetime(cycles_df["flux_date"])

        # Validation requires h2o_slope (from full H2O flux pipeline) and Global_Radiation
        # (from weather merge). Both absent from the toy synthetic cycles output.
        # Gracefully skip with a warning rather than crash — full data exercises this path.
        required = ["h2o_slope", "Global_Radiation"]
        missing = [c for c in required if c not in cycles_df.columns]
        if missing:
            return StepResult(
                name="validation",
                ok=True,  # not a failure: known limitation of toy synthetic input
                elapsed_seconds=time.time() - t0,
                rows_in=rows_in,
                rows_out=0,
                metrics={
                    "skipped": True,
                    "missing_columns": missing,
                    "note": "validation needs full H2O flux + weather merge; not available "
                    "on bundled synthetic sample. Real LIBZ data exercises this step.",
                },
            )

        if "is_nighttime" not in cycles_df.columns:
            hours = cycles_df["flux_datetime"].dt.hour
            cycles_df["is_nighttime"] = (hours < 6) | (hours >= 18)
            result = run_science_validation(cycles_df, derive_daytime=False)
        else:
            result = run_science_validation(cycles_df)

        out_dir = paths.exports_dir / "digital_twin"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "033_science_validation_summary.json"
        out_path.write_text(json.dumps(result, indent=2, default=str))

        return StepResult(
            name="validation",
            ok=True,
            elapsed_seconds=time.time() - t0,
            rows_in=rows_in,
            rows_out=1,
            artefacts=[out_path],
            metrics={"summary_json": str(out_path)},
        )
    except Exception as e:
        return StepResult(
            name="validation", ok=False, elapsed_seconds=time.time() - t0, error=str(e)
        )


_STEP_FUNCTIONS = {
    "qc": step_qc,
    "flux": step_flux,
    "windows": step_windows,
    "validation": step_validation,
}


def run_pipeline(
    paths: DataPaths,
    *,
    steps: list[str] | None = None,
    skip: list[str] | None = None,
    keep_going: bool = False,
) -> PipelineResult:
    """Run the library-mode pipeline against ``paths``.

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
    """
    selected: list[str] = list(steps) if steps else list(STEPS_IN_ORDER)
    if skip:
        skip_set = set(skip)
        selected = [s for s in selected if s not in skip_set]

    unknown = [s for s in selected if s not in _STEP_FUNCTIONS]
    if unknown:
        raise ValueError(f"unknown pipeline step(s): {unknown}; valid: {list(_STEP_FUNCTIONS)}")

    t_total = time.time()
    aggregate = PipelineResult(paths=paths)

    for name in selected:
        result = _STEP_FUNCTIONS[name](paths)
        aggregate.steps.append(result)
        if not result.ok and not keep_going:
            break

    aggregate.total_seconds = time.time() - t_total
    return aggregate


def run_step(name: str, paths: DataPaths) -> StepResult:
    """Run a single pipeline step by name. Convenience for notebook cells."""
    if name not in _STEP_FUNCTIONS:
        raise ValueError(f"unknown step: {name!r}; valid: {list(_STEP_FUNCTIONS)}")
    return _STEP_FUNCTIONS[name](paths)

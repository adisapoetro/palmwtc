"""Parity tests: palmwtc port vs. original flux_chamber source.

Loads the original ``flux_chamber/src/science_validation.py`` via
``importlib.util`` (not a package import — avoids polluting sys.modules with
a competing ``src`` package) and asserts numeric equality to 1e-12 against
the palmwtc port on synthetic inputs.

Skipped automatically when the flux_chamber source is not on disk (CI
environments that don't mount the monorepo sibling).
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import pytest

FLUX_CHAMBER_SRC = Path("/Users/adisapoetro/flux_chamber/src/science_validation.py")


def _load_original() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_flux_chamber_science_validation_orig", FLUX_CHAMBER_SRC
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pytestmark = pytest.mark.skipif(
    not FLUX_CHAMBER_SRC.exists(),
    reason="flux_chamber source not available at expected path",
)


def _synthetic_cycles(n_per_chamber: int = 400, seed: int = 42) -> pd.DataFrame:
    """Deterministic synthetic cycles (mirrors test_science._build_synthetic_cycles)."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2026-01-01 00:00")
    deltas_h = rng.uniform(0, 24 * 30, size=n_per_chamber * 2)
    rows = []
    for i, dh in enumerate(deltas_h):
        ts = start + pd.Timedelta(hours=float(dh))
        hour = ts.hour
        is_day = 6 <= hour < 18
        chamber = "Chamber_1" if i < n_per_chamber else "Chamber_2"
        if is_day:
            par_like = max(0.0, 400.0 * np.sin(np.pi * (hour - 6) / 12) + rng.normal(0, 50))
            radiation = par_like / 2.02
            assim = (0.04 * par_like * 12.0) / (0.04 * par_like + 12.0) - 2.0
            flux_absolute = -assim + rng.normal(0, 0.5)
            co2_slope = flux_absolute * 0.1
            h2o_slope = max(0.05, 2.0 + rng.normal(0, 0.3))
            vpd = max(0.3, 1.5 + rng.normal(0, 0.4))
            temp = 28.0 + rng.normal(0, 2.0)
        else:
            radiation = 0.0
            temp = 24.0 + rng.normal(0, 3.0)
            R = 3.0 * 2.0 ** ((temp - 25.0) / 10.0) + rng.normal(0, 0.3)
            flux_absolute = max(0.1, R)
            co2_slope = flux_absolute * 0.1
            h2o_slope = max(0.01, 0.3 + rng.normal(0, 0.1))
            vpd = max(0.1, 0.5 + rng.normal(0, 0.2))
        rows.append(
            {
                "flux_datetime": ts,
                "Source_Chamber": chamber,
                "flux_absolute": flux_absolute,
                "co2_slope": co2_slope,
                "h2o_slope": h2o_slope,
                "Global_Radiation": radiation,
                "mean_temp": temp,
                "vpd_kPa": vpd,
            }
        )
    return pd.DataFrame(rows)


def _assert_numeric_equal(a: Any, b: Any, path: str = "") -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        assert set(a.keys()) == set(b.keys()), f"key mismatch at {path}: {set(a) ^ set(b)}"
        for k in a:
            _assert_numeric_equal(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        assert len(a) == len(b), f"list length mismatch at {path}"
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _assert_numeric_equal(x, y, f"{path}[{i}]")
    elif isinstance(a, float) and isinstance(b, float):
        if math.isnan(a) and math.isnan(b):
            return
        assert a == pytest.approx(b, abs=1e-12, rel=1e-12), f"{path}: {a} != {b}"
    elif a is None and b is None:
        return
    else:
        assert a == b, f"{path}: {a!r} != {b!r}"


def test_default_config_parity() -> None:
    orig = _load_original()
    from palmwtc.validation import DEFAULT_CONFIG as PORT_CONFIG

    assert orig.DEFAULT_CONFIG == PORT_CONFIG


def test_derive_is_daytime_parity() -> None:
    orig = _load_original()
    from palmwtc.validation import derive_is_daytime

    df = _synthetic_cycles(n_per_chamber=300)
    port_result = derive_is_daytime(df)
    orig_result = orig.derive_is_daytime(df)
    pd.testing.assert_series_equal(port_result, orig_result, check_names=False)


def test_run_science_validation_parity() -> None:
    orig = _load_original()
    from palmwtc.validation import run_science_validation

    df = _synthetic_cycles(n_per_chamber=400)
    port_out = run_science_validation(df.copy(), label="parity")
    orig_out = orig.run_science_validation(df.copy(), label="parity")
    _assert_numeric_equal(port_out, orig_out)


def test_run_science_validation_parity_small_frame() -> None:
    """Small frame exercises the N/A paths in both implementations identically."""
    orig = _load_original()
    from palmwtc.validation import run_science_validation

    df = _synthetic_cycles(n_per_chamber=30)
    port_out = run_science_validation(df.copy(), label="tiny")
    orig_out = orig.run_science_validation(df.copy(), label="tiny")
    _assert_numeric_equal(port_out, orig_out)

"""Characterization tests for ``palmwtc.qc.processor``.

``QCProcessor`` is the OOP entry point ported verbatim from
``flux_chamber/src/qc_functions.py``. Keep it as a class — CLAUDE.md §1
notes the user prefers OOP.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

from palmwtc.qc.processor import QCProcessor

FLUX_CHAMBER_SRC = Path("/Users/adisapoetro/flux_chamber/src/qc_functions.py")


def _load_original() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_flux_chamber_qc_functions_orig", FLUX_CHAMBER_SRC
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_PARITY_SKIP = pytest.mark.skipif(
    not FLUX_CHAMBER_SRC.exists(),
    reason="flux_chamber source not available at expected path",
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_df() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=200, freq="4s")
    rng = np.random.default_rng(0)
    base = 25.0 + rng.normal(0, 0.5, size=200)
    base[10] = 100.0
    base[100] = -50.0
    return pd.DataFrame({"AirTC_Avg": base}, index=idx)


@pytest.fixture
def var_config_dict() -> dict:
    return {
        "AirTemp": {
            "columns": ["AirTC_Avg"],
            "hard": [-40.0, 60.0],
            "soft": [10.0, 35.0],
            "rate_of_change": {"limit": 5.0},
            "iqr_factor": 1.5,
        }
    }


# ──────────────────────────────────────────────────────────────────────────────
# Standalone tests
# ──────────────────────────────────────────────────────────────────────────────


def test_qcprocessor_constructor_copies_input(
    synthetic_df: pd.DataFrame, var_config_dict: dict
) -> None:
    proc = QCProcessor(synthetic_df, var_config_dict)
    proc.df.iloc[0, 0] = 999.0
    # Original untouched
    assert synthetic_df.iloc[0, 0] != 999.0


def test_qcprocessor_process_variable_writes_flag_columns(
    synthetic_df: pd.DataFrame, var_config_dict: dict
) -> None:
    proc = QCProcessor(synthetic_df, var_config_dict)
    result = proc.process_variable("AirTC_Avg")
    df = proc.get_processed_dataframe()
    assert "AirTC_Avg_rule_flag" in df.columns
    assert "AirTC_Avg_qc_flag" in df.columns
    # Hard violation rows propagate to flag 2
    assert df["AirTC_Avg_rule_flag"].iloc[10] == 2
    assert df["AirTC_Avg_qc_flag"].iloc[10] == 2
    assert isinstance(result, dict)
    assert "final_flags" in result


def test_qcprocessor_qc_flag_max_synced_with_rule_flag(
    synthetic_df: pd.DataFrame, var_config_dict: dict
) -> None:
    """When qc_flag pre-exists, processor uses elementwise max with rule_flag."""
    df = synthetic_df.copy()
    df["AirTC_Avg_qc_flag"] = 0
    df.loc[df.index[5], "AirTC_Avg_qc_flag"] = 2  # pre-existing flag 2 at idx 5
    proc = QCProcessor(df, var_config_dict)
    proc.process_variable("AirTC_Avg")
    out = proc.get_processed_dataframe()
    # Pre-existing flag 2 must not be demoted
    assert out["AirTC_Avg_qc_flag"].iloc[5] == 2
    # Rule-flag 2 from hard violation is also reflected
    assert out["AirTC_Avg_qc_flag"].iloc[10] == 2


def test_qcprocessor_skip_lists_passed_through(
    synthetic_df: pd.DataFrame, var_config_dict: dict
) -> None:
    proc = QCProcessor(synthetic_df, var_config_dict)
    result = proc.process_variable(
        "AirTC_Avg",
        skip_persistence=["AirTC_Avg"],
        skip_roc=["AirTC_Avg"],
    )
    # Both checks were skipped → those flag series should be all-zero
    assert (result["roc_flags"] == 0).all()
    assert (result["persistence_flags"] == 0).all()


# ──────────────────────────────────────────────────────────────────────────────
# Parity tests against original
# ──────────────────────────────────────────────────────────────────────────────


@_PARITY_SKIP
def test_parity_qcprocessor_results_match_original(
    synthetic_df: pd.DataFrame, var_config_dict: dict
) -> None:
    orig = _load_original()
    expected_proc = orig.QCProcessor(synthetic_df, var_config_dict)
    actual_proc = QCProcessor(synthetic_df, var_config_dict)
    expected_res = expected_proc.process_variable("AirTC_Avg")
    actual_res = actual_proc.process_variable("AirTC_Avg")
    pd.testing.assert_series_equal(
        actual_res["final_flags"], expected_res["final_flags"], check_exact=True
    )
    pd.testing.assert_frame_equal(
        actual_proc.get_processed_dataframe(),
        expected_proc.get_processed_dataframe(),
        check_exact=True,
    )


def test_module_reexports_match_init() -> None:
    import palmwtc.qc as qc

    assert hasattr(qc, "QCProcessor")

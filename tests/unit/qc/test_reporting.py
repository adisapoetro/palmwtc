"""Characterization tests for ``palmwtc.qc.reporting``.

Behaviour ported verbatim from ``flux_chamber/src/qc_reporting.py``. These
tests lock in:

- :func:`generate_qc_summary_from_results` — DataFrame shape + sort order.
- :func:`export_qc_data` — Parquet primary path, CSV fallback, optional
  timestamped backup.
- :func:`build_field_alert_context` — context dict shape, status badge
  thresholds, chemical-formula prettification.
- :func:`render_field_alert_html` — Jinja2 rendering against an injected
  template directory; asserts on HTML structure (not byte-identity, since
  Jinja whitespace handling can vary).

Sibling-dependency note: ``build_field_alert_context`` lazily imports
``compute_sensor_health_score`` and ``generate_recommendations`` from the
dashboard sub-package. These tests stub those modules with deterministic
implementations so the test suite does not depend on the (yet-to-be-ported)
``palmwtc.dashboard`` tree.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd
import pytest

from palmwtc.qc.reporting import (
    _COLOR_HEX,
    _prettify_chemical,
    build_field_alert_context,
    export_qc_data,
    generate_qc_summary_from_results,
    render_field_alert_html,
)

# ---------------------------------------------------------------------------
# Stub the dashboard.core dependencies of build_field_alert_context.
#
# Original lives at flux_chamber/dashboard/core/{health_scoring,recommendations}.py
# and is imported via a sys.path hack. We register dummy modules so the
# in-test import resolves without relying on the legacy directory layout.
# ---------------------------------------------------------------------------


def _install_dashboard_stubs() -> None:
    """Register fake ``dashboard.core.*`` modules with deterministic helpers."""

    def _compute_sensor_health_score(qc_summary: dict, *_, **__) -> dict:
        score = qc_summary.get("flag_0_percent", 0)
        if score >= 80:
            status, color = "Healthy", "green"
        elif score >= 50:
            status, color = "Warning", "orange"
        else:
            status, color = "Critical", "red"
        return {
            "score": round(score, 1),
            "status": status,
            "color": color,
            "factors": ["test stub"],
            "flag_0_pct": qc_summary.get("flag_0_percent", 0),
            "flag_1_pct": qc_summary.get("flag_1_percent", 0),
            "flag_2_pct": qc_summary.get("flag_2_percent", 0),
        }

    def _generate_recommendations(*_, qc_results: dict, **__) -> list[dict]:
        recs: list[dict] = []
        for var, res in qc_results.items():
            summary = res.get("summary", res)
            if summary.get("flag_2_percent", 0) > 10:
                recs.append(
                    {
                        "sensor": var,
                        "severity": "critical",
                        "action": "REPLACE",
                        "message": f"{var} is {summary['flag_2_percent']:.1f}% bad",
                    }
                )
            elif summary.get("flag_1_percent", 0) > 15:
                recs.append(
                    {
                        "sensor": var,
                        "severity": "warning",
                        "action": "CALIBRATE",
                        "message": f"{var} suspect {summary['flag_1_percent']:.1f}%",
                    }
                )
        return recs

    pkg_dashboard = types.ModuleType("dashboard")
    pkg_dashboard.__path__ = []  # mark as package
    pkg_core = types.ModuleType("dashboard.core")
    pkg_core.__path__ = []
    mod_health = types.ModuleType("dashboard.core.health_scoring")
    mod_health.compute_sensor_health_score = _compute_sensor_health_score
    mod_recs = types.ModuleType("dashboard.core.recommendations")
    mod_recs.generate_recommendations = _generate_recommendations

    sys.modules["dashboard"] = pkg_dashboard
    sys.modules["dashboard.core"] = pkg_core
    sys.modules["dashboard.core.health_scoring"] = mod_health
    sys.modules["dashboard.core.recommendations"] = mod_recs


@pytest.fixture(autouse=True)
def _stub_dashboard_modules(monkeypatch):
    """Make the lazy ``from dashboard.core...`` imports resolve to stubs."""
    _install_dashboard_stubs()
    yield
    for mod in (
        "dashboard.core.recommendations",
        "dashboard.core.health_scoring",
        "dashboard.core",
        "dashboard",
    ):
        sys.modules.pop(mod, None)


# ---------------------------------------------------------------------------
# generate_qc_summary_from_results
# ---------------------------------------------------------------------------


def _qc_summary(flag_0_pct: float, flag_1_pct: float, flag_2_pct: float, total: int = 100) -> dict:
    f0 = round(total * flag_0_pct / 100)
    f1 = round(total * flag_1_pct / 100)
    f2 = round(total * flag_2_pct / 100)
    return {
        "total_points": total,
        "flag_0_count": f0,
        "flag_0_percent": flag_0_pct,
        "flag_1_count": f1,
        "flag_1_percent": flag_1_pct,
        "flag_2_count": f2,
        "flag_2_percent": flag_2_pct,
    }


def test_generate_qc_summary_from_results_returns_sorted_dataframe():
    qc_results = {
        "var_low": {"summary": _qc_summary(50.0, 30.0, 20.0)},
        "var_high": {"summary": _qc_summary(95.0, 4.0, 1.0)},
        "var_mid": {"summary": _qc_summary(75.0, 15.0, 10.0)},
    }
    df = generate_qc_summary_from_results(qc_results)
    assert list(df.columns) == [
        "Variable",
        "Total_Records",
        "Flag_0_Good",
        "Flag_0_Pct",
        "Flag_1_Suspect",
        "Flag_1_Pct",
        "Flag_2_Bad",
        "Flag_2_Pct",
    ]
    # Sorted by Flag_0_Pct descending
    assert list(df["Variable"]) == ["var_high", "var_mid", "var_low"]
    assert df["Total_Records"].tolist() == [100, 100, 100]


def test_generate_qc_summary_from_results_handles_inline_summary():
    """V2 path: result dict already *is* the summary (no nested 'summary')."""
    qc_results = {"v": _qc_summary(80.0, 15.0, 5.0)}
    df = generate_qc_summary_from_results(qc_results)
    assert df.iloc[0]["Variable"] == "v"
    assert df.iloc[0]["Flag_0_Pct"] == 80.0


def test_generate_qc_summary_includes_optional_breakdown_columns():
    res = {
        "summary": _qc_summary(70.0, 20.0, 10.0),
        "bounds_flags": pd.Series([0, 0, 1, 1, 2]),
        "iqr_flags": pd.Series([0, 1, 0, 1, 0]),
    }
    df = generate_qc_summary_from_results({"x": res})
    assert "Bounds_Failures" in df.columns
    assert "IQR_Outliers" in df.columns
    assert df.iloc[0]["Bounds_Failures"] == 3  # entries > 0
    assert df.iloc[0]["IQR_Outliers"] == 2


# ---------------------------------------------------------------------------
# export_qc_data
# ---------------------------------------------------------------------------


def test_export_qc_data_writes_parquet_by_default(tmp_path):
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
    out = export_qc_data(df, output_dir=str(tmp_path))
    assert out == tmp_path / "QC_Flagged_Data_latest.parquet"
    assert out.exists()
    round_trip = pd.read_parquet(out)
    assert list(round_trip.columns) == ["a", "b"]
    assert len(round_trip) == 3


def test_export_qc_data_resets_timestamp_index(tmp_path):
    idx = pd.date_range("2024-01-01", periods=3, freq="h", name="TIMESTAMP")
    df = pd.DataFrame({"co2": [400.0, 401.0, 402.0]}, index=idx)
    out = export_qc_data(df, output_dir=str(tmp_path))
    rt = pd.read_parquet(out)
    assert "TIMESTAMP" in rt.columns
    assert "co2" in rt.columns


def test_export_qc_data_csv_backup(tmp_path):
    df = pd.DataFrame({"a": [1, 2, 3]})
    export_qc_data(df, output_dir=str(tmp_path), keep_csv_backup=True)
    csvs = list(tmp_path.glob("QC_Flagged_Data_*.csv"))
    assert len(csvs) == 1
    assert (tmp_path / "QC_Flagged_Data_latest.parquet").exists()


# ---------------------------------------------------------------------------
# _prettify_chemical
# ---------------------------------------------------------------------------


def test_prettify_chemical_substitutes_known_formulas():
    assert _prettify_chemical("CO2 flux") == "CO<sub>2</sub> flux"
    assert _prettify_chemical("h2o leak") == "H<sub>2</sub>O leak"
    assert _prettify_chemical("CH4 + N2O") == "CH<sub>4</sub> + N<sub>2</sub>O"


def test_prettify_chemical_leaves_sensor_ids_alone():
    """C1 and C2 must not be mangled (no `2` substitution to subscript)."""
    assert _prettify_chemical("C1 sensor") == "C1 sensor"
    assert _prettify_chemical("Chamber C2 anomaly") == "Chamber C2 anomaly"


def test_color_hex_table():
    assert _COLOR_HEX["green"] == "#2ecc71"
    assert _COLOR_HEX["orange"] == "#f39c12"
    assert _COLOR_HEX["red"] == "#e74c3c"


# ---------------------------------------------------------------------------
# build_field_alert_context
# ---------------------------------------------------------------------------


def _make_qc_dataframe(n: int = 200) -> pd.DataFrame:
    """Synthetic QC-flagged frame with rule_flag and qc_flag columns."""
    ts = pd.date_range("2024-06-01", periods=n, freq="30min")
    # CO2: mostly good (flag 0), a few bad
    co2_flags = [0] * (n - 10) + [2] * 10
    # Temp: mixed
    t_flags = [0] * (n // 2) + [1] * (n // 4) + [2] * (n // 4)
    return pd.DataFrame(
        {
            "TIMESTAMP": ts,
            "CO2_rule_flag": co2_flags,
            "Temp_qc_flag": t_flags,
            # Cross-variable check column with some flags
            "cv_temp_humidity": [0] * (n - 5) + [1] * 5,
            "cv_any_flag": [0] * n,  # should be excluded
        }
    )


def test_build_field_alert_context_returns_expected_keys():
    df = _make_qc_dataframe()
    ctx = build_field_alert_context(df, config={"healthy_threshold": 80})
    expected_keys = {
        "report_date",
        "lookback_days",
        "window_start",
        "window_end",
        "system_status",
        "status_color",
        "avg_score",
        "total_sensors",
        "healthy_count",
        "attention_sensors",
        "critical_recs",
        "warning_recs",
        "cv_issues",
        "qc_source",
        "health_rows",
        "recommendations",
    }
    assert set(ctx.keys()) == expected_keys


def test_build_field_alert_context_status_thresholds():
    """Status badge maps from avg_score using config thresholds."""
    # All sensors green (95% good)
    df = pd.DataFrame(
        {
            "TIMESTAMP": pd.date_range("2024-01-01", periods=100, freq="h"),
            "CO2_rule_flag": [0] * 95 + [2] * 5,
        }
    )
    ctx = build_field_alert_context(df, config={"healthy_threshold": 80, "warning_threshold": 50})
    assert ctx["system_status"] == "HEALTHY"
    assert ctx["status_color"] == "#2ecc71"

    # All sensors critical (0% good)
    df_bad = pd.DataFrame(
        {
            "TIMESTAMP": pd.date_range("2024-01-01", periods=100, freq="h"),
            "CO2_rule_flag": [2] * 100,
        }
    )
    ctx_bad = build_field_alert_context(
        df_bad, config={"healthy_threshold": 80, "warning_threshold": 50}
    )
    assert ctx_bad["system_status"] == "CRITICAL"
    assert ctx_bad["status_color"] == "#e74c3c"


def test_build_field_alert_context_prettifies_chemical_names():
    df = pd.DataFrame(
        {
            "TIMESTAMP": pd.date_range("2024-01-01", periods=10, freq="h"),
            "CO2_rule_flag": [0] * 8 + [2] * 2,
        }
    )
    ctx = build_field_alert_context(df, config={})
    health_vars = [h["variable"] for h in ctx["health_rows"]]
    assert any("CO<sub>2</sub>" in v for v in health_vars)


def test_build_field_alert_context_priority_variables_filter():
    df = _make_qc_dataframe()
    ctx = build_field_alert_context(df, config={}, priority_variables=["CO2"])
    health_vars = [h["variable"] for h in ctx["health_rows"]]
    # Only CO2 reported; Temp omitted
    assert any("CO" in v for v in health_vars)
    assert not any(v.startswith("Temp") for v in health_vars)


def test_build_field_alert_context_cv_issues_excludes_cv_any_flag():
    df = _make_qc_dataframe()
    ctx = build_field_alert_context(df, config={})
    issue_names = [issue["name"] for issue in ctx["cv_issues"]]
    # Only positive-pct issues retained — but cv_any_flag must never appear
    for name in issue_names:
        assert "Any Flag" not in name


def test_build_field_alert_context_window_from_index_when_no_timestamp_col():
    idx = pd.date_range("2024-03-15", periods=24, freq="h", name="TIMESTAMP")
    df = pd.DataFrame({"CO2_rule_flag": [0] * 24}, index=idx)
    ctx = build_field_alert_context(df, config={})
    # Falls through to `df.index.name` branch, then df[ts_col] (still works
    # because TIMESTAMP is the index name and reading df["TIMESTAMP"] when
    # the index has that name surfaces the column-or-index magic).
    assert ctx["window_start"].startswith("2024-03-15")


# ---------------------------------------------------------------------------
# render_field_alert_html
# ---------------------------------------------------------------------------


_TEMPLATE = """<!DOCTYPE html>
<html><body>
<h1>Field QC Alert — {{ report_date }}</h1>
<p>Status: {{ system_status }}</p>
<p>Avg score: {{ avg_score }}</p>
<p>Healthy: {{ healthy_count }}/{{ total_sensors }}</p>
{% for rec in critical_recs %}
<div class="critical">{{ rec.sensor }}: {{ rec.message }}</div>
{% endfor %}
{% for issue in cv_issues %}
<div class="cv">{{ issue.name }}: {{ issue.pct }}%</div>
{% endfor %}
</body></html>
"""


def test_render_field_alert_html_renders_template(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "field_alert.html").write_text(_TEMPLATE)
    context = {
        "report_date": "2024-06-01 12:00",
        "system_status": "HEALTHY",
        "avg_score": "92",
        "healthy_count": 5,
        "total_sensors": 6,
        "critical_recs": [{"sensor": "CO2", "message": "ok"}],
        "cv_issues": [{"name": "Temp Humidity", "pct": 3.5}],
    }
    html = render_field_alert_html(context, template_dir=template_dir)
    assert "Field QC Alert" in html
    assert "HEALTHY" in html
    assert "92" in html
    assert "5/6" in html
    assert "CO2" in html
    assert "Temp Humidity" in html


def test_render_field_alert_html_default_template_dir_resolves():
    """``template_dir=None`` must find the bundled ``field_alert.html`` template.

    Regression test for the v0.2.0 → v0.2.7 bug where the default
    ``template_dir`` pointed at the deleted ``palmwtc.dashboard`` subpackage.
    Fixed in v0.2.8: templates now live in ``palmwtc/qc/templates/``.
    """
    # Minimal valid context — every key referenced by field_alert.html must
    # be present, but values can be empty / placeholder.
    context = {
        "report_date": "2026-04-27 12:00",
        "lookback_days": 1,
        "window_start": "2026-04-26 12:00",
        "window_end": "2026-04-27 12:00",
        "system_status": "HEALTHY",
        "status_color": "#2ecc71",
        "avg_score": "100",
        "total_sensors": 0,
        "healthy_count": 0,
        "attention_sensors": [],
        "critical_recs": [],
        "warning_recs": [],
        "cv_issues": [],
        "qc_source": "020",
        "health_rows": [],
        "recommendations": [],
    }
    html = render_field_alert_html(context, template_dir=None)
    assert html.startswith("<!DOCTYPE html") or "<html" in html
    # Sanity check that template variables actually rendered.
    assert "2026-04-27" in html or "HEALTHY" in html


# ---------------------------------------------------------------------------
# Cross-check vs original (when the upstream source is reachable on disk)
# ---------------------------------------------------------------------------


_ORIGINAL_SRC = Path("/Users/adisapoetro/flux_chamber/src/qc_reporting.py")


def _load_original_module():
    if not _ORIGINAL_SRC.exists():
        return None
    import importlib.util

    spec = importlib.util.spec_from_file_location("_legacy_qc_reporting", _ORIGINAL_SRC)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(not _ORIGINAL_SRC.exists(), reason="legacy source not on disk")
def test_generate_qc_summary_matches_original():
    legacy = _load_original_module()
    if legacy is None:
        pytest.skip("legacy not loadable")
    qc_results = {
        "x": {"summary": _qc_summary(80.0, 15.0, 5.0)},
        "y": {"summary": _qc_summary(60.0, 30.0, 10.0)},
    }
    new_df = generate_qc_summary_from_results(qc_results)
    legacy_df = legacy.generate_qc_summary_from_results(qc_results)
    pd.testing.assert_frame_equal(new_df.reset_index(drop=True), legacy_df.reset_index(drop=True))

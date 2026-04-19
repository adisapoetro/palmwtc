"""Characterization tests for palmwtc.io.cloud.

Functions ported from flux_chamber/src/data_utils.py: get_cloud_sensor_dirs.
"""

from __future__ import annotations

from pathlib import Path

from palmwtc.io import get_cloud_sensor_dirs


def _mkdirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def test_get_cloud_sensor_dirs_main_only(tmp_path: Path) -> None:
    main = tmp_path / "main"
    _mkdirs(
        main / "chamber_1",
        main / "chamber_2",
        main / "climate",
        main / "soil_sensor",
    )

    result = get_cloud_sensor_dirs(tmp_path)

    assert set(result.keys()) == {"chamber_1", "chamber_2", "climate", "soil_sensor"}
    # Chambers should be non-flat (subdirs expected)
    c1 = result["chamber_1"]
    assert len(c1) == 1
    assert c1[0]["path"] == main / "chamber_1"
    assert c1[0]["is_flat"] is False

    # Climate and soil should be flat
    climate = result["climate"]
    assert len(climate) == 1
    assert climate[0]["is_flat"] is True


def test_get_cloud_sensor_dirs_with_updates(tmp_path: Path) -> None:
    main = tmp_path / "main"
    _mkdirs(main / "chamber_1")

    update = tmp_path / "update_241015"
    _mkdirs(
        update / "10_chamber1",
        update / "10_chamber2",
        update / "10_climate",
        update / "10_soil",
    )

    result = get_cloud_sensor_dirs(tmp_path)

    # chamber_1 should have main + update entry
    c1_paths = [e["path"] for e in result["chamber_1"]]
    assert main / "chamber_1" in c1_paths
    assert update / "10_chamber1" in c1_paths

    # All update entries are flat
    update_c1 = next(e for e in result["chamber_1"] if "update" in str(e["path"]))
    assert update_c1["is_flat"] is True


def test_get_cloud_sensor_dirs_multiple_updates_sorted(tmp_path: Path) -> None:
    _mkdirs(tmp_path / "main" / "chamber_1")
    _mkdirs(tmp_path / "update_240801" / "08_chamber1")
    _mkdirs(tmp_path / "update_241201" / "12_chamber1")
    _mkdirs(tmp_path / "update_241001" / "10_chamber1")

    result = get_cloud_sensor_dirs(tmp_path)
    c1_paths = [str(e["path"]) for e in result["chamber_1"]]
    # main should be first; updates chronological after that
    assert "main/chamber_1" in c1_paths[0]
    # Updates are in sorted order (lex sort of update_YYMMDD is chronological)
    assert "update_240801" in c1_paths[1]
    assert "update_241001" in c1_paths[2]
    assert "update_241201" in c1_paths[3]


def test_get_cloud_sensor_dirs_empty_base(tmp_path: Path) -> None:
    result = get_cloud_sensor_dirs(tmp_path)
    for entries in result.values():
        assert entries == []


def test_get_cloud_sensor_dirs_accepts_string(tmp_path: Path) -> None:
    _mkdirs(tmp_path / "main" / "chamber_1")
    result = get_cloud_sensor_dirs(str(tmp_path))
    assert len(result["chamber_1"]) == 1

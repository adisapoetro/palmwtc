"""Cloud / shared-drive adapters for the palmwtc package.

Ported verbatim from ``flux_chamber/src/data_utils.py`` (Phase 2).
Walks the Google Drive cloud mount layout used by the LIBZ chamber deployment.
Behaviour preservation is the prime directive.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Cloud / Multi-Source Data Helpers
# ---------------------------------------------------------------------------

# Sensor type detection patterns (matched case-insensitively against folder names)
_SENSOR_PATTERNS = {
    "chamber_1": ["chamber1", "chamber_1"],
    "chamber_2": ["chamber2", "chamber_2"],
    "climate": ["climate"],
    "soil_sensor": ["soil"],
}


def get_cloud_sensor_dirs(chamber_base) -> dict:
    """
    Discover all raw data directories for each sensor type under the cloud Chamber base.

    Searches:
      - ``<chamber_base>/main/<sensor>/``  (monthly sub-dirs for chambers, flat for others)
      - ``<chamber_base>/update_YYMMDD/<MM_sensortype>/``  (all flat, sorted chronologically)

    Returns
    -------
    dict[str, list[dict]]
        Keys: "chamber_1", "chamber_2", "climate", "soil_sensor"
        Values: list of {"path": Path, "is_flat": bool}
    """
    base = Path(chamber_base)
    result = {k: [] for k in _SENSOR_PATTERNS}

    # 1. Main folder (standard structure, same as local)
    main_dir = base / "main"
    if main_dir.exists():
        main_map = {
            "chamber_1": (main_dir / "chamber_1", False),
            "chamber_2": (main_dir / "chamber_2", False),
            "climate": (main_dir / "climate", True),
            "soil_sensor": (main_dir / "soil_sensor", True),
        }
        for sensor, (path, is_flat) in main_map.items():
            if path.exists():
                result[sensor].append({"path": path, "is_flat": is_flat})

    # 2. update_YYMMDD folders — sorted so Main is always first and updates are chronological
    update_dirs = sorted(base.glob("update_[0-9]*"))
    for update_dir in update_dirs:
        if not update_dir.is_dir():
            continue
        for subdir in sorted(update_dir.iterdir()):
            if not subdir.is_dir():
                continue
            name_lower = subdir.name.lower()
            for sensor, patterns in _SENSOR_PATTERNS.items():
                if any(p in name_lower for p in patterns):
                    result[sensor].append({"path": subdir, "is_flat": True})
                    break

    for sensor, entries in result.items():
        print(
            f"  Cloud {sensor}: {len(entries)} director{'y' if len(entries) == 1 else 'ies'} found"
        )

    return result

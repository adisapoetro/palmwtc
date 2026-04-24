"""Cloud / shared-drive adapters for palmwtc.

The LIBZ automated whole-tree chamber deployment exports raw logger files to
a shared Google Drive folder that is mounted locally as a drive letter or
FUSE mount.  The folder hierarchy inside this mount follows a two-level
layout:

- ``<chamber_base>/main/<sensor>/`` — the primary archive, mirrors the
  on-site local backup.  Chamber subdirectories contain monthly sub-folders;
  climate and soil-sensor subdirectories are flat.
- ``<chamber_base>/update_YYMMDD/<MM_sensortype>/`` — one or more
  incremental update folders appended whenever the SD cards are downloaded
  in the field.  All update sub-folders are flat.

:func:`get_cloud_sensor_dirs` walks this layout and returns a structured
dict that :func:`~palmwtc.io.load_from_multiple_dirs` can consume directly.
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


def get_cloud_sensor_dirs(chamber_base: Path | str) -> dict[str, list[dict]]:
    """Discover all raw-data directories for each sensor type under the cloud chamber base.

    Walks the Google Drive mount layout used by the LIBZ deployment.  The
    result is a dict of directory entries ready for
    :func:`~palmwtc.io.load_from_multiple_dirs`.

    Search order (determines deduplication priority in
    :func:`~palmwtc.io.load_from_multiple_dirs`):

    1. ``<chamber_base>/main/<sensor>/`` — primary archive; chamber
       subdirectories have monthly sub-folders (``is_flat=False``); climate
       and soil-sensor subdirectories are flat (``is_flat=True``).
    2. ``<chamber_base>/update_YYMMDD/<MM_sensortype>/`` — incremental update
       folders, sorted chronologically.  All are flat (``is_flat=True``).

    Sensor-type detection uses case-insensitive substring matching against
    the subdirectory name:

    - ``"chamber_1"`` — names containing ``"chamber1"`` or ``"chamber_1"``.
    - ``"chamber_2"`` — names containing ``"chamber2"`` or ``"chamber_2"``.
    - ``"climate"``   — names containing ``"climate"``.
    - ``"soil_sensor"`` — names containing ``"soil"``.

    Parameters
    ----------
    chamber_base : Path or str
        Root of the mounted Google Drive share for one chamber site
        (e.g. the local path of the shared drive folder).

    Returns
    -------
    dict[str, list[dict]]
        Keys are ``"chamber_1"``, ``"chamber_2"``, ``"climate"``, and
        ``"soil_sensor"``.  Each value is a list of ``{"path": Path,
        "is_flat": bool}`` dicts, suitable as the *dir_entries* argument of
        :func:`~palmwtc.io.load_from_multiple_dirs`.  Missing sensor types
        have an empty list.

    Examples
    --------
    >>> from pathlib import Path
    >>> from palmwtc.io import get_cloud_sensor_dirs
    >>> dirs = get_cloud_sensor_dirs(Path("/mnt/gdrive/LIBZ_Chamber"))  # doctest: +SKIP
    >>> list(dirs.keys())  # doctest: +SKIP
    ['chamber_1', 'chamber_2', 'climate', 'soil_sensor']
    """
    base = Path(chamber_base)
    result: dict[str, list[dict]] = {k: [] for k in _SENSOR_PATTERNS}

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

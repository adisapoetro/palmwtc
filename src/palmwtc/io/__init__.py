"""palmwtc.io — data loading, path resolution, and cloud-mount adapters.

This subpackage handles everything between raw logger files on disk and a
clean :class:`pandas.DataFrame` ready for the QC and flux pipelines.  Three
modules cover distinct concerns:

- :mod:`palmwtc.io.loaders` — reads the pre-integrated monthly CSV files
  (``Integrated_Data_YYYY-MM.csv``) and raw TOA5 ``.dat`` files from one
  or more directories.  Also writes monthly export CSVs.
- :mod:`palmwtc.io.paths` — resolves QC-file paths given a data directory,
  and produces a :func:`~palmwtc.io.paths.data_integrity_report` summary.
- :mod:`palmwtc.io.cloud` — walks the Google Drive mount layout used by the
  LIBZ deployment to discover all raw-data directories for each sensor type.

All public helpers are re-exported here.  Callers can write::

    from palmwtc.io import load_monthly_data, get_cloud_sensor_dirs

without needing to know which sub-module each function lives in.
"""

from palmwtc.io.cloud import get_cloud_sensor_dirs
from palmwtc.io.loaders import (
    export_monthly,
    integrate_temp_humidity_c2,
    load_data_in_range,
    load_from_multiple_dirs,
    load_monthly_data,
    load_radiation_data,
    read_toa5_file,
)
from palmwtc.io.paths import (
    data_integrity_report,
    find_latest_qc_file,
    get_usecols,
)

__all__ = [
    "data_integrity_report",
    "export_monthly",
    "find_latest_qc_file",
    "get_cloud_sensor_dirs",
    "get_usecols",
    "integrate_temp_humidity_c2",
    "load_data_in_range",
    "load_from_multiple_dirs",
    "load_monthly_data",
    "load_radiation_data",
    "read_toa5_file",
]

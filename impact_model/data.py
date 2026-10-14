# -*- coding: utf-8 -*-
"""
Reading the ERA5 data that drive the model.

Two small NetCDF files in `data/` are produced once by
`scripts/prepare_era5_data.py` and then committed to the repository:

    era5_mopani_daily.nc   daily rainfall, maximum and minimum temperature,
                           averaged over the Mopani study area
    era5_sst_monthly.nc    monthly sea surface temperature averaged over the
                           Nino 3.4 box and over the whole tropical band

Students do not need a Copernicus account. See `data/README.md` for how the
files were made.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

from .config import STUDY_AREA
from .weather import reference_et_hargreaves

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DAILY_FILE = DATA_DIR / "era5_mopani_daily.nc"
SST_FILE = DATA_DIR / "era5_sst_monthly.nc"


class MissingDataError(FileNotFoundError):
    """Raised when the processed ERA5 files have not been created yet."""


def _open(path: Path):
    if not path.exists():
        raise MissingDataError(
            f"{path.name} was not found in {path.parent}.\n"
            "The processed ERA5 files are created once with\n"
            "    python scripts/prepare_era5_data.py download\n"
            "    python scripts/prepare_era5_data.py process\n"
            "and then committed to the repository. If you cloned the repository and "
            "see this message, ask the lecturer."
        )
    try:
        import xarray as xr
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise ImportError(
            "Reading the ERA5 files needs xarray and netCDF4. "
            "Activate the 'impact' conda environment."
        ) from error
    return xr.open_dataset(path)


@lru_cache(maxsize=1)
def load_daily_weather() -> pd.DataFrame:
    """
    Daily ERA5 weather for the study area, with reference evapotranspiration.

    Returns a frame indexed by date with columns `precip` (mm/day), `t_max`,
    `t_min`, `t_mean` (degC) and `et0` (mm/day, Hargreaves-Samani). Days are
    South African Standard Time (UTC+2) calendar days.
    """
    with _open(DAILY_FILE) as ds:
        frame = pd.DataFrame(
            {
                "precip": ds["precip"].to_numpy().astype(float),
                "t_max": ds["t_max"].to_numpy().astype(float),
                "t_min": ds["t_min"].to_numpy().astype(float),
            },
            index=pd.DatetimeIndex(ds["time"].to_numpy()).normalize(),
        )
    frame = frame.sort_index()
    frame.index.name = "date"
    frame["precip"] = frame["precip"].clip(lower=0.0)
    frame["t_mean"] = 0.5 * (frame["t_max"] + frame["t_min"])
    frame["et0"] = reference_et_hargreaves(
        frame["t_min"].to_numpy(),
        frame["t_max"].to_numpy(),
        frame.index.dayofyear.to_numpy(),
        STUDY_AREA.centre_latitude,
    )
    if frame[["precip", "t_max", "t_min"]].isna().any().any():
        gaps = int(frame[["precip", "t_max", "t_min"]].isna().any(axis=1).sum())
        raise ValueError(f"The daily ERA5 file has {gaps} days with missing values.")
    return frame


@lru_cache(maxsize=1)
def load_monthly_sst() -> pd.DataFrame:
    """
    Monthly ERA5 sea surface temperature (degC): `nino34` over the Nino 3.4 box
    (5S-5N, 170W-120W) and `tropics` over the whole 20S-20N band, ocean only.
    Indexed by the first day of each month.
    """
    with _open(SST_FILE) as ds:
        frame = pd.DataFrame(
            {
                "nino34": ds["nino34_sst"].to_numpy().astype(float),
                "tropics": ds["tropical_sst"].to_numpy().astype(float),
            },
            index=pd.DatetimeIndex(ds["time"].to_numpy()).to_period("M").to_timestamp(),
        )
    frame.index.name = "month"
    return frame.sort_index().dropna()


def data_summary() -> dict:
    """What period the bundled files cover, for display and for checks."""
    daily = load_daily_weather()
    sst = load_monthly_sst()
    return {
        "daily_start": daily.index[0],
        "daily_end": daily.index[-1],
        "sst_start": sst.index[0],
        "sst_end": sst.index[-1],
        "mean_annual_rainfall": float(daily["precip"].resample("YS").sum().iloc[1:-1].mean()),
    }


def clear_cache() -> None:
    """Forget loaded data, for example after the files have been regenerated."""
    load_daily_weather.cache_clear()
    load_monthly_sst.cache_clear()


__all__ = [
    "DATA_DIR",
    "DAILY_FILE",
    "SST_FILE",
    "MissingDataError",
    "clear_cache",
    "data_summary",
    "load_daily_weather",
    "load_monthly_sst",
]

# -*- coding: utf-8 -*-
"""
Prepare the ERA5 data the model uses. This is run once by the lecturer, not by
students, and the two small output files are committed to the repository.

Step 1, download (needs a Copernicus CDS account and a ~/.cdsapirc file; see
https://cds.climate.copernicus.eu/how-to-api):

    python scripts/prepare_era5_data.py download

Step 2, process the raw files into data/era5_mopani_daily.nc and
data/era5_sst_monthly.nc:

    python scripts/prepare_era5_data.py process

The raw downloads go to data/raw/, which is ignored by git. They come to
roughly 0.5 GB, mostly the tropical SST fields. The download is done year by
year and skips files that already exist, so it can be interrupted and resumed.
CDS queue times vary from minutes to hours.

What is downloaded:

  * Hourly 2 m temperature and total precipitation from ERA5
    (reanalysis-era5-single-levels) over the Mopani study box set in
    impact_model/config.py, 1979 to the last complete month.
  * Monthly mean sea surface temperature (reanalysis-era5-single-levels-monthly-means)
    over the tropical band 20S-20N.

What processing does:

  * Mopani: averages over the grid points in the box (weighted by the cosine of
    latitude), then builds daily totals of rainfall and daily maximum and
    minimum temperature for South African Standard Time (UTC+2) days.
  * SST: averages over the Nino 3.4 box (5S-5N, 170W-120W) and over all ocean
    points in 20S-20N, giving two monthly series. The relative index itself is
    computed in impact_model/climate.py, so the recipe stays visible.
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from impact_model.config import FIRST_SEASON, STUDY_AREA  # noqa: E402

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
HOURLY_DIR = RAW_DIR / "mopani_hourly"
SST_DIR = RAW_DIR / "sst_monthly"
DAILY_OUT = DATA_DIR / "era5_mopani_daily.nc"
SST_OUT = DATA_DIR / "era5_sst_monthly.nc"

HOURLY_VARIABLES = {"total_precipitation": "tp", "2m_temperature": "t2m"}
TROPICAL_BAND = [20, -180, -20, 180]          # north, west, south, east
NINO34_BOX = dict(lat=(-5.0, 5.0), lon360=(190.0, 240.0))
LOCAL_UTC_OFFSET_HOURS = 2                    # South African Standard Time


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _months_for(year: int, today: dt.date) -> list:
    """All months, or only completed months for the current year."""
    if year < today.year:
        return [f"{m:02d}" for m in range(1, 13)]
    return [f"{m:02d}" for m in range(1, today.month)]


def _retrieve(client, dataset: str, request: dict, target: Path) -> None:
    if target.exists() and target.stat().st_size > 0:
        print(f"  have  {target.relative_to(ROOT)}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    print(f"  get   {target.relative_to(ROOT)}")
    client.retrieve(dataset, request, str(partial))
    partial.rename(target)


def download(first_year: int, last_year: int) -> None:
    try:
        import cdsapi
    except ImportError:
        sys.exit("cdsapi is not installed. Activate the 'impact' environment first.")

    client = cdsapi.Client()
    today = dt.date.today()
    days = [f"{d:02d}" for d in range(1, 32)]
    hours = [f"{h:02d}:00" for h in range(24)]

    print(f"Mopani box {STUDY_AREA.cds_area} (N, W, S, E), hourly, {first_year}-{last_year}")
    for year in range(first_year, last_year + 1):
        months = _months_for(year, today)
        if not months:
            continue
        # One variable per request: asking for an instantaneous and an
        # accumulated variable together makes the CDS return a zip of two files.
        for variable, short in HOURLY_VARIABLES.items():
            _retrieve(
                client,
                "reanalysis-era5-single-levels",
                {
                    "product_type": ["reanalysis"],
                    "variable": [variable],
                    "year": [str(year)],
                    "month": months,
                    "day": days,
                    "time": hours,
                    "area": STUDY_AREA.cds_area,
                    "data_format": "netcdf",
                    "download_format": "unarchived",
                },
                HOURLY_DIR / f"{short}_{year}.nc",
            )

    print(f"Tropical SST {TROPICAL_BAND} (N, W, S, E), monthly means, {first_year}-{last_year}")
    for year in range(first_year, last_year + 1):
        months = _months_for(year, today)
        if not months:
            continue
        _retrieve(
            client,
            "reanalysis-era5-single-levels-monthly-means",
            {
                "product_type": ["monthly_averaged_reanalysis"],
                "variable": ["sea_surface_temperature"],
                "year": [str(year)],
                "month": months,
                "time": ["00:00"],
                "area": TROPICAL_BAND,
                "data_format": "netcdf",
                "download_format": "unarchived",
            },
            SST_DIR / f"sst_{year}.nc",
        )
    print("Done. Now run: python scripts/prepare_era5_data.py process")


# ---------------------------------------------------------------------------
# Process
# ---------------------------------------------------------------------------

def _tidy(ds):
    """Make files from the old and new CDS look the same: a 'time' dimension, no ensemble."""
    if "valid_time" in ds.dims or "valid_time" in ds.coords:
        ds = ds.rename({"valid_time": "time"})
    if "expver" in ds.dims:
        # Older files split recent ERA5T data onto a second expver level.
        ds = ds.max("expver", skipna=True)
    drop = [name for name in ("number", "expver", "step", "surface") if name in ds.coords]
    return ds.drop_vars(drop)


def _box_mean(da, lat_mask=None, lon_mask=None):
    """Area mean weighted by cos(latitude), ignoring missing (land) points."""
    if lat_mask is not None:
        da = da.isel(latitude=np.where(lat_mask)[0])
    if lon_mask is not None:
        da = da.isel(longitude=np.where(lon_mask)[0])
    weights = np.cos(np.deg2rad(da["latitude"]))
    valid = da.notnull()
    total = (da.fillna(0.0) * weights).sum(("latitude", "longitude"))
    norm = (valid * weights).sum(("latitude", "longitude"))
    return total / norm


def _process_hourly():
    import pandas as pd
    import xarray as xr

    def series(short: str) -> "pd.Series":
        files = sorted(HOURLY_DIR.glob(f"{short}_*.nc"))
        if not files:
            sys.exit(f"No raw files {short}_*.nc in {HOURLY_DIR}. Run the download step first.")
        parts = []
        for path in files:
            with xr.open_dataset(path) as ds:
                ds = _tidy(ds)
                mean = _box_mean(ds[short]).load()
            parts.append(mean.to_series())
        out = pd.concat(parts).sort_index()
        return out[~out.index.duplicated(keep="last")].dropna()

    tp = series("tp") * 1000.0                     # m per hour -> mm per hour
    t2m = series("t2m") - 273.15                   # K -> degC
    offset = pd.Timedelta(hours=LOCAL_UTC_OFFSET_HOURS)

    # ERA5 hourly precipitation at time t is the total over the hour ending at t,
    # so that hour starts at t - 1 h. Assign it to the local day it starts in.
    rain_day = (tp.index - pd.Timedelta(hours=1) + offset).floor("D")
    temp_day = (t2m.index + offset).floor("D")

    precip = tp.clip(lower=0.0).groupby(rain_day).agg(["sum", "count"])
    temp = t2m.groupby(temp_day).agg(["max", "min", "count"])
    daily = pd.DataFrame(
        {"precip": precip["sum"], "t_max": temp["max"], "t_min": temp["min"]}
    )
    complete = (precip["count"] == 24).reindex(daily.index, fill_value=False) & (
        temp["count"] == 24
    ).reindex(daily.index, fill_value=False)
    daily = daily[complete].dropna()

    first = pd.Timestamp(FIRST_SEASON, 1, 1)
    daily = daily[daily.index >= first]
    # Keep one unbroken run of days; a gap would silently shift the seasons.
    gaps = daily.index.to_series().diff().dt.days.fillna(1)
    if (gaps > 1).any():
        sys.exit(f"Daily record has gaps, first after {gaps[gaps > 1].index[0].date()}.")

    ds = xr.Dataset(
        {
            "precip": ("time", daily["precip"].to_numpy("float32"),
                       {"units": "mm day-1", "long_name": "daily total precipitation"}),
            "t_max": ("time", daily["t_max"].to_numpy("float32"),
                      {"units": "degC", "long_name": "daily maximum of hourly 2 m temperature"}),
            "t_min": ("time", daily["t_min"].to_numpy("float32"),
                      {"units": "degC", "long_name": "daily minimum of hourly 2 m temperature"}),
        },
        coords={"time": daily.index.to_numpy()},
        attrs={
            "title": f"ERA5 daily weather averaged over {STUDY_AREA.name}",
            "source": "ERA5 hourly data on single levels (reanalysis-era5-single-levels), Copernicus Climate Change Service",
            "area_north_west_south_east": str(STUDY_AREA.cds_area),
            "day_definition": "South African Standard Time (UTC+2) calendar days",
            "area_weighting": "cos(latitude) over ERA5 grid points in the box",
            "created": dt.datetime.now().isoformat(timespec="seconds"),
            "created_by": "scripts/prepare_era5_data.py",
        },
    )
    ds.to_netcdf(DAILY_OUT)
    print(f"  wrote {DAILY_OUT.relative_to(ROOT)}: {daily.index[0].date()} to "
          f"{daily.index[-1].date()}, mean annual rainfall "
          f"{daily['precip'].resample('YS').sum().iloc[:-1].mean():.0f} mm")


def _process_sst():
    import pandas as pd
    import xarray as xr

    files = sorted(SST_DIR.glob("sst_*.nc"))
    if not files:
        sys.exit(f"No raw SST files in {SST_DIR}. Run the download step first.")

    nino, tropics = [], []
    for path in files:
        with xr.open_dataset(path) as ds:
            ds = _tidy(ds)
            sst = ds["sst"] - 273.15
            lat = sst["latitude"].to_numpy()
            lon360 = np.mod(sst["longitude"].to_numpy(), 360.0)
            nino_lat = (lat >= NINO34_BOX["lat"][0]) & (lat <= NINO34_BOX["lat"][1])
            nino_lon = (lon360 >= NINO34_BOX["lon360"][0]) & (lon360 <= NINO34_BOX["lon360"][1])
            tropical_lat = (lat >= -20.0) & (lat <= 20.0)
            nino.append(_box_mean(sst, nino_lat, nino_lon).load().to_series())
            tropics.append(_box_mean(sst, tropical_lat).load().to_series())

    frame = pd.DataFrame({"nino34": pd.concat(nino), "tropics": pd.concat(tropics)}).sort_index()
    frame = frame[~frame.index.duplicated(keep="last")].dropna()
    frame.index = frame.index.to_period("M").to_timestamp()

    ds = xr.Dataset(
        {
            "nino34_sst": ("time", frame["nino34"].to_numpy("float32"),
                           {"units": "degC", "long_name": "mean SST over 5S-5N, 170W-120W"}),
            "tropical_sst": ("time", frame["tropics"].to_numpy("float32"),
                             {"units": "degC", "long_name": "mean SST over all ocean points 20S-20N"}),
        },
        coords={"time": frame.index.to_numpy()},
        attrs={
            "title": "ERA5 monthly mean SST for the relative Nino 3.4 index",
            "source": "ERA5 monthly averaged data on single levels, Copernicus Climate Change Service",
            "area_weighting": "cos(latitude), ocean points only",
            "created": dt.datetime.now().isoformat(timespec="seconds"),
            "created_by": "scripts/prepare_era5_data.py",
        },
    )
    ds.to_netcdf(SST_OUT)
    print(f"  wrote {SST_OUT.relative_to(ROOT)}: {frame.index[0]:%Y-%m} to {frame.index[-1]:%Y-%m}")


def process() -> None:
    print("Processing hourly Mopani data")
    _process_hourly()
    print("Processing monthly SST")
    _process_sst()
    print("Done. Check with: python scripts/check_install.py")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="step", required=True)
    get = sub.add_parser("download", help="download raw ERA5 files from the CDS")
    get.add_argument("--first-year", type=int, default=FIRST_SEASON)
    get.add_argument("--last-year", type=int, default=dt.date.today().year)
    sub.add_parser("process", help="reduce the raw files to the two committed NetCDF files")
    args = parser.parse_args()

    if args.step == "download":
        download(args.first_year, args.last_year)
    else:
        process()


if __name__ == "__main__":
    main()

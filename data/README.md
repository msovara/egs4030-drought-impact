# Data used by the model

Both files are produced by `scripts/prepare_era5_data.py` from ERA5 (Hersbach
et al., 2020), made available by the Copernicus Climate Change Service. They are
small enough to keep in the repository, so students need no Copernicus account.

## `era5_mopani_daily.nc`

Daily weather averaged over the study area, from 1979.

| Variable | Units | Meaning |
|---|---|---|
| `precip` | mm/day | Total precipitation |
| `t_max` | °C | Highest hourly 2 m temperature of the day |
| `t_min` | °C | Lowest hourly 2 m temperature of the day |

Days are South African Standard Time (UTC+2) calendar days. ERA5 hourly
precipitation is the total over the hour ending at the time stamp, so each hour
is assigned to the local day in which it starts. Because the daily extremes are
taken from hourly values, the true maximum and minimum are slightly
underestimated.

**Study area.** 23.0–24.0°S, 30.5–31.0°E (5 × 3 ERA5 grid points), set in
`impact_model/config.py` as `STUDY_AREA`. It covers the dryland maize areas of
the Mopani lowveld around Giyani and Letsitele, east of the escarpment and west
of the Kruger National Park. The escarpment is left out on purpose: rainfall
there is much higher, and ERA5's 0.25° grid cannot resolve the gradient, so
including it would mix two quite different climates. If you change the box,
rerun both steps of the preparation script.

## `era5_sst_monthly.nc`

Monthly mean sea surface temperature, ocean points only, weighted by the cosine
of latitude.

| Variable | Units | Meaning |
|---|---|---|
| `nino34_sst` | °C | Mean over 5°S–5°N, 170°W–120°W |
| `tropical_sst` | °C | Mean over all ocean points in 20°S–20°N |

The relative Niño 3.4 index is calculated from these in
`impact_model/climate.py`, following the C3S definition:

1. Each series is expressed as an anomaly from its 1993–2016 monthly
   climatology (the C3S hindcast period).
2. The tropical anomaly is subtracted from the Niño 3.4 anomaly.
3. The difference is multiplied by a scaling factor for each calendar month:
   the standard deviation of the Niño 3.4 anomaly divided by the standard
   deviation of the difference, both over 1991–2020. This gives the relative
   index the same year-to-year variability as the traditional index.

## Recreating the files

Needs a Copernicus CDS account with the ERA5 licence accepted, and an API key in
`~/.cdsapirc` (see <https://cds.climate.copernicus.eu/how-to-api>).

```bash
conda activate impact
python scripts/prepare_era5_data.py download    # resumable; CDS queues vary
python scripts/prepare_era5_data.py process
python scripts/check_install.py
```

The raw downloads (about 0.5 GB) go to `data/raw/`, which git ignores. Only the
two processed files need to be committed.

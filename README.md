# From the ocean to the maize field

A small crop water-balance model for the EGS4030/5030S guest lecture on climate
impact modelling at the University of Cape Town (19 October 2026), and the
practical assignment that follows it.

The model follows one chain from the ocean to a maize field: the relative
Niño 3.4 index, November to March rainfall over the Mopani district of Limpopo,
a daily soil water balance, and the resulting maize yield. It is small enough to
read in an afternoon and runs a growing season in a few milliseconds, so
students can run thousands of seasons on a laptop and see how the answer changes
when an assumption changes. That is something they cannot easily do with the
coupled climate and hydrological models they meet elsewhere in the module.

The practical is built around three ideas:

- understand the physical mechanism before describing the observed relationship;
- an ENSO index is not, in itself, a measure of local agricultural impact;
- a strong El Niño shifts the odds of particular outcomes but does not determine
  the outcome of any individual season.

The student brief is in [`student_task/TASK_BRIEF.md`](student_task/TASK_BRIEF.md).

---

## Getting started

Clone the repository and work from its root. The ERA5 files are already in
`data/`. No Copernicus account and no API key.

```bash
git clone https://github.com/msovara/egs4030-drought-impact.git
cd egs4030-drought-impact
git checkout stefaantask
```

`stefaantask` is the class branch. `main` is the earlier demonstration and will not run this practical.

### Dashboard on any laptop

Same shape as a normal Python project: a virtual environment, then one install
file, then the app.

```bash
python -m venv .venv
```

Activate it (`source .venv/bin/activate` on macOS or Linux, `.venv\Scripts\activate` on Windows), then:

```bash
python -m pip install -r requirements.txt
python scripts/check_install.py
python -m streamlit run app.py
```

The dashboard opens at <http://localhost:8501>. `check_install.py` takes a few
seconds and ends with one line saying whether the machine is ready.

`requirements.txt` is enough for the dashboard and for the figure templates.
It is also what a hosted copy of this branch would install.

### The practical environment (WSL and miniforge)

The class machines already use conda. That path installs the same packages,
plus cartopy if you want maps:

```bash
conda env create -f environment.yml
conda activate impact
python scripts/check_install.py
streamlit run app.py
```

Figure templates are in `student_task/templates/`. `python scripts/run_demo.py --help`
lists text-only views.

A `FAIL` from `check_install.py` means the model will not run. A `WARN` means
it still runs; the message says what is missing. The warning that
`C3S_FORECAST` is empty is expected: Tab 4 asks you to type the DJF range from
the C3S chart.

---

## Data

All inputs come from ERA5 (Copernicus Climate Change Service) and are stored in
two small NetCDF files in `data/`, so students need no Copernicus account and no
network connection:

| File | Contents |
|---|---|
| `era5_mopani_daily.nc` | Daily rainfall and maximum and minimum temperature, averaged over the study area, from 1979 |
| `era5_sst_monthly.nc` | Monthly mean SST over the Niño 3.4 box and over the 20°S–20°N band, from 1979 |

They are created once by the lecturer with
`scripts/prepare_era5_data.py` (download, then process). See
[`data/README.md`](data/README.md) for the details, including the study area
and the choices behind it.

### Before each teaching season

1. Refresh the ERA5 files so that they include the most recent season.
2. Enter the DJF range from the latest C3S relative Niño 3.4 forecast in
   `C3S_FORECAST` in `impact_model/climate.py`. Until this is filled in,
   `check_install.py` gives a warning and the forecast tab asks for the values.
3. Run `check_install.py` and look at its summary of the fitted ENSO–rainfall
   relationship. If the slope is not negative, check the study area and the
   index before teaching with it.

---

## How the model works

| Step | Method | Module |
|---|---|---|
| ENSO index | DJF relative Niño 3.4 following the C3S definition: the Niño 3.4 SST anomaly minus the 20°S–20°N mean anomaly (both relative to 1993–2016), rescaled month by month to the variability of the traditional index over 1991–2020 | `climate.py` |
| Local rainfall | November–March ERA5 rainfall over the study area | `climate.py` |
| ENSO–rainfall link | Least-squares line through the 1979–present seasons, with bootstrap refits for its uncertainty | `climate.py` |
| Atmospheric demand | Hargreaves–Samani (Hargreaves & Samani, 1985) reference evapotranspiration from ERA5 temperature | `weather.py` |
| Soil water | FAO-56 (Allen et al., 1998) single crop coefficient root-zone balance, with SCS curve-number runoff | `crop.py` |
| Yield | FAO-33 (Doorenbos & Kassam, 1979) stage-weighted yield response to water shortage | `crop.py` |
| Experiments | Historical runs, the same-rainfall experiment and the uncertainty cascade | `experiment.py` |

Yield is reported as a percentage of the yield with no water shortage. The
absolute figure for dryland maize in Mopani depends on management and is not
something this model can supply.

### The season ahead

NOAA CPC's advisory of 8 October 2026 had Niño 3.4 at +2.1 °C, with a strong-to-very strong event likely through January–March 2027 and an 83% chance that October–December exceeds any event since 1950. The three closest analogues in the observed record — 1982/83, 1997/98 and 2015/16 — are the seasons of the best-documented southern African crop failures.

For the forward experiment, for each ensemble member it:

1. draws a DJF index value from the forecast range;
2. turns it into a November–March rainfall total using the fitted line (and, from
   step 2 of the cascade onwards, a refitted line plus the scatter of a past
   season about it);
3. borrows the daily rainfall and temperature of a past season with a broadly
   similar total, scaled to the new total;
4. runs the crop model, from step 4 onwards with a soil and a flowering
   sensitivity drawn from a plausible range.

Adding these steps one at a time shows how uncertainty accumulates along the
chain. The same calculation for a neutral ENSO range, and the model run on the
actual historical seasons, give two reference distributions.

### Package layout

```
impact_model/
    config.py       study area, period, soils, crop, planting dates
    data.py         reading the two ERA5 files
    climate.py      relative Niño 3.4, Mopani rainfall, the fitted link, the C3S forecast range
    weather.py      reference evapotranspiration; rescaling a season's rainfall
    crop.py         the impact model: soil water balance and yield response
    experiment.py   historical runs, same-rainfall experiment, uncertainty cascade
    indices.py      SPI and SPEI, available for comparison
app.py              Streamlit dashboard, five tabs following the practical
scripts/
    check_install.py      pre-session check of packages, data and model behaviour
    run_demo.py           text-only views of the model
    prepare_era5_data.py  one-off download and processing of the ERA5 inputs
student_task/
    TASK_BRIEF.md         the assignment
    templates/            one script per figure in the assignment
environment.yml     conda environment (conda-forge only)
```

If you only read one file, read `crop.py`.

---

## Using the dashboard in the lecture

The tabs follow the order of the assignment.

1. **One season.** Pick a past season and watch the root-zone water fall through
   the stress threshold. The growth stages are shaded, so it is easy to see
   whether a dry spell fell during flowering. 2015/16 is a useful starting
   point. Finish on the stage table, which shows exactly where the yield went.
2. **Same rain, different harvests.** Every past season is given the same
   November–March total, keeping its own timing. The spread of yields comes
   from timing alone.
3. **ENSO and Mopani rainfall.** The fitted relationship, its scatter, and the
   El Niño seasons that were not dry. The expander compares the relative and
   traditional indices.
4. **The 2026/27 season.** The uncertainty cascade for the C3S forecast range,
   against a neutral season and the historical record.
5. **About the model.** Equations, parameters, data and what is left out.

A possible outline for the session, to adjust as needed:

| Time | Content |
|---|---|
| 0:00–0:25 | What is an impact model, and how does it differ from a climate model |
| 0:25–0:45 | The equations, on the board, using Tab 5 |
| 0:45–1:15 | Live demonstration, Tabs 1 and 2 |
| 1:15–1:30 | Break |
| 1:30–1:45 | Tab 3, ENSO, rainfall and maize in Limpopo |
| 1:45–2:00 | Tab 4: The season ahead |
| 2:00–2:10 | Tab 6: WRF-Hydro and the cluster fit |
| 2:10–2:30 | The assignment, and getting everyone running |

---

## What the model leaves out

These are worth discussing openly with the class; they are part of what the
practical is about.

- **The ENSO–rainfall link is a straight line through fewer than fifty
  seasons**, with only a few strong El Niño events. A strong forecast can lie
  near or beyond the edge of the data.
- **The relative index must match the forecast product.** The forecast range is
  read from the C3S relative Niño 3.4 plume, so the historical index follows the
  C3S definition: the same anomaly base period (1993–2016) and the same
  month-by-month scaling factor, computed over 1991–2020. It is calculated from
  ERA5 SST rather than from the SST products behind the C3S verification, which
  may introduce small differences.
- **ERA5 rainfall is reanalysis output, not gauge data.** It tends to produce too
  many days of light rain, which affects dry-spell lengths, and at 0.25° it
  cannot represent the escarpment.
- **The forward runs reuse past daily sequences**, so they cannot produce a
  pattern of wet and dry days that has not occurred since 1979.
- **One point, one crop, water only.** There is no spatial variation, no
  nutrient limitation, no pests, and no farmer decisions apart from the
  planting date.
- **Soil water at planting is estimated roughly** from the preceding months, and
  soil reached by growing roots is assumed to be at field capacity (the
  `new_soil_relative_depletion` argument of `run_season` changes this).

---

## References

Allen, R.G., Pereira, L.S., Raes, D. and Smith, M. (1998) *Crop
evapotranspiration: guidelines for computing crop water requirements*. FAO
Irrigation and Drainage Paper 56. Rome: FAO.

Doorenbos, J. and Kassam, A.H. (1979) *Yield response to water*. FAO Irrigation
and Drainage Paper 33. Rome: FAO.

Hargreaves, G.H. and Samani, Z.A. (1985) 'Reference crop evapotranspiration from
temperature', *Applied Engineering in Agriculture*, 1(2), pp. 96–99.

Hersbach, H. et al. (2020) 'The ERA5 global reanalysis', *Quarterly Journal of
the Royal Meteorological Society*, 146(730), pp. 1999–2049.

L'Heureux, M.L. et al. (2024) 'A relative sea surface temperature index for
classifying ENSO events in a changing climate', *Journal of Climate*, 37(4),
pp. 1197–1211.

van Oldenborgh, G.J. et al. (2021) 'Defining El Niño indices in a warming
climate', *Environmental Research Letters*, 16(4), 044003.

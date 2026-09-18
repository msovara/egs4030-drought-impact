# From the ocean to the maize field

A desktop-scale climate impact model for the EGS4030/5030S guest lecture on
climate impact modelling.

The package runs a complete impact chain — observed ocean state, to seasonal
rainfall, to a daily soil water balance, to crop yield — in milliseconds per
season on an ordinary laptop. That speed is the pedagogical point. Students can
change an assumption and see the consequence immediately, which is not something
they can do with the coupled models they meet in the rest of the module.

---

## Quick start

```bash
pip install -r requirements.txt

python scripts/check_install.py                          # 71 checks, ~12 seconds
python scripts/run_demo.py --site limpopo --observed     # text output
python scripts/run_demo.py --site limpopo --scenario 2.4 # the season ahead
streamlit run app.py                                     # interactive dashboard
```

The dashboard opens at <http://localhost:8501>.

Run `check_install.py` on the lecture room machine before the session, and have
the students run it on their own laptops at the start of the practical. It
verifies the dependencies, exercises every site and crop, confirms the water
balance closes to within a rounding error, and checks that the model responds in
the right direction to rainfall, irrigation and warming. A single line of output
tells you whether a machine is ready.

No cluster, no data download, no API key. Both observational inputs are bundled
in `data/`: `nino34_monthly.csv`, NOAA CPC's monthly Niño 3.4 record from 1950,
and `dmi_son_annual_averages.csv`, the SON Dipole Mode Index for 1980–2020.

---

## Two climate drivers

The driver is a parameter, not a hard-wired choice. Everything downstream of
`climate.py` is identical either way, which is the clearest argument the package
makes for keeping the driver in its own module.

| | ENSO (default) | IOD |
|---|---|---|
| Index | Niño 3.4 | Dipole Mode Index |
| Season | DJF, **inside** the growing season | SON, **before** planting |
| Record | 1950–2025, 76 seasons | 1980–2020, 41 seasons |
| Events in record | 24 El Niño, 28 La Niña | 7 positive, 7 negative |
| Assumed sensitivity | −0.14 per sd | −0.09 per sd |
| Composite signal | separable, p < 0.001 | not separable, p ≈ 0.7 |

Select it in the sidebar, or with `--driver` on the command line. The two are
correlated at r = 0.61 over their common years, which is itself worth raising:
attributing an impact to one rather than the other is genuinely hard.

**The contrast is the teaching point.** The ENSO signal is stronger and its
record is nearly twice as long, so its composite survives a significance test.
The IOD composite does not, and flips sign depending on the random seed. Neither
result is a bug. They are what a short record and a weak teleconnection buy you,
and a student who understands why has understood most of what seasonal
prediction can and cannot do.

### The 2026/27 season

The lecture falls inside a developing El Niño. NOAA CPC's advisory of 10
September 2026 had Niño 3.4 at +1.8 °C with a 75% chance that October–December
would exceed any event since 1950. The three closest analogues in the observed
record — 1982/83, 1997/98 and 2015/16 — are the seasons of the best-documented
southern African crop failures.

Tab 4 runs the model forward on that. The advisory figures are recorded in
`climate.CPC_ADVISORY` with their source, so they can be cited rather than
asserted, and updated when the season moves on.

---

## What the model actually is

Three layers, all standard in operational agricultural drought assessment, and
all short enough to read in one sitting.

| Layer | Method | Source |
|---|---|---|
| Atmospheric demand | Hargreaves–Samani reference evapotranspiration | Hargreaves & Samani (1985) |
| Soil water | FAO-56 single crop coefficient root zone water balance | Allen et al. (1998) |
| Yield | FAO-33 stage-weighted yield response to water deficit | Doorenbos & Kassam (1979) |
| Runoff | SCS curve number | USDA-SCS (1972) |
| Drought indices | SPI (gamma) and SPEI (log-logistic) | McKee et al. (1993); Vicente-Serrano et al. (2010) |

The crop is stressed once root zone depletion passes the readily available water
threshold, and the resulting transpiration deficit is converted to yield loss
with a stage-dependent response factor `Ky`. For maize `Ky` is 1.5 during
flowering against 0.4 during vegetative growth, which is the mechanism behind
the lecture's central claim: **when the rain fails matters more than how much
fails.**

---

## Package layout

```
impact_model/
    config.py       sites, soils, crops, growth stages
    climate.py      observed ENSO and IOD, and the assumed link to local rainfall
    weather.py      daily weather generator and reference evapotranspiration
    crop.py         THE IMPACT MODEL: water balance and yield response
    indices.py      SPI and SPEI
    experiment.py   multi-season runs, composites, scenarios, sensitivity sweeps
    driver_error.py measured Mvula v5 forecast skill
app.py              Streamlit dashboard, seven tabs following the lecture
scripts/run_demo.py command-line demonstration
scripts/check_install.py  pre-session verification
data/               the two bundled observational records
student_task/       assessment brief
```

If you read one file, read `crop.py`. It is the model.

---

## Running the lecture

The dashboard tabs are ordered to match the session.

**Tab 1 — One season, day by day.** Drag the rainfall slider and watch the soil
water store fall through the stress threshold. The growth stages are shaded, so
it is visually obvious when a dry spell lands on flowering. Finish on the stage
table, which shows exactly where the yield went.

**Tab 2 — Why timing beats totals.** An ensemble at each rainfall anomaly, where
members differ only in the day-to-day sequence of rain. The spread is large.
This is the tab that kills the idea that seasonal rainfall total is a sufficient
predictor.

**Tab 3 — The observed record.** 76 observed seasons of Niño 3.4 driven through
the model, composited by phase, with the significance test reported on screen.
Point out the bad seasons that were *not* El Niño years. Then switch the driver
to the IOD in the sidebar and show the same analysis collapsing into noise.

**Tab 4 — The season ahead.** The model run forward on the developing El Niño,
against a neutral baseline with paired weather seeds. Two things to land here:
the distributions overlap, so a historic El Niño shifts the odds without
settling the outcome; and the closest analogues are 1982, 1997 and 2015, which
the students can go and check against what actually happened.

**Tab 5 — Index is not impact.** SPI against modelled yield. The correlation is
real but far from perfect, and the dashboard lists the seasons in the worst
yield quartile that SPI would not have flagged as a drought at all.

**Tab 6 — When the driver is wrong.** The measured skill of
[Mvula v5](https://github.com/msovara/lapai-forecast-africa), a lightweight
African weather model, used to put a real number on what a driver error costs.

The evaluation is analysis-forced: every entry is a *single* +6 h step from a
fresh ERA5 analysis in a 00Z campaign, so the four rows are **times of day, not
forecast lead times**. The tell is that RMSE runs 1.38, 7.80, 4.38, 3.23 — a
decay curve cannot come back down. Read as times of day the pattern is one
coherent fault: unbiased at dawn, 5.33 °C too cold in the early afternoon, 1.30 °C
too warm at night. The model has not learnt the daily heating cycle.

That matters more than a cold bias would, because Hargreaves–Samani takes the
square root of the daily *range*. Driving the crop model with a damped diurnal
cycle cuts evaporative demand from about 511 mm to 330 mm and makes it report
more than double the true harvest. A student who assumed the error was a simple
uniform offset would have predicted an error about six times smaller and
concluded it was tolerable. The structure of the error mattered more than its
size, and the headline RMSE said nothing about it.

**Tab 7 — The model itself.** Equations and parameters, for the students who
want to know what they have been clicking on.

Suggested shape for the 2.5 hours:

| Time | Content |
|---|---|
| 0:00–0:25 | What is an impact model, and how does it differ from a climate model |
| 0:25–0:45 | The equations, on the board, using Tab 7 |
| 0:45–1:15 | Live demonstration, Tabs 1 and 2 |
| 1:15–1:30 | Break |
| 1:30–1:50 | Tab 3, both drivers, and what the significance test says |
| 1:50–2:05 | Tab 4: the season ahead, and Tab 5: index against impact |
| 2:05–2:20 | Tab 6: driver error, and where WRF-Hydro and the cluster fit |
| 2:20–2:30 | The assignment, and getting everyone running |

### The three-rung ladder

If you demonstrate Mvula in the first half, the session gains a structure that
carries the whole argument about model complexity and computational cost:

| Rung | Model | Timescale | Runs on |
|---|---|---|---|
| Environmental information | Mvula v5 CNN, 8.8 MiB | +6 hours | Laptop CPU, ~2.5 s |
| Impact | This crop water balance | One season, 140 days | Laptop CPU, ~16 ms |
| Coupled physical | WRF-Hydro over the Inkomati | Continuous | Lengau |

Mvula belongs in the demonstration, driven by you. The crop model belongs in the
students' hands and in the assignment, because it needs no data download, no
CDS API key and no network. Note that Mvula's initial conditions come from a
0.25° ARCO ERA5 store on Google Cloud at roughly 16 MiB per state, which is
fine for one machine on the podium and a poor bet for thirty laptops at once.

---

## What this model is not

It is worth being blunt with the students about this, and the dashboard says so
on Tab 6.

- **The teleconnection is an assumption, not a result.** Both index records are
  observed. The step from an index to local rainfall is an illustrative
  sensitivity, not a fitted regression. It is built from a correlation and a
  coefficient of variation, and `climate.DEFAULT_SENSITIVITY_NOTE` shows the
  arithmetic so students can argue with it. `climate.fit_sensitivity` exists so
  it can be replaced with a real one, and doing so is part of the assessment.
- **The phase classification depends on the period you select.** Events are
  declared against the mean of the years being analysed, not against a fixed
  climatology, because NOAA's published Niño 3.4 anomalies use a 1991–2020 base
  period that leaves a cold offset over a record starting in 1950. Pass
  `baseline="file"` to `load_index` to see the published classification instead.
- **The scenario is a scenario.** Tab 4 takes an index value you choose and runs
  the model on it. It is not a seasonal forecast, and RONI, which is what CPC
  forecasts, is not the same quantity as the raw Niño 3.4 anomaly.
- **The weather is generated, not observed.** A two-state Markov chain with
  gamma-distributed wet-day amounts reproduces plausible daily sequences, but it
  is not a reanalysis. It is used so the demonstration runs offline on any
  machine. The extension task swaps it for ERA5.
- **One point, not a field.** There is no lateral flow, no spatial
  heterogeneity, no nutrient limitation, no pests, no farmer decisions. Real
  yield gaps in southern Africa are frequently driven by nitrogen and by
  planting date, not by water alone.
- **Yield is potential-relative.** The absolute tonnages depend entirely on the
  assumed unstressed potential yield, which is a crude single number per crop.
- **Root growth is assumed to reach charged soil.** By default the soil that
  roots newly reach is at field capacity, which is the standard FAO-56
  simplification and is optimistic on a dryland profile. It contributes around a
  quarter of the season's water supply, so it matters. The
  `new_soil_relative_depletion` argument to `run_season` exists so this can be
  varied, and doing so makes a good exercise.

Every one of these is a legitimate discussion point rather than an apology. Being
explicit about where a model stops being trustworthy is most of what impact
modelling actually involves.

---

## References

Allen, R.G., Pereira, L.S., Raes, D. and Smith, M. (1998) *Crop
evapotranspiration: guidelines for computing crop water requirements*. FAO
Irrigation and Drainage Paper 56. Rome: FAO.

Doorenbos, J. and Kassam, A.H. (1979) *Yield response to water*. FAO Irrigation
and Drainage Paper 33. Rome: FAO.

Hargreaves, G.H. and Samani, Z.A. (1985) 'Reference crop evapotranspiration from
temperature', *Applied Engineering in Agriculture*, 1(2), pp. 96–99.

McKee, T.B., Doesken, N.J. and Kleist, J. (1993) 'The relationship of drought
frequency and duration to time scales', *Proceedings of the 8th Conference on
Applied Climatology*, pp. 179–184.

Vicente-Serrano, S.M., Beguería, S. and López-Moreno, J.I. (2010) 'A multiscalar
drought index sensitive to global warming: the Standardized Precipitation
Evapotranspiration Index', *Journal of Climate*, 23(7), pp. 1696–1718.

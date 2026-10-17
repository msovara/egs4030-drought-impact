# -*- coding: utf-8 -*-
"""
Check that the model and its data work before relying on them.

Checks the Python packages, the bundled ERA5 files, the relative Nino 3.4 index,
the fitted ENSO-rainfall relationship, the crop model and the uncertainty
cascade, and checks that results are physically sensible rather than merely
free of errors. Run it at the start of each session:

    conda activate impact
    python scripts/check_install.py

The core packages are required. The packages used only for students' own
figures and maps (matplotlib, cartopy) and for downloading data (cdsapi) are
reported as warnings if missing, so that the hosted dashboard still passes.
"""

import os
import sys
import time
import traceback
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

failures: list[str] = []
warnings: list[str] = []
checks = 0

CONDA_ENV_NAME = "impact"

# (import name, distribution name, minimum version or None, what it is for)
CORE_MODULES = [
    ("numpy", "numpy", None, "model"),
    ("pandas", "pandas", None, "model"),
    ("scipy", "scipy", None, "model"),
    ("xarray", "xarray", None, "reading the ERA5 files"),
    ("netCDF4", "netCDF4", None, "reading the ERA5 files"),
    ("plotly", "plotly", None, "dashboard"),
    ("streamlit", "streamlit", None, "dashboard"),
]
TASK_MODULES = [
    ("cdsapi", "cdsapi", (0, 7, 2), "downloading ERA5 (lecturer only)"),
    ("matplotlib", "matplotlib", None, "the figure templates"),
    ("cartopy", "cartopy", None, "maps"),
]


def check(condition: bool, message: str) -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(message)
        print(f"  FAIL  {message}")


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * 74)


def warn(message: str) -> None:
    warnings.append(message)
    print(f"  WARN  {message}")


def version_of(module, distribution: str) -> str:
    version = getattr(module, "__version__", None)
    if version:
        return str(version)
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "unknown"


def version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for piece in version.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


print("=" * 74)
print("EGS4030/5030S drought impact model: installation check")
print("=" * 74)

started = time.perf_counter()

section("Environment")
print(f"  info  Python {sys.version.split()[0]} at {sys.executable}")
active_env = os.environ.get("CONDA_DEFAULT_ENV")
in_venv = sys.prefix != sys.base_prefix or bool(os.environ.get("VIRTUAL_ENV"))
if active_env == CONDA_ENV_NAME:
    print(f"  ok    conda environment '{active_env}' is active")
elif in_venv:
    print("  ok    running inside a virtual environment (pip install is fine)")
elif active_env:
    warn(f"conda environment '{active_env}' is active, not '{CONDA_ENV_NAME}'. "
         f"Run 'conda activate {CONDA_ENV_NAME}' first")
else:
    print("  info  no conda environment active (fine for a pip install)")
    print(f"        for the practical, run 'conda activate {CONDA_ENV_NAME}' first")

section("Core dependencies (required)")
for module, distribution, _, purpose in CORE_MODULES:
    try:
        imported = __import__(module)
        print(f"  ok    {module:<12} {version_of(imported, distribution):<10} {purpose}")
        checks += 1
    except ImportError:
        failures.append(f"{module} is not installed")
        print(f"  FAIL  {module} is not installed")

section("Student task packages (installed by environment.yml)")
for module, distribution, minimum, purpose in TASK_MODULES:
    try:
        imported = __import__(module)
    except Exception as error:  # a broken binary raises more than ImportError
        reason = "is not installed" if isinstance(error, ImportError) else \
            f"failed to import ({type(error).__name__}: {error})"
        warn(f"{module} {reason}, needed for {purpose}")
        continue
    version = version_of(imported, distribution)
    if minimum and version_tuple(version) < minimum:
        warn(f"{module} {version} is older than "
             f"{'.'.join(map(str, minimum))}, needed for {purpose}")
    else:
        print(f"  ok    {module:<12} {version:<10} {purpose}")


# The model is imported only after the dependency check, so that a missing
# package is reported clearly rather than as an import traceback.
if failures:
    print("\nCore packages are missing, so the model checks were skipped.")
    print("Run 'conda activate impact', or recreate the environment from environment.yml.")
    sys.exit(1)

import numpy as np  # noqa: E402

from impact_model.climate import (  # noqa: E402
    C3S_FORECAST,
    fit_teleconnection,
    forecast_djf_range,
    load_enso_index,
    monthly_enso_indices,
    rainy_season_totals,
)
from impact_model.config import (  # noqa: E402
    FIRST_SEASON,
    MAIZE,
    PLANTING_DATES,
    SOILS,
)
from impact_model.crop import relative_yield_from_arrays  # noqa: E402
from impact_model.data import (  # noqa: E402
    MissingDataError,
    load_daily_weather,
    load_monthly_sst,
)
from impact_model.experiment import (  # noqa: E402
    CASCADE_STAGES,
    run_cascade,
    run_historical,
    run_one_season,
    same_total_experiment,
    season_weather,
)

section("ERA5 data files")
try:
    weather = load_daily_weather()
    sst = load_monthly_sst()
except MissingDataError as error:
    print(f"  FAIL  {error}")
    failures.append("The processed ERA5 files are missing")
    print("\nFAILED: the model cannot run without its data.")
    sys.exit(1)

try:
    print(f"  ok    daily Mopani weather {weather.index[0].date()} to {weather.index[-1].date()}")
    print(f"  ok    monthly SST {sst.index[0]:%Y-%m} to {sst.index[-1]:%Y-%m}")
    check(weather.index[0] <= np.datetime64(f"{FIRST_SEASON}-07-01"),
          "Daily weather should start early enough to spin up the 1979 season")
    check(sst.index[-1] >= np.datetime64("2026-02-01"),
          "SST should reach at least February 2026, the end of the 2025/26 DJF season")
    gaps = int((weather.index.to_series().diff().dt.days > 1).sum())
    check(gaps == 0, f"Daily weather has {gaps} gaps")
    annual = weather["precip"].resample("YS").sum().iloc[1:-1]
    check(200 < annual.mean() < 1500,
          f"Mean annual rainfall {annual.mean():.0f} mm is outside 200-1500 mm")
    check(20 < weather["t_max"].mean() < 38,
          f"Mean daily maximum temperature {weather['t_max'].mean():.1f} degC is implausible")
    check((weather["t_max"] >= weather["t_min"]).all(), "Some days have t_max below t_min")
    check(20 < sst["nino34"].mean() < 32, "Nino 3.4 SST should be in degC")
    print(f"  ok    mean annual rainfall {annual.mean():.0f} mm, mean daily maximum "
          f"{weather['t_max'].mean():.1f} degC")
except Exception:
    failures.append("ERA5 data check raised an exception")
    traceback.print_exc()

section("Relative Nino 3.4 index and Mopani rainfall")
try:
    enso = load_enso_index()
    rain = rainy_season_totals()
    counts = enso["phase"].value_counts()
    check(enso.index[0] == FIRST_SEASON, f"Index should start with the {FIRST_SEASON} season")
    check(len(enso) >= 45, f"Expected at least 45 DJF seasons, got {len(enso)}")
    check(counts.get("El Nino", 0) >= 5 and counts.get("La Nina", 0) >= 3,
          "Too few El Nino or La Nina seasons; check the index calculation")
    factors = monthly_enso_indices().attrs["scaling_factors"]
    check(factors.between(0.8, 2.5).all(),
          f"Relative index scaling factors {factors.min():.2f}-{factors.max():.2f} look implausible")
    print(f"  ok    C3S scaling factors by month {factors.min():.2f} to {factors.max():.2f}")
    check(0.3 < enso["relative"].std() < 2.0,
          f"Relative index standard deviation {enso['relative'].std():.2f} degC is implausible")
    check(len(rain) >= 45, f"Expected at least 45 complete rainy seasons, got {len(rain)}")
    print(f"  ok    {len(enso)} DJF seasons {enso.index[0]}-{enso.index[-1]}: "
          + ", ".join(f"{k} {v}" for k, v in counts.items()))
    print(f"  ok    {len(rain)} Nov-Mar seasons, median {rain.median():.0f} mm, "
          f"range {rain.min():.0f}-{rain.max():.0f} mm")

    fit = fit_teleconnection()
    check(np.isfinite(fit.slope) and fit.n >= 45, "Teleconnection fit failed")
    print(f"  ok    fitted relationship: {fit.summary()}")
    if fit.slope >= 0:
        warn("The fitted slope is not negative: El Nino is not associated with less "
             "rain in this record. Check the study area and the index before teaching.")
except Exception:
    failures.append("Index or rainfall check raised an exception")
    traceback.print_exc()

section("Crop model")
try:
    seasons = list(rain.index)
    season = int(seasons[len(seasons) // 2])
    result, _ = run_one_season(season)
    daily = result.daily
    storage_change = float(daily["soil_water"].iloc[-1] - result.metadata["initial_soil_water"])
    inputs = float(daily["precip"].sum() - daily["runoff"].sum() + daily["root_zone_gain"].sum())
    outputs = float(daily["et_actual"].sum() + daily["deep_percolation"].sum())
    residual = inputs - outputs - storage_change
    check(abs(residual) < 0.5, f"Water balance residual {residual:.2f} mm should be near zero")
    print(f"  ok    {season} season: water balance closes to {residual:+.3f} mm")

    _, growing = season_weather(season)
    check(len(growing) >= MAIZE.season_length, "Season weather is too short")
    initial_depletion = 1 - result.metadata["initial_soil_water"] / daily["total_available_water"].iloc[0]
    fast = relative_yield_from_arrays(
        growing["precip"].to_numpy(), growing["et0"].to_numpy(), MAIZE,
        SOILS["sandy_loam"], initial_depletion,
    )
    check(abs(fast - result.relative_yield) < 1e-9, "Fast and full yield calculations disagree")

    yields = [run_one_season(season, rain_factor=f)[0].relative_yield for f in (0.5, 1.0, 1.5)]
    check(yields[0] <= yields[1] <= yields[2], f"Yield should not fall as rain increases: {yields}")
    sandy = run_one_season(season, soil_key="sand", rain_factor=0.7)[0].relative_yield
    loam = run_one_season(season, soil_key="loam", rain_factor=0.7)[0].relative_yield
    check(sandy <= loam + 1e-9, "A sand should not out-yield a loam in a dry season")
    for planting in PLANTING_DATES:
        run_one_season(season, planting=planting)
    print(f"  ok    rain x0.5, x1, x1.5 gives {yields[0]:.0%}, {yields[1]:.0%}, {yields[2]:.0%} "
          f"of potential; all planting dates run")
except Exception:
    failures.append("Crop model check raised an exception")
    traceback.print_exc()

section("Historical runs and the same-rainfall experiment")
try:
    history = run_historical()
    check(len(history) >= 45, f"Expected at least 45 historical seasons, got {len(history)}")
    check(history["relative_yield"].between(0, 1).all(), "Relative yield outside 0-1")
    r_rain = history["relative_yield"].corr(history["rainfall"])
    check(r_rain > 0, "Modelled yield should increase with seasonal rainfall overall")
    same = same_total_experiment()
    totals = rain.loc[same.index] * same["scale_factor"]
    check(float(np.ptp(totals)) < 0.5, "Same-total experiment did not equalise the totals")
    print(f"  ok    {len(history)} seasons; yield vs rainfall r = {r_rain:.2f}")
    print(f"  ok    all seasons at {same.attrs['total_mm']:.0f} mm: yields "
          f"{same['relative_yield'].min():.0%} to {same['relative_yield'].max():.0%}")
except Exception:
    failures.append("Historical run check raised an exception")
    traceback.print_exc()

section("Uncertainty cascade")
try:
    forecast = forecast_djf_range()
    if forecast is None:
        info("C3S_FORECAST in impact_model/climate.py to be filled in in `impact_model/climate.py`; "
             "checking with a placeholder range of 1.0 to 2.0 degC")
        test_range = (1.0, 2.0)
    else:
        test_range = forecast
        print(f"  ok    C3S forecast range {forecast[0]:+.2f} to {forecast[1]:+.2f} degC "
              f"({C3S_FORECAST['band']})")
    cascade = run_cascade(test_range, members=120)
    summary = cascade.stage_summary()
    first, last = CASCADE_STAGES[0][1], CASCADE_STAGES[-1][1]
    check(summary.loc[last, "spread_p10_p90"] >= summary.loc[first, "spread_p10_p90"],
          "The spread should not shrink as sources of uncertainty are added")
    check(0.2 < summary.loc["Historical seasons, 1979 on", "prob_poor"] < 0.45,
          "About a third of historical seasons should count as poor")
    print(f"  ok    spread (10th-90th percentile) widens from "
          f"{summary.loc[first, 'spread_p10_p90']:.0%} to {summary.loc[last, 'spread_p10_p90']:.0%}")
    print(f"  ok    chance of a poor season: {summary.loc[last, 'prob_poor']:.0%} for this range, "
          f"{summary.loc['Neutral ENSO, all uncertainty', 'prob_poor']:.0%} for a neutral season")
except Exception:
    failures.append("Cascade check raised an exception")
    traceback.print_exc()

elapsed = time.perf_counter() - started

print("\n" + "=" * 74)
if failures:
    print(f"FAILED: {len(failures)} of {checks} checks did not pass ({elapsed:.1f} s)")
    for failure in failures:
        print(f"  - {failure}")
    sys.exit(1)

print(f"All {checks} checks passed in {elapsed:.1f} s. The model is ready.")
if warnings:
    print(f"\n{len(warnings)} warning(s):")
    for message in warnings:
        print(f"  - {message}")
    if any("not installed" in m or "older than" in m or "failed to import" in m for m in warnings):
        print(f"Missing packages can be fixed from the repository root with: "
              f"conda env update -n {CONDA_ENV_NAME} -f environment.yml --prune")
print("=" * 74)

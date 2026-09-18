# -*- coding: utf-8 -*-
"""
Multi-season experiments: the full chain from an observed ocean index to crop yield.

This is the module that makes the lecture's argument. It builds one continuous
daily climate record for the whole observed period, applies the index-driven
rainfall anomaly season by season, runs the impact model for each growing season,
and composites the resulting yields by climate phase.

The driver is a parameter, not a hard-wired choice. Running the same impact model
from ENSO and from the IOD, and asking which one predicts the harvest better, is
a more interesting question than either index on its own.

Building a single continuous record matters for more than tidiness. SPI and SPEI
are defined by fitting a distribution to each calendar month across many years,
so they can only be computed on a long record. Running each season in isolation
would make the drought indices meaningless.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .climate import (
    DEFAULT_DRIVER,
    ClimateDriver,
    TeleconnectionAssumption,
    get_driver,
    load_index,
    rainfall_anomaly_from_index,
)
from .config import CROPS, SITES, SOILS, Crop, Site
from .crop import SeasonResult, run_season
from .indices import (
    standardized_precipitation_evapotranspiration_index,
    standardized_precipitation_index,
)
from .weather import WeatherGeneratorParams, generate_weather

# The water balance needs some spin-up before planting so the season does not
# start from an arbitrary soil moisture state.
SPINUP_DAYS = 120


@dataclass
class ObservedRun:
    """Everything a multi-year run produces, kept together for the dashboard."""

    seasons: pd.DataFrame          # one row per growing season
    weather: pd.DataFrame          # the continuous daily climate record
    monthly: pd.DataFrame          # monthly totals with SPI and SPEI attached
    site: Site
    crop: Crop
    assumption: TeleconnectionAssumption
    driver: ClimateDriver          # which ocean index drove the run


def _planting_date(site: Site, year: int) -> pd.Timestamp:
    """
    Planting date for the season attributed to `year`.

    Summer-rainfall sites plant late in the calendar year and harvest in the next,
    so the season labelled 1997 is planted in November 1997. Winter-rainfall sites
    plant and harvest within the same calendar year.
    """
    return pd.Timestamp(year=year, month=1, day=1) + pd.Timedelta(
        days=site.planting_day_of_year - 1
    )


def _season_year(dates: pd.DatetimeIndex, planting_day_of_year: int) -> np.ndarray:
    """
    Label each date with the growing season it belongs to.

    A season runs from its planting date to the day before the next planting date,
    so for a November-planted crop the whole of January to October belongs to the
    season that was planted in the previous calendar year.
    """
    return np.where(
        dates.dayofyear.to_numpy() >= planting_day_of_year,
        dates.year.to_numpy(),
        dates.year.to_numpy() - 1,
    )


# Planting follows the onset of the rains rather than a fixed date, so the profile
# is never bone dry at sowing. Capping the initial deficit below the depletion
# fraction stops every run from showing spurious establishment stress.
MAX_INITIAL_DEPLETION_FRACTION = 0.50


def _initial_depletion(spinup: pd.DataFrame, capacity_mm: float) -> float:
    """
    Estimate the pre-planting soil water deficit from the spin-up period.

    A crude bucket is enough here: the point is only to avoid starting every
    season from the same arbitrary moisture state, which would otherwise wash out
    the effect of a dry antecedent period.
    """
    balance = float((spinup["precip"] - 0.35 * spinup["et0"]).sum())
    deficit = 0.85 - balance / max(capacity_mm * 3.0, 1e-6)
    return float(np.clip(deficit, 0.05, MAX_INITIAL_DEPLETION_FRACTION))


def run_single_season(
    site: Site,
    crop: Crop,
    rainfall_anomaly: float,
    year: int = 2000,
    temperature_shift: float = 0.0,
    irrigation_mm_per_week: float = 0.0,
    seed: Optional[int] = None,
    diurnal_range_shift: float = 0.0,
) -> Tuple[SeasonResult, pd.DataFrame]:
    """
    Run one season in isolation and return the result with its driving weather.

    Used by the single-season view and the sensitivity sweep. Multi-year runs go
    through `run_observed_record` instead, which shares one climate record.
    """
    soil = SOILS[site.soil]
    planting = _planting_date(site, year)
    start = planting - pd.Timedelta(days=SPINUP_DAYS)

    params = WeatherGeneratorParams(
        rainfall_anomaly=rainfall_anomaly,
        temperature_shift=temperature_shift,
        diurnal_range_shift=diurnal_range_shift,
        seed=seed,
    )
    weather = generate_weather(
        site, start=start, days=SPINUP_DAYS + crop.season_length + 30, params=params
    )

    capacity = soil.available_water_capacity * crop.rooting_depth_initial
    result = run_season(
        weather.iloc[SPINUP_DAYS:],
        crop=crop,
        soil=soil,
        initial_depletion_fraction=_initial_depletion(weather.iloc[:SPINUP_DAYS], capacity),
        irrigation_mm=_weekly_irrigation(irrigation_mm_per_week, crop.season_length),
    )
    return result, weather


def _weekly_irrigation(mm_per_week: float, season_days: int) -> Optional[np.ndarray]:
    if mm_per_week <= 0:
        return None
    irrigation = np.zeros(season_days)
    irrigation[::7] = mm_per_week
    return irrigation


def run_observed_record(
    site_key: str,
    crop_key: str,
    driver: "str | ClimateDriver" = DEFAULT_DRIVER,
    assumption: Optional[TeleconnectionAssumption] = None,
    temperature_shift: float = 0.0,
    irrigation_mm_per_week: float = 0.0,
    seed: int = 42,
    index_record: Optional[pd.DataFrame] = None,
    min_year: Optional[int] = None,
) -> ObservedRun:
    """
    Run the impact model across every season in the observed index record.

    One continuous daily climate series is generated for the whole period, with
    each growing season's rainfall scaled by the anomaly implied by that season's
    ocean index. SPI and SPEI are then computed once on the full record, and the
    value at the end of the flowering stage is attached to each season.
    """
    site = SITES[site_key]
    crop = CROPS[crop_key]
    soil = SOILS[site.soil]
    spec = get_driver(driver)
    assumption = assumption or TeleconnectionAssumption.for_driver(spec)

    frame = (
        index_record
        if index_record is not None
        else load_index(spec, min_year=min_year)
    )

    years = [int(year) for year in frame.index]
    rng = np.random.default_rng(seed)

    anomaly_by_year = {
        year: rainfall_anomaly_from_index(
            float(frame.loc[year, "index_standardized"]),
            site_key,
            assumption,
            driver=spec,
            rng=rng,
        )
        for year in years
    }

    # Cover a spin-up year before the first season and a full year after the last,
    # so that every season has antecedent conditions and SPI has a complete record.
    start = pd.Timestamp(year=years[0] - 1, month=1, day=1)
    end = _planting_date(site, years[-1]) + pd.Timedelta(days=crop.season_length + 40)
    dates = pd.date_range(start=start, end=end, freq="D")

    season_labels = _season_year(dates, site.planting_day_of_year)
    anomaly_series = pd.Series(
        [anomaly_by_year.get(int(label), 0.0) for label in season_labels], index=dates
    )

    weather = generate_weather(
        site,
        start=start,
        days=len(dates),
        params=WeatherGeneratorParams(
            temperature_shift=temperature_shift, seed=int(rng.integers(0, 2**31 - 1))
        ),
        rainfall_anomaly=anomaly_series,
    )

    monthly = pd.DataFrame(
        {
            "precip": weather["precip"].resample("MS").sum(),
            "pet": weather["et0"].resample("MS").sum(),
            "t_mean": weather["t_mean"].resample("MS").mean(),
        }
    )
    monthly["spi3"] = standardized_precipitation_index(monthly["precip"], scale=3)
    monthly["spi6"] = standardized_precipitation_index(monthly["precip"], scale=6)
    monthly["spei3"] = standardized_precipitation_evapotranspiration_index(
        monthly["precip"], monthly["pet"], scale=3
    )

    irrigation = _weekly_irrigation(irrigation_mm_per_week, crop.season_length)
    capacity = soil.available_water_capacity * crop.rooting_depth_initial
    flowering_end_day = (
        crop.stage_lengths["initial"]
        + crop.stage_lengths["development"]
        + crop.stage_lengths["mid"]
    )

    records: List[Dict[str, float]] = []
    for year in years:
        planting = _planting_date(site, year)
        harvest = planting + pd.Timedelta(days=crop.season_length - 1)
        if harvest > weather.index[-1]:
            continue

        spinup = weather.loc[planting - pd.Timedelta(days=SPINUP_DAYS) : planting - pd.Timedelta(days=1)]
        season_weather = weather.loc[planting:harvest]

        result = run_season(
            season_weather,
            crop=crop,
            soil=soil,
            initial_depletion_fraction=_initial_depletion(spinup, capacity),
            irrigation_mm=irrigation,
        )

        flowering = result.stage_summary.set_index("stage").loc["mid"]
        flowering_month = (planting + pd.Timedelta(days=flowering_end_day)).to_period("M").to_timestamp()

        records.append(
            {
                "year": year,
                "index_value": float(frame.loc[year, "index_value"]),
                "index_standardized": float(frame.loc[year, "index_standardized"]),
                "phase": str(frame.loc[year, "phase"]),
                "rainfall_anomaly": anomaly_by_year[year],
                "season_rainfall": result.season_rainfall,
                "relative_yield": result.relative_yield,
                "actual_yield": result.actual_yield,
                "water_stress_days": result.water_stress_days,
                "et_deficit_ratio": (
                    1.0 - result.season_et_actual / result.season_et_potential
                    if result.season_et_potential > 0
                    else 0.0
                ),
                "flowering_deficit": float(flowering["deficit_ratio"]),
                "spi3": _lookup(monthly["spi3"], flowering_month),
                "spei3": _lookup(monthly["spei3"], flowering_month),
            }
        )

    seasons = pd.DataFrame(records).set_index("year")
    return ObservedRun(
        seasons=seasons,
        weather=weather,
        monthly=monthly,
        site=site,
        crop=crop,
        assumption=assumption,
        driver=spec,
    )


def _lookup(series: pd.Series, timestamp: pd.Timestamp) -> float:
    """Read one month out of an index series, returning NaN if it is missing."""
    if timestamp in series.index:
        value = series.loc[timestamp]
        return float(value) if pd.notna(value) else float("nan")
    return float("nan")


def composite_by_phase(seasons: pd.DataFrame) -> pd.DataFrame:
    """Mean impact statistics grouped by climate phase, with sample sizes."""
    grouped = seasons.groupby("phase").agg(
        seasons=("actual_yield", "size"),
        mean_yield=("actual_yield", "mean"),
        median_yield=("actual_yield", "median"),
        yield_std=("actual_yield", "std"),
        mean_rainfall=("season_rainfall", "mean"),
        mean_stress_days=("water_stress_days", "mean"),
        mean_spi3=("spi3", "mean"),
    )

    baseline = seasons["actual_yield"].mean()
    grouped["yield_anomaly_percent"] = 100.0 * (grouped["mean_yield"] - baseline) / baseline

    order = [p for p in ("negative", "neutral", "positive") if p in grouped.index]
    return grouped.loc[order]


@dataclass
class ScenarioResult:
    """A forward run at a specified index value, against a neutral baseline."""

    members: pd.DataFrame          # ensemble under the scenario index
    baseline: pd.DataFrame         # same seeds, index held at zero
    index_value: float
    index_standardized: float
    phase: str
    driver: ClimateDriver
    analogues: pd.DataFrame        # observed seasons with a similar index

    @property
    def yield_loss_percent(self) -> float:
        """Mean yield change relative to the neutral baseline, in percent."""
        baseline_mean = self.baseline["actual_yield"].mean()
        if baseline_mean <= 0:
            return float("nan")
        return 100.0 * (self.members["actual_yield"].mean() - baseline_mean) / baseline_mean


def run_scenario(
    site_key: str,
    crop_key: str,
    index_value: float,
    driver: "str | ClimateDriver" = DEFAULT_DRIVER,
    observed: Optional[ObservedRun] = None,
    assumption: Optional[TeleconnectionAssumption] = None,
    members: int = 60,
    temperature_shift: float = 0.0,
    irrigation_mm_per_week: float = 0.0,
    n_analogues: int = 5,
    seed: int = 2026,
) -> ScenarioResult:
    """
    Run the impact model forward at a specified index value.

    This is what turns the practical from a historical exercise into a forecast.
    Given a seasonal index value, whether observed or predicted, it produces the
    distribution of harvests consistent with it, alongside the same ensemble run
    with the index set to zero so the climate signal can be separated from
    ordinary weather noise.

    The index is standardised against the observed record, so a scenario value
    only has meaning relative to the record the model was set up with. The
    paired seeds mean that member `i` of the scenario and member `i` of the
    baseline differ only in the rainfall anomaly applied to them.
    """
    spec = get_driver(driver)
    assumption = assumption or TeleconnectionAssumption.for_driver(spec)
    observed = observed or run_observed_record(
        site_key, crop_key, driver=spec, assumption=assumption
    )

    # Reference the scenario against the same record the phases were defined on,
    # so a scenario value is classified exactly as an observed season would be.
    record = observed.seasons["index_value"]
    anomaly = float(index_value - record.mean())
    standardized = anomaly / float(record.std(ddof=1))

    phase = "neutral"
    if anomaly >= spec.event_threshold:
        phase = "positive"
    elif anomaly <= -spec.event_threshold:
        phase = "negative"

    site = SITES[site_key]
    crop = CROPS[crop_key]
    rng = np.random.default_rng(seed)
    member_seeds = rng.integers(0, 2**31 - 1, members)

    def ensemble(index_sd: float) -> pd.DataFrame:
        # A fresh noise stream per ensemble, but the same weather seeds, so the
        # two ensembles are comparable member by member.
        noise_rng = np.random.default_rng(seed + 1)
        rows = []
        for member, member_seed in enumerate(member_seeds):
            anomaly = rainfall_anomaly_from_index(
                index_sd, site_key, assumption, driver=spec, rng=noise_rng
            )
            result, _ = run_single_season(
                site,
                crop,
                rainfall_anomaly=anomaly,
                temperature_shift=temperature_shift,
                irrigation_mm_per_week=irrigation_mm_per_week,
                seed=int(member_seed),
            )
            rows.append(
                {
                    "member": member,
                    "rainfall_anomaly": anomaly,
                    "season_rainfall": result.season_rainfall,
                    "actual_yield": result.actual_yield,
                    "relative_yield": result.relative_yield,
                    "water_stress_days": result.water_stress_days,
                }
            )
        return pd.DataFrame(rows)

    return ScenarioResult(
        members=ensemble(standardized),
        baseline=ensemble(0.0),
        index_value=float(index_value),
        index_standardized=standardized,
        phase=phase,
        driver=spec,
        analogues=analogue_seasons(observed, index_value, n=n_analogues),
    )


def analogue_seasons(
    observed: ObservedRun, index_value: float, n: int = 5
) -> pd.DataFrame:
    """
    The observed seasons whose index was closest to a given value.

    Analogues are how a forecaster with no model reasons about an approaching
    event, and they are a useful sanity check on the model: if the analogue
    seasons are the ones that are remembered as disasters, the model composite
    should reflect that.
    """
    seasons = observed.seasons
    distance = (seasons["index_value"] - index_value).abs()
    closest = seasons.loc[distance.nsmallest(min(n, len(seasons))).index]
    return closest.assign(
        index_difference=(closest["index_value"] - index_value)
    ).sort_values("index_value", ascending=False)


def sensitivity_sweep(
    site_key: str,
    crop_key: str,
    anomalies: np.ndarray,
    members: int = 20,
    temperature_shift: float = 0.0,
    irrigation_mm_per_week: float = 0.0,
    seed: int = 7,
) -> pd.DataFrame:
    """
    Yield response to seasonal rainfall anomaly, as an ensemble.

    Each anomaly is run `members` times with different weather realisations, which
    shows the students that a single deterministic run tells them very little. The
    spread at a given anomaly comes purely from rainfall timing, not from the total.
    """
    site = SITES[site_key]
    crop = CROPS[crop_key]
    rng = np.random.default_rng(seed)

    rows = []
    for anomaly in anomalies:
        for member in range(members):
            result, _ = run_single_season(
                site,
                crop,
                rainfall_anomaly=float(anomaly),
                temperature_shift=temperature_shift,
                irrigation_mm_per_week=irrigation_mm_per_week,
                seed=int(rng.integers(0, 2**31 - 1)),
            )
            rows.append(
                {
                    "rainfall_anomaly": float(anomaly),
                    "member": member,
                    "season_rainfall": result.season_rainfall,
                    "relative_yield": result.relative_yield,
                    "actual_yield": result.actual_yield,
                    "water_stress_days": result.water_stress_days,
                }
            )
    return pd.DataFrame(rows)


def _bias_sweep(
    site_key: str,
    crop_key: str,
    biases: np.ndarray,
    column: str,
    apply_bias,
    members: int,
    rainfall_anomaly: float,
    irrigation_mm_per_week: float,
    seed: int,
) -> pd.DataFrame:
    """
    Shared machinery for the driver-error sweeps.

    Rainfall is held fixed so that the temperature error is the only thing
    varying. Every member at every bias uses the same weather seed, so a
    difference between two biases is caused by the bias alone and not by
    resampling the rainfall. `apply_bias` turns one bias value into the keyword
    arguments that impose it.
    """
    site = SITES[site_key]
    crop = CROPS[crop_key]

    # Shared seeds across biases: the paired design removes sampling noise.
    member_seeds = np.random.default_rng(seed).integers(0, 2**31 - 1, members)

    rows = []
    for bias in biases:
        for member, member_seed in enumerate(member_seeds):
            result, weather = run_single_season(
                site,
                crop,
                rainfall_anomaly=rainfall_anomaly,
                irrigation_mm_per_week=irrigation_mm_per_week,
                seed=int(member_seed),
                **apply_bias(float(bias)),
            )
            rows.append(
                {
                    column: float(bias),
                    "member": member,
                    "actual_yield": result.actual_yield,
                    "relative_yield": result.relative_yield,
                    "et_potential": result.season_et_potential,
                    "water_stress_days": result.water_stress_days,
                    "mean_diurnal_range": float(
                        (weather["t_max"] - weather["t_min"]).mean()
                    ),
                }
            )
    return pd.DataFrame(rows)


def temperature_bias_sweep(
    site_key: str,
    crop_key: str,
    biases: np.ndarray,
    members: int = 20,
    rainfall_anomaly: float = 0.0,
    irrigation_mm_per_week: float = 0.0,
    seed: int = 13,
) -> pd.DataFrame:
    """
    Yield response to a uniform temperature offset in the driving weather.

    A uniform offset moves the daily maximum and minimum together, so it reaches
    ET0 only through the mean term in Hargreaves-Samani. It is the error a
    student would naively assume a biased weather model has, and it is not the
    error the AI model in `driver_error.py` actually makes.
    """
    return _bias_sweep(
        site_key, crop_key, biases,
        column="temperature_bias",
        apply_bias=lambda value: {"temperature_shift": value},
        members=members,
        rainfall_anomaly=rainfall_anomaly,
        irrigation_mm_per_week=irrigation_mm_per_week,
        seed=seed,
    )


def diurnal_range_sweep(
    site_key: str,
    crop_key: str,
    range_biases: np.ndarray,
    members: int = 20,
    rainfall_anomaly: float = 0.0,
    irrigation_mm_per_week: float = 0.0,
    temperature_shift: float = 0.0,
    seed: int = 17,
) -> pd.DataFrame:
    """
    Yield response to an error in the daily temperature *range*.

    This is the error the AI weather model actually makes: it is roughly right at
    dawn and far too cold in the early afternoon, so it damps the daily heating
    cycle without shifting the mean nearly as much. Hargreaves-Samani takes the
    square root of the range, so this route into ET0 is both distinct from a
    uniform offset and, for a given number of degrees, considerably stronger.
    """
    return _bias_sweep(
        site_key, crop_key, range_biases,
        column="diurnal_range_bias",
        apply_bias=lambda value: {
            "diurnal_range_shift": value,
            "temperature_shift": temperature_shift,
        },
        members=members,
        rainfall_anomaly=rainfall_anomaly,
        irrigation_mm_per_week=irrigation_mm_per_week,
        seed=seed,
    )


def available_options() -> Dict[str, Dict[str, str]]:
    """Human-readable site and crop menus for the dashboard."""
    return {
        "sites": {key: site.name for key, site in SITES.items()},
        "crops": {key: crop.name for key, crop in CROPS.items()},
    }

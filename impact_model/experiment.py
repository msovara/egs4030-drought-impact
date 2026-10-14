# -*- coding: utf-8 -*-
"""
Experiments: running the crop model on the historical record and on the
season ahead.

    run_one_season           one historical season in full daily detail
    run_historical           every season since 1979 with its ERA5 weather
    same_total_experiment    every historical rainfall sequence scaled to the
                             same seasonal total, to separate timing from amount
    run_cascade              the season ahead, adding one source of uncertainty
                             at a time

Seasons are labelled by planting year: the 2015 season is planted in November
2015 and harvested in 2016.
"""

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .climate import (
    TeleconnectionFit,
    fit_teleconnection,
    load_enso_index,
    rainy_season_label,
    rainy_season_totals,
)
from .config import (
    CASCADE_FLOWERING_KY,
    CASCADE_SOILS,
    DEFAULT_PLANTING,
    DEFAULT_SOIL,
    EL_NINO_THRESHOLD,
    FIRST_SEASON,
    LA_NINA_THRESHOLD,
    MAIZE,
    PLANTING_DATES,
    RAINY_SEASON_MONTHS,
    SOILS,
    Crop,
)
from .crop import SeasonResult, relative_yield_from_arrays, run_season
from .data import load_daily_weather
from .indices import standardized_precipitation_index
from .weather import scale_rainy_season

# The soil water balance starts this many days before planting, so that each
# season begins from a soil moisture state set by its own preceding weather.
SPINUP_DAYS = 120

# Planting follows the first good rains, so the profile is never bone dry at
# sowing. Capping the initial deficit stops every dry start showing spurious
# establishment stress.
MAX_INITIAL_DEPLETION_FRACTION = 0.50

# A day with less rain than this counts as dry when measuring dry spells.
DRY_DAY_MM = 1.0


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def planting_date(season: int, planting: str = DEFAULT_PLANTING) -> pd.Timestamp:
    month, day = PLANTING_DATES[planting]
    return pd.Timestamp(year=season, month=month, day=day)


def _initial_depletion(spinup_precip: np.ndarray, spinup_et0: np.ndarray, capacity_mm: float) -> float:
    """
    A rough estimate of how dry the root zone is at planting.

    A simple running balance over the spin-up period is enough: the aim is only
    that a dry spring leaves the soil drier at planting than a wet one.
    """
    balance = float(np.sum(spinup_precip) - 0.35 * np.sum(spinup_et0))
    deficit = 0.85 - balance / max(capacity_mm * 3.0, 1e-6)
    return float(np.clip(deficit, 0.05, MAX_INITIAL_DEPLETION_FRACTION))


def longest_dry_spell(precip: np.ndarray, threshold: float = DRY_DAY_MM) -> int:
    """The longest run of consecutive days with less than `threshold` mm."""
    longest = current = 0
    for value in precip:
        current = current + 1 if value < threshold else 0
        longest = max(longest, current)
    return longest


def _soil_and_crop(soil_key: str, crop: Optional[Crop]) -> Tuple:
    return SOILS[soil_key], (crop or MAIZE)


@lru_cache(maxsize=8)
def available_seasons(planting: str = DEFAULT_PLANTING, season_days: int = MAIZE.season_length) -> Tuple[int, ...]:
    """Seasons with complete weather from spin-up to harvest, from 1979 onwards."""
    weather = load_daily_weather()
    totals = rainy_season_totals()
    seasons = []
    for season in totals.index:
        start = planting_date(season, planting) - pd.Timedelta(days=SPINUP_DAYS)
        end = planting_date(season, planting) + pd.Timedelta(days=season_days - 1)
        if season >= FIRST_SEASON and start >= weather.index[0] and end <= weather.index[-1]:
            seasons.append(int(season))
    return tuple(seasons)


# ---------------------------------------------------------------------------
# One season, in detail
# ---------------------------------------------------------------------------

def season_weather(
    season: int,
    planting: str = DEFAULT_PLANTING,
    rain_factor: float = 1.0,
    season_days: int = MAIZE.season_length,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    The ERA5 weather for one season: the spin-up period and the growing season.

    `rain_factor` scales the rainfall of that season's rainy months (see
    `weather.scale_rainy_season`); 1 leaves it as observed.
    """
    weather = load_daily_weather()
    plant = planting_date(season, planting)
    window = weather.loc[plant - pd.Timedelta(days=SPINUP_DAYS): plant + pd.Timedelta(days=season_days + 30)]
    window = scale_rainy_season(window, rain_factor, season, RAINY_SEASON_MONTHS)
    spinup = window.loc[: plant - pd.Timedelta(days=1)]
    growing = window.loc[plant:]
    return spinup, growing


def run_one_season(
    season: int,
    soil_key: str = DEFAULT_SOIL,
    planting: str = DEFAULT_PLANTING,
    rain_factor: float = 1.0,
    crop: Optional[Crop] = None,
) -> Tuple[SeasonResult, pd.DataFrame]:
    """Run one historical season and return the result with its daily weather."""
    soil, crop = _soil_and_crop(soil_key, crop)
    spinup, growing = season_weather(season, planting, rain_factor, crop.season_length)
    capacity = soil.available_water_capacity * crop.rooting_depth_initial
    result = run_season(
        growing,
        crop=crop,
        soil=soil,
        initial_depletion_fraction=_initial_depletion(
            spinup["precip"].to_numpy(), spinup["et0"].to_numpy(), capacity
        ),
    )
    return result, growing.iloc[: crop.season_length]


# ---------------------------------------------------------------------------
# The historical record
# ---------------------------------------------------------------------------

def _flowering_window(crop: Crop) -> Tuple[int, int]:
    start = crop.stage_lengths["initial"] + crop.stage_lengths["development"]
    return start, start + crop.stage_lengths["mid"]


def run_historical(
    soil_key: str = DEFAULT_SOIL,
    planting: str = DEFAULT_PLANTING,
    crop: Optional[Crop] = None,
) -> pd.DataFrame:
    """
    Run every season since 1979 with its own ERA5 weather.

    One row per season, with the ENSO index, the rainfall, the modelled relative
    yield (fraction of the water-unlimited yield) and some descriptions of how
    the rain was distributed through the season.
    """
    soil, crop = _soil_and_crop(soil_key, crop)
    enso = load_enso_index()
    totals = rainy_season_totals()
    weather = load_daily_weather()

    monthly_precip = weather["precip"].resample("MS").sum()
    spi3 = standardized_precipitation_index(monthly_precip, scale=3)
    flower_start, flower_end = _flowering_window(crop)

    rows: List[Dict[str, float]] = []
    for season in available_seasons(planting, crop.season_length):
        if season not in enso.index:
            continue
        result, growing = run_one_season(season, soil_key, planting, crop=crop)
        precip = growing["precip"].to_numpy()
        flowering_end_month = (
            planting_date(season, planting) + pd.Timedelta(days=flower_end - 1)
        ).to_period("M").to_timestamp()
        rows.append(
            {
                "season": season,
                "relative_index": float(enso.loc[season, "relative"]),
                "traditional_index": float(enso.loc[season, "traditional"]),
                "phase": enso.loc[season, "phase"],
                "rainfall": float(totals.loc[season]),
                "crop_season_rainfall": result.season_rainfall,
                "flowering_rainfall": float(precip[flower_start:flower_end].sum()),
                "longest_dry_spell": longest_dry_spell(precip),
                "flowering_dry_spell": longest_dry_spell(precip[flower_start:flower_end]),
                "stress_days": result.water_stress_days,
                "mean_t_max": float(growing["t_max"].mean()),
                "relative_yield": result.relative_yield,
                "spi3_flowering": float(spi3.get(flowering_end_month, np.nan)),
            }
        )
    return pd.DataFrame(rows).set_index("season")


def same_total_experiment(
    total_mm: Optional[float] = None,
    soil_key: str = DEFAULT_SOIL,
    planting: str = DEFAULT_PLANTING,
    crop: Optional[Crop] = None,
) -> pd.DataFrame:
    """
    Give every historical season the same rainy-season total, keeping its timing.

    Each season's daily rainfall is multiplied by (total_mm / its own total), so
    every season ends up with the same amount of rain but keeps its own pattern
    of wet days and dry spells. Any spread in yield is then down to timing. By
    default the total is the median of the historical record.
    """
    soil, crop = _soil_and_crop(soil_key, crop)
    totals = rainy_season_totals()
    total_mm = float(totals.median()) if total_mm is None else float(total_mm)
    flower_start, flower_end = _flowering_window(crop)

    rows = []
    for season in available_seasons(planting, crop.season_length):
        factor = total_mm / float(totals.loc[season])
        result, growing = run_one_season(season, soil_key, planting, rain_factor=factor, crop=crop)
        precip = growing["precip"].to_numpy()
        rows.append(
            {
                "season": season,
                "original_rainfall": float(totals.loc[season]),
                "scale_factor": factor,
                "flowering_rainfall": float(precip[flower_start:flower_end].sum()),
                "longest_dry_spell": longest_dry_spell(precip),
                "flowering_dry_spell": longest_dry_spell(precip[flower_start:flower_end]),
                "relative_yield": result.relative_yield,
            }
        )
    frame = pd.DataFrame(rows).set_index("season")
    frame.attrs["total_mm"] = total_mm
    return frame


# ---------------------------------------------------------------------------
# The season ahead: the uncertainty cascade
# ---------------------------------------------------------------------------

CASCADE_STAGES: List[Tuple[str, str]] = [
    ("driver", "1. ENSO forecast range"),
    ("regional", "2. + Mopani rainfall response"),
    ("weather", "3. + day-to-day weather"),
    ("response", "4. + soil and crop response"),
]


@dataclass
class _SeasonArrays:
    """Pre-extracted daily arrays for one season, so the cascade runs quickly."""

    precip: np.ndarray
    et0: np.ndarray
    rainy_mask: np.ndarray
    total: float


def _season_arrays(planting: str, season_days: int) -> Dict[int, _SeasonArrays]:
    weather = load_daily_weather()
    totals = rainy_season_totals()
    arrays = {}
    for season in available_seasons(planting, season_days):
        plant = planting_date(season, planting)
        window = weather.loc[plant - pd.Timedelta(days=SPINUP_DAYS): plant + pd.Timedelta(days=season_days - 1)]
        label = rainy_season_label(window.index)
        mask = np.isin(window.index.month, RAINY_SEASON_MONTHS) & (label == season)
        arrays[season] = _SeasonArrays(
            precip=window["precip"].to_numpy(dtype=float),
            et0=window["et0"].to_numpy(dtype=float),
            rainy_mask=mask,
            total=float(totals.loc[season]),
        )
    return arrays


def _choose_donor(target: float, arrays: Dict[int, _SeasonArrays], rng: np.random.Generator) -> int:
    """
    A historical season to borrow the day-to-day rainfall sequence from.

    Chosen at random among seasons whose total is within a factor of 1.5 of the
    target, so that the rescaling stays modest. If fewer than five qualify, the
    five closest are used instead.
    """
    seasons = np.array(list(arrays))
    ratio = np.abs(np.log(np.array([arrays[s].total for s in seasons]) / target))
    pool = seasons[ratio <= np.log(1.5)]
    if len(pool) < 5:
        pool = seasons[np.argsort(ratio)[:5]]
    return int(rng.choice(pool))


def _yield_for(season_arrays: _SeasonArrays, target: float, crop: Crop, soil) -> float:
    factor = target / season_arrays.total
    precip = np.where(season_arrays.rainy_mask, season_arrays.precip * factor, season_arrays.precip)
    capacity = soil.available_water_capacity * crop.rooting_depth_initial
    initial = _initial_depletion(precip[:SPINUP_DAYS], season_arrays.et0[:SPINUP_DAYS], capacity)
    return relative_yield_from_arrays(
        precip[SPINUP_DAYS:], season_arrays.et0[SPINUP_DAYS:], crop, soil, initial
    )


@dataclass
class CascadeResult:
    """
    Everything the season-ahead experiment produces.

    `members` has one row per ensemble member and stage. `neutral` is the full
    cascade (all four sources of uncertainty) run with a neutral ENSO index,
    and `historical` is the model run on the actual seasons since 1979. The
    poor-season threshold is the lower tercile of the historical yields, so in
    the historical record one season in three is poor by definition.
    """

    index_range: Tuple[float, float]
    members: pd.DataFrame
    neutral: pd.DataFrame
    historical: pd.DataFrame
    fit: TeleconnectionFit
    poor_threshold: float
    reference_season: int
    settings: Dict[str, object] = field(default_factory=dict)

    def stage_summary(self) -> pd.DataFrame:
        """Spread and probability of a poor season at each stage, plus references."""
        rows = []
        groups = [(label, self.members[self.members["stage"] == key]) for key, label in CASCADE_STAGES]
        groups.append(("Neutral ENSO, all uncertainty", self.neutral))
        groups.append(("Historical seasons, 1979 on", self.historical))
        for label, group in groups:
            values = group["relative_yield"].to_numpy()
            rows.append(
                {
                    "case": label,
                    "members": len(values),
                    "p10": float(np.percentile(values, 10)),
                    "median": float(np.median(values)),
                    "p90": float(np.percentile(values, 90)),
                    "spread_p10_p90": float(np.percentile(values, 90) - np.percentile(values, 10)),
                    "prob_poor": float(np.mean(values < self.poor_threshold)),
                }
            )
        return pd.DataFrame(rows).set_index("case")

    def historical_in_range(self) -> pd.DataFrame:
        """Past seasons whose index fell inside the forecast range."""
        low, high = self.index_range
        h = self.historical
        return h[(h["relative_index"] >= low) & (h["relative_index"] <= high)]


def run_cascade(
    index_range: Tuple[float, float],
    members: int = 300,
    soil_key: str = DEFAULT_SOIL,
    planting: str = DEFAULT_PLANTING,
    crop: Optional[Crop] = None,
    seed: int = 2026,
) -> CascadeResult:
    """
    Run the season ahead, adding one source of uncertainty at a time.

    Stage 1, ENSO forecast range: the DJF index is drawn uniformly from
        `index_range`, rainfall is the value on the fitted line, and every member
        uses the same "typical" historical rainfall sequence, rescaled.
    Stage 2, + Mopani rainfall response: as stage 1, but the line itself is
        uncertain (bootstrap refits) and the scatter of real seasons about the
        line is added.
    Stage 3, + day-to-day weather: as stage 2, but each member borrows its daily
        sequence from a different historical season with a similar total.
    Stage 4, + soil and crop response: as stage 3, but each member also draws a
        soil type and a yield response at flowering from plausible ranges.

    The default soil and crop are used in stages 1 to 3.
    """
    low, high = sorted(float(v) for v in index_range)
    crop = crop or MAIZE
    default_soil = SOILS[soil_key]
    fit = fit_teleconnection()
    arrays = _season_arrays(planting, crop.season_length)
    historical = run_historical(soil_key, planting, crop)

    # The "typical" sequence for stages 1 and 2: the season closest to the median total.
    totals = pd.Series({s: a.total for s, a in arrays.items()})
    reference = int((totals - totals.median()).abs().idxmin())

    soil_options = [SOILS[k] for k in CASCADE_SOILS]
    crop_options = [crop.with_flowering_ky(ky) for ky in CASCADE_FLOWERING_KY]

    def one_stage(stage: str, lo: float, hi: float, rng: np.random.Generator) -> List[Dict]:
        rows = []
        for member in range(members):
            index_value = rng.uniform(lo, hi)
            if stage == "driver":
                target = float(fit.predict(index_value))
            else:
                target = fit.sample(index_value, rng)
            donor = reference if stage in ("driver", "regional") else _choose_donor(target, arrays, rng)
            soil, member_crop = default_soil, crop
            if stage == "response":
                k_soil = int(rng.integers(len(soil_options)))
                k_crop = int(rng.integers(len(crop_options)))
                soil, member_crop = soil_options[k_soil], crop_options[k_crop]
            rows.append(
                {
                    "stage": stage,
                    "member": member,
                    "index": index_value,
                    "rainfall": target,
                    "sequence_from": donor,
                    "soil": soil.name,
                    "flowering_ky": member_crop.ky_by_stage["mid"],
                    "relative_yield": _yield_for(arrays[donor], target, member_crop, soil),
                }
            )
        return rows

    rng = np.random.default_rng(seed)
    rows: List[Dict] = []
    for stage, _ in CASCADE_STAGES:
        rows.extend(one_stage(stage, low, high, rng))
    neutral_rows = one_stage("response", LA_NINA_THRESHOLD, EL_NINO_THRESHOLD, np.random.default_rng(seed + 1))

    return CascadeResult(
        index_range=(low, high),
        members=pd.DataFrame(rows),
        neutral=pd.DataFrame(neutral_rows),
        historical=historical,
        fit=fit,
        poor_threshold=float(historical["relative_yield"].quantile(1 / 3)),
        reference_season=reference,
        settings={"members": members, "soil": soil_key, "planting": planting, "seed": seed},
    )

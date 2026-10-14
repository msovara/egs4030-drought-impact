# -*- coding: utf-8 -*-
"""
The impact model itself: a daily root-zone water balance driving a yield response.

Two components, both standard in operational agricultural drought assessment:

1. FAO-56 single crop coefficient water balance (Allen et al., 1998). Tracks root
   zone depletion and reduces actual transpiration below potential once depletion
   passes the readily available water threshold.

2. FAO-33 yield response (Doorenbos and Kassam, 1979). Converts the seasonal
   water deficit into a yield loss, weighted by growth stage through the yield
   response factor Ky.

In plain terms: the root zone is treated as a bucket. Rain fills it, the crop
empties it, and once it falls below a threshold the crop can no longer draw
water fast enough and grows less. How much yield that costs depends on when in
the season it happens.

The whole model is around 200 lines and runs a season in a few milliseconds, so
it is practical to run thousands of seasons on a laptop.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .config import STAGE_ORDER, Crop, Soil


@dataclass
class SeasonResult:
    """Everything the dashboard and the student task need from one season."""

    daily: pd.DataFrame
    stage_summary: pd.DataFrame
    relative_yield: float
    actual_yield: float
    potential_yield: float
    season_rainfall: float
    season_et_actual: float
    season_et_potential: float
    water_stress_days: int
    metadata: Dict[str, float] = field(default_factory=dict)

    @property
    def yield_loss_fraction(self) -> float:
        return 1.0 - self.relative_yield


def _stage_for_each_day(crop: Crop) -> List[str]:
    """Map each day of the season onto its FAO-56 growth stage."""
    stages: List[str] = []
    for stage in STAGE_ORDER:
        stages.extend([stage] * crop.stage_lengths[stage])
    return stages


def crop_coefficient_curve(crop: Crop) -> np.ndarray:
    """
    Daily Kc over the season (FAO-56 figure 25).

    Kc is flat at Kc_ini through establishment, rises linearly through the
    development stage, is flat at Kc_mid through flowering and grain fill, then
    falls linearly to Kc_end as the crop senesces.
    """
    lengths = crop.stage_lengths
    initial = np.full(lengths["initial"], crop.kc_initial)
    development = np.linspace(
        crop.kc_initial, crop.kc_mid, lengths["development"], endpoint=False
    )
    mid = np.full(lengths["mid"], crop.kc_mid)
    late = np.linspace(crop.kc_mid, crop.kc_end, lengths["late"])
    return np.concatenate([initial, development, mid, late])


def rooting_depth_curve(crop: Crop) -> np.ndarray:
    """Root depth in metres, growing linearly until the end of the mid stage."""
    lengths = crop.stage_lengths
    grow_days = lengths["initial"] + lengths["development"] + lengths["mid"]
    growing = np.linspace(
        crop.rooting_depth_initial, crop.rooting_depth_max, grow_days
    )
    mature = np.full(lengths["late"], crop.rooting_depth_max)
    return np.concatenate([growing, mature])


def scs_runoff(precip: float, curve_number: float) -> float:
    """
    Surface runoff by the SCS curve number method (USDA-SCS, 1972).

    Rainfall that runs off never enters the root zone, so ignoring it would make
    a dry season look wetter than it is on the heavier soils.
    """
    potential_retention = 25400.0 / curve_number - 254.0
    initial_abstraction = 0.2 * potential_retention
    if precip <= initial_abstraction:
        return 0.0
    excess = precip - initial_abstraction
    return excess * excess / (precip + 0.8 * potential_retention)


def _simulate(
    precip: np.ndarray,
    et0: np.ndarray,
    crop: Crop,
    soil: Soil,
    initial_depletion_fraction: float,
    new_soil_relative_depletion: float,
) -> Dict[str, np.ndarray]:
    """The daily water balance loop, on plain arrays."""
    season_days = crop.season_length
    kc = crop_coefficient_curve(crop)
    root_depth = rooting_depth_curve(crop)

    total_available_water = soil.available_water_capacity * root_depth
    readily_available_water = crop.depletion_fraction * total_available_water

    depletion = np.zeros(season_days)
    et_actual = np.zeros(season_days)
    et_potential = np.zeros(season_days)
    stress_coefficient = np.zeros(season_days)
    runoff = np.zeros(season_days)
    deep_percolation = np.zeros(season_days)
    root_zone_gain = np.zeros(season_days)

    current_depletion = initial_depletion_fraction * total_available_water[0]
    previous_taw = total_available_water[0]

    for day in range(season_days):
        taw = total_available_water[day]
        raw = readily_available_water[day]

        # Root growth brings soil that already holds water into the balance. That
        # is a genuine input, so it is tracked explicitly rather than being left
        # to appear as a residual.
        capacity_added = max(taw - previous_taw, 0.0)
        root_zone_gain[day] = capacity_added * (1.0 - new_soil_relative_depletion)
        current_depletion += capacity_added * new_soil_relative_depletion
        previous_taw = taw

        runoff[day] = scs_runoff(precip[day], soil.curve_number)
        infiltration = precip[day] - runoff[day]

        etc = kc[day] * et0[day]
        et_potential[day] = etc

        # FAO-56 eq. 84: transpiration falls off linearly once depletion passes RAW.
        if current_depletion > raw and taw > raw:
            ks = max((taw - current_depletion) / (taw - raw), 0.0)
        else:
            ks = 1.0
        stress_coefficient[day] = ks

        # The crop cannot transpire water that is not in the profile.
        extractable = max(taw - current_depletion + infiltration, 0.0)
        et_actual[day] = min(ks * etc, extractable)

        current_depletion = current_depletion - infiltration + et_actual[day]

        # Water above field capacity drains out of the root zone within a day.
        if current_depletion < 0.0:
            deep_percolation[day] = -current_depletion
            current_depletion = 0.0

        depletion[day] = current_depletion

    return {
        "precip": precip,
        "et0": et0,
        "kc": kc,
        "et_potential": et_potential,
        "et_actual": et_actual,
        "stress_coefficient": stress_coefficient,
        "depletion": depletion,
        "total_available_water": total_available_water,
        "readily_available_water": readily_available_water,
        "root_depth": root_depth,
        "runoff": runoff,
        "deep_percolation": deep_percolation,
        "root_zone_gain": root_zone_gain,
    }


def _stage_bounds(crop: Crop) -> List[Tuple[str, int, int]]:
    bounds, start = [], 0
    for stage in STAGE_ORDER:
        end = start + crop.stage_lengths[stage]
        bounds.append((stage, start, end))
        start = end
    return bounds


def _check_weather(weather: pd.DataFrame, crop: Crop) -> None:
    if len(weather) < crop.season_length:
        raise ValueError(
            f"Weather series has {len(weather)} days but the season needs "
            f"{crop.season_length}."
        )


def relative_yield_from_arrays(
    precip: np.ndarray,
    et0: np.ndarray,
    crop: Crop,
    soil: Soil,
    initial_depletion_fraction: float = 0.5,
    new_soil_relative_depletion: float = 0.0,
) -> float:
    """
    The relative yield of one season from daily arrays starting at planting.

    Gives exactly the same answer as `run_season(...).relative_yield`, without
    building the daily tables. Used by experiments that run thousands of seasons.
    """
    days = crop.season_length
    if len(precip) < days or len(et0) < days:
        raise ValueError(f"Need {days} days of weather, got {min(len(precip), len(et0))}.")
    arrays = _simulate(
        np.asarray(precip, dtype=float)[:days],
        np.asarray(et0, dtype=float)[:days],
        crop, soil, initial_depletion_fraction, new_soil_relative_depletion,
    )
    relative_yield = 1.0
    for stage, start, end in _stage_bounds(crop):
        etc_sum = arrays["et_potential"][start:end].sum()
        eta_sum = arrays["et_actual"][start:end].sum()
        deficit_ratio = 1.0 - eta_sum / etc_sum if etc_sum > 0 else 0.0
        relative_yield *= max(1.0 - crop.ky_by_stage[stage] * deficit_ratio, 0.0)
    return float(np.clip(relative_yield, 0.0, 1.0))


def run_season(
    weather: pd.DataFrame,
    crop: Crop,
    soil: Soil,
    initial_depletion_fraction: float = 0.5,
    new_soil_relative_depletion: float = 0.0,
) -> SeasonResult:
    """
    Run the water balance and yield model for one growing season.

    `weather` must cover at least `crop.season_length` days from planting and
    carry `precip` and `et0` columns, in mm/day.

    `initial_depletion_fraction` is how dry the root zone is at planting, from 0
    (full) to 1 (at wilting point).

    `new_soil_relative_depletion` sets how wet the soil is that the roots reach as
    they grow downwards, from 0 for field capacity to 1 for wilting point. The
    default of 0 is the standard FAO-56 simplification and is optimistic for a
    dryland profile, which makes it a reasonable thing to vary.
    """
    _check_weather(weather, crop)
    season_days = crop.season_length
    weather = weather.iloc[:season_days]
    arrays = _simulate(
        weather["precip"].to_numpy(dtype=float),
        weather["et0"].to_numpy(dtype=float),
        crop, soil, initial_depletion_fraction, new_soil_relative_depletion,
    )
    total_available_water = arrays["total_available_water"]
    stages = _stage_for_each_day(crop)

    daily = pd.DataFrame(arrays, index=weather.index)
    daily["soil_water"] = total_available_water - daily["depletion"]
    daily["stage"] = stages
    daily["day_of_season"] = np.arange(1, season_days + 1)

    stage_rows = []
    relative_yield = 1.0
    for stage in STAGE_ORDER:
        mask = daily["stage"] == stage
        etc_sum = float(daily.loc[mask, "et_potential"].sum())
        eta_sum = float(daily.loc[mask, "et_actual"].sum())
        deficit_ratio = 1.0 - (eta_sum / etc_sum) if etc_sum > 0 else 0.0
        ky = crop.ky_by_stage[stage]

        # FAO-33: fractional yield loss in a stage is Ky times the relative deficit.
        stage_yield_factor = max(1.0 - ky * deficit_ratio, 0.0)
        relative_yield *= stage_yield_factor

        stage_rows.append(
            {
                "stage": stage,
                "days": int(mask.sum()),
                "rainfall": float(daily.loc[mask, "precip"].sum()),
                "et_potential": etc_sum,
                "et_actual": eta_sum,
                "deficit_ratio": deficit_ratio,
                "ky": ky,
                "stage_yield_factor": stage_yield_factor,
                "mean_stress_coefficient": float(daily.loc[mask, "stress_coefficient"].mean()),
                "stress_days": int((daily.loc[mask, "stress_coefficient"] < 0.99).sum()),
            }
        )

    stage_summary = pd.DataFrame(stage_rows)
    relative_yield = float(np.clip(relative_yield, 0.0, 1.0))

    return SeasonResult(
        daily=daily,
        stage_summary=stage_summary,
        relative_yield=relative_yield,
        actual_yield=relative_yield * crop.potential_yield,
        potential_yield=crop.potential_yield,
        season_rainfall=float(daily["precip"].sum()),
        season_et_actual=float(daily["et_actual"].sum()),
        season_et_potential=float(daily["et_potential"].sum()),
        water_stress_days=int((daily["stress_coefficient"] < 0.99).sum()),
        metadata={
            "crop": crop.name,
            "soil": soil.name,
            "season_runoff": float(daily["runoff"].sum()),
            "season_percolation": float(daily["deep_percolation"].sum()),
            "season_root_zone_gain": float(daily["root_zone_gain"].sum()),
            # Storage before the first day's fluxes, needed to close the balance.
            "initial_soil_water": float(
                total_available_water[0] * (1.0 - initial_depletion_fraction)
            ),
        },
    )

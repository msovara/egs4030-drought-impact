# -*- coding: utf-8 -*-
"""
Daily weather: reference evapotranspiration, and rescaling a season's rainfall.

The daily rainfall and temperature themselves come from ERA5 (see `data.py`).
This module turns temperature into atmospheric water demand, and provides the
one manipulation the experiments need: taking a real season's day-to-day
rainfall sequence and scaling it to a different seasonal total.
"""

from typing import Tuple

import numpy as np
import pandas as pd

SOLAR_CONSTANT = 0.0820          # MJ m-2 min-1
MJ_TO_MM = 0.408                 # latent heat of vaporisation conversion at 20 degC


def extraterrestrial_radiation(day_of_year: np.ndarray, latitude: float) -> np.ndarray:
    """Top-of-atmosphere radiation Ra in MJ m-2 day-1 (FAO-56 eq. 21)."""
    phi = np.deg2rad(latitude)
    inverse_distance = 1.0 + 0.033 * np.cos(2.0 * np.pi * day_of_year / 365.0)
    declination = 0.409 * np.sin(2.0 * np.pi * day_of_year / 365.0 - 1.39)

    # Clipped because |tan(phi) tan(delta)| exceeds 1 inside the polar circles.
    cos_sunset = np.clip(-np.tan(phi) * np.tan(declination), -1.0, 1.0)
    sunset_angle = np.arccos(cos_sunset)

    return (
        (24.0 * 60.0 / np.pi)
        * SOLAR_CONSTANT
        * inverse_distance
        * (
            sunset_angle * np.sin(phi) * np.sin(declination)
            + np.cos(phi) * np.cos(declination) * np.sin(sunset_angle)
        )
    )


def reference_et_hargreaves(
    t_min: np.ndarray,
    t_max: np.ndarray,
    day_of_year: np.ndarray,
    latitude: float,
) -> np.ndarray:
    """
    Reference crop evapotranspiration ET0 in mm/day (Hargreaves and Samani, 1985).

    Hargreaves is used in preference to Penman-Monteith because it needs only
    temperature and latitude, so students can run it for any location without
    hunting for humidity, wind and radiation.
    """
    t_mean = 0.5 * (t_min + t_max)
    temp_range = np.maximum(t_max - t_min, 0.0)
    radiation_mm = MJ_TO_MM * extraterrestrial_radiation(day_of_year, latitude)
    et0 = 0.0023 * radiation_mm * (t_mean + 17.8) * np.sqrt(temp_range)
    return np.maximum(et0, 0.0)


def scale_rainy_season(
    weather: pd.DataFrame,
    factor: float,
    season_year: int,
    months: Tuple[int, ...],
) -> pd.DataFrame:
    """
    Multiply the daily rainfall of one rainy season by `factor`.

    Only days in `months` of the season labelled `season_year` are changed (for
    a November to March season, November 2015 to March 2016 for the 2015
    season). Wet and dry days stay where they were, so the timing of the rain
    and the dry spells is kept and only the amounts change.

    Note what this cannot do: it cannot turn a dry day into a wet one. Scaling a
    wet season down to a dry total gives many small rain events rather than
    long dry spells, which is why the experiments only borrow sequences from
    seasons with a broadly similar total.
    """
    if factor == 1.0:
        return weather
    dates = weather.index
    label = np.where(dates.month >= months[0], dates.year, dates.year - 1)
    mask = np.isin(dates.month, months) & (label == season_year)
    scaled = weather.copy()
    scaled.loc[mask, "precip"] = scaled.loc[mask, "precip"] * max(float(factor), 0.0)
    return scaled

# -*- coding: utf-8 -*-
"""
Daily weather for a site: reference evapotranspiration and a stochastic generator.

The generator produces daily rainfall and temperature whose seasonal statistics
match a site's climatology, scaled by a seasonal rainfall anomaly. This lets the
class drive the impact model with a wet or dry season without needing a gridded
dataset on the lecture-room machine. See `era5.py` for the observed-data path.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Site

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


@dataclass
class WeatherGeneratorParams:
    """Controls on the stochastic generator, exposed so students can experiment."""

    rainfall_anomaly: float = 0.0     # fractional change in seasonal total, -1..+1
    temperature_shift: float = 0.0    # degC added to the whole series
    # degC added to the daily maximum minus minimum, leaving the mean unchanged.
    # Negative values damp the daily heating cycle, which is the error signature
    # of the AI weather model in driver_error.py. It reaches ET0 through the
    # square-root range term in Hargreaves-Samani, not through the mean.
    diurnal_range_shift: float = 0.0
    wet_day_gamma_shape: float = 0.7  # gamma shape for wet-day rainfall amounts
    seed: int | None = None


def _monthly_rainfall_targets(site: Site) -> np.ndarray:
    """Long-term mean rainfall per calendar month (mm)."""
    fractions = np.asarray(site.rainfall_seasonality, dtype=float)
    fractions = fractions / fractions.sum()
    return site.annual_rainfall * fractions


def _daily_anomaly(
    dates: pd.DatetimeIndex,
    rainfall_anomaly: float | pd.Series,
) -> np.ndarray:
    """Broadcast a scalar anomaly, or align a per-date anomaly series, to the dates."""
    if isinstance(rainfall_anomaly, pd.Series):
        aligned = rainfall_anomaly.reindex(dates).ffill().bfill()
        return aligned.to_numpy(dtype=float)
    return np.full(len(dates), float(rainfall_anomaly))


def generate_weather(
    site: Site,
    start: pd.Timestamp,
    days: int,
    params: WeatherGeneratorParams,
    rainfall_anomaly: float | pd.Series | None = None,
) -> pd.DataFrame:
    """
    Generate a daily weather series for `site`.

    Rainfall occurrence uses a two-state Markov chain whose wet-day probability
    follows the site's seasonal cycle; amounts on wet days are gamma distributed.
    A drier season is produced by reducing both the wet-day frequency and the mean
    amount, which is closer to observed behaviour than scaling amounts alone.

    `rainfall_anomaly` overrides `params.rainfall_anomaly` and may be a Series
    indexed by date, which is how a multi-year run applies a different anomaly to
    each growing season within one continuous climate record.

    Returns a frame indexed by date with columns: precip, t_min, t_max, t_mean, et0.
    """
    rng = np.random.default_rng(params.seed)
    dates = pd.date_range(start=start, periods=days, freq="D")
    day_of_year = dates.dayofyear.to_numpy()
    month_index = dates.month.to_numpy() - 1

    if rainfall_anomaly is None:
        rainfall_anomaly = params.rainfall_anomaly
    anomaly = _daily_anomaly(dates, rainfall_anomaly)

    baseline_totals = _monthly_rainfall_targets(site)
    days_in_month = np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])

    # Split the anomaly between wet-day frequency and wet-day intensity. The square
    # root gives each roughly half the response, which matches the observed
    # behaviour of southern African rainfall better than scaling amounts alone.
    baseline_wet_fraction = np.clip(
        0.42 * baseline_totals / np.maximum(baseline_totals.max(), 1e-6), 0.02, 0.55
    )
    scale_factor = np.sqrt(np.maximum(1.0 + anomaly, 0.02))
    wet_fraction = np.clip(baseline_wet_fraction[month_index] * scale_factor, 0.01, 0.85)

    monthly_totals = baseline_totals[month_index] * (1.0 + anomaly)
    expected_wet_days = wet_fraction * days_in_month[month_index]
    mean_wet_amount = np.maximum(monthly_totals, 0.0) / np.maximum(expected_wet_days, 1e-6)

    # Persistence: wet days cluster, so P(wet|wet) exceeds the unconditional rate.
    p_wet_given_dry = np.clip(wet_fraction * 0.72, 0.005, 0.9)
    p_wet_given_wet = np.clip(wet_fraction * 0.72 + 0.34, 0.01, 0.95)

    # Drawn up front so the Markov loop stays a cheap comparison per day.
    uniform_draws = rng.random(days)
    gamma_draws = rng.gamma(params.wet_day_gamma_shape, 1.0, days)

    precip = np.zeros(days)
    previous_wet = False
    for i in range(days):
        threshold = p_wet_given_wet[i] if previous_wet else p_wet_given_dry[i]
        is_wet = uniform_draws[i] < threshold
        if is_wet:
            precip[i] = gamma_draws[i] * mean_wet_amount[i] / params.wet_day_gamma_shape
        previous_wet = is_wet

    # Temperature: annual harmonic plus AR(1) noise, warmer and more variable when dry.
    phase = 2.0 * np.pi * (day_of_year - 15) / 365.25
    hemisphere_sign = -1.0 if site.latitude < 0 else 1.0
    seasonal_mean = site.temp_mean_annual + hemisphere_sign * site.temp_amplitude * np.cos(phase)

    innovations = rng.normal(0.0, 1.6, days)
    noise = np.zeros(days)
    for i in range(1, days):
        noise[i] = 0.72 * noise[i - 1] + innovations[i]

    # Dry seasons are hotter: less soil moisture means more sensible heating.
    drought_warming = -2.0 * np.minimum(anomaly, 0.0)
    t_mean = seasonal_mean + noise + params.temperature_shift + drought_warming

    # Wet days are cooler and have a compressed diurnal range.
    wet_mask = precip > 1.0
    t_mean = t_mean - 1.5 * wet_mask
    diurnal = site.diurnal_range * np.where(wet_mask, 0.65, 1.0)
    diurnal = diurnal + rng.normal(0.0, 1.0, days)
    # Applied after the noise so that a bias is a bias rather than a rescaling,
    # and floored so a large negative shift cannot invert the daily cycle.
    diurnal = np.maximum(diurnal + params.diurnal_range_shift, 1.0)

    t_min = t_mean - 0.5 * diurnal
    t_max = t_mean + 0.5 * diurnal

    et0 = reference_et_hargreaves(t_min, t_max, day_of_year, site.latitude)

    return pd.DataFrame(
        {
            "precip": precip,
            "t_min": t_min,
            "t_max": t_max,
            "t_mean": t_mean,
            "et0": et0,
        },
        index=dates,
    )

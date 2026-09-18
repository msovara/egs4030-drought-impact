# -*- coding: utf-8 -*-
"""
Meteorological drought indices: SPI and SPEI.

These are the indices the students will already have met in the climate half of
the module. Computing them here lets the lecture make its central point directly:
a drought index tells you the climate anomaly, but not the impact. Two seasons
with the same SPI can produce very different yields depending on when in the
growth cycle the deficit falls.
"""

import numpy as np
import pandas as pd
from scipy import stats


def _fit_and_transform(values: np.ndarray, distribution: str) -> np.ndarray:
    """Fit a distribution to one calendar month's values and map to a z-score."""
    finite = values[np.isfinite(values)]
    if finite.size < 8:
        return np.full(values.shape, np.nan)

    if distribution == "gamma":
        # Rainfall records contain exact zeros, which the gamma cannot represent.
        # The standard treatment mixes a point mass at zero with the fitted gamma.
        zero_fraction = float((finite <= 0).sum()) / finite.size
        positive = finite[finite > 0]
        if positive.size < 8:
            return np.full(values.shape, np.nan)
        shape, _, scale = stats.gamma.fit(positive, floc=0)
        cdf = np.where(
            values > 0,
            zero_fraction + (1.0 - zero_fraction) * stats.gamma.cdf(values, shape, loc=0, scale=scale),
            zero_fraction / 2.0,
        )
    elif distribution == "fisk":
        # SPEI uses a log-logistic on P - PET, which can legitimately be negative.
        shape, loc, scale = stats.fisk.fit(finite)
        cdf = stats.fisk.cdf(values, shape, loc=loc, scale=scale)
    else:
        raise ValueError(f"Unsupported distribution: {distribution}")

    # Keep the normal quantile finite at the tails of short records.
    cdf = np.clip(cdf, 1e-6, 1.0 - 1e-6)
    result = stats.norm.ppf(cdf)
    result[~np.isfinite(values)] = np.nan
    return result


def _standardize_by_month(accumulated: pd.Series, distribution: str) -> pd.Series:
    output = pd.Series(np.nan, index=accumulated.index, dtype=float)
    for month in range(1, 13):
        mask = accumulated.index.month == month
        if not mask.any():
            continue
        output.loc[mask] = _fit_and_transform(accumulated.loc[mask].to_numpy(float), distribution)
    return output


def standardized_precipitation_index(monthly_precip: pd.Series, scale: int = 3) -> pd.Series:
    """
    SPI at the given accumulation scale in months (McKee et al., 1993).

    `monthly_precip` must be a monthly-frequency series indexed by date. A gamma
    distribution is fitted separately for each calendar month so that the index
    is comparable across the seasonal cycle.
    """
    accumulated = monthly_precip.rolling(scale, min_periods=scale).sum()
    return _standardize_by_month(accumulated, "gamma").rename(f"SPI{scale}")


def standardized_precipitation_evapotranspiration_index(
    monthly_precip: pd.Series,
    monthly_pet: pd.Series,
    scale: int = 3,
) -> pd.Series:
    """
    SPEI at the given accumulation scale (Vicente-Serrano et al., 2010).

    SPEI standardises the climatic water balance P - PET rather than rainfall
    alone, so it responds to the warming-driven component of drought that SPI
    is blind to. That contrast is worth showing explicitly in the lecture.
    """
    water_balance = (monthly_precip - monthly_pet).rolling(scale, min_periods=scale).sum()
    return _standardize_by_month(water_balance, "fisk").rename(f"SPEI{scale}")


def classify_drought(index_value: float) -> str:
    """Map an SPI or SPEI value onto the standard severity classes."""
    if not np.isfinite(index_value):
        return "No data"
    if index_value <= -2.0:
        return "Extreme drought"
    if index_value <= -1.5:
        return "Severe drought"
    if index_value <= -1.0:
        return "Moderate drought"
    if index_value < -0.5:
        return "Mild drought"
    if index_value <= 0.5:
        return "Near normal"
    if index_value <= 1.5:
        return "Moderately wet"
    return "Very wet"


def monthly_aggregate(daily: pd.DataFrame) -> pd.DataFrame:
    """Collapse a daily weather frame to the monthly totals the indices need."""
    return pd.DataFrame(
        {
            "precip": daily["precip"].resample("MS").sum(),
            "pet": daily["et0"].resample("MS").sum(),
            "t_mean": daily["t_mean"].resample("MS").mean(),
        }
    )

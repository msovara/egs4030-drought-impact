# -*- coding: utf-8 -*-
"""
The climate driver: ENSO, and how it shows up in Mopani rainfall.

Three steps, each kept short enough to read in one sitting:

1. The relative Nino 3.4 index. The traditional index is the sea surface
   temperature (SST) anomaly over the Nino 3.4 box. Because the whole tropical
   ocean has warmed, a traditional anomaly now partly reflects that background
   warming rather than ENSO itself. The relative index subtracts the anomaly of
   the whole tropical band (20S-20N), leaving the part of the Nino 3.4 anomaly
   that is unusual compared with the rest of the tropics. That contrast is what
   the atmosphere responds to. Subtracting the tropical mean also damps the
   index slightly, so it is rescaled to vary by as much as the traditional
   index. Several forecasting centres, including NOAA CPC and the Copernicus
   Climate Change Service (C3S), now use relative indices; this one follows the
   C3S definition so that it matches the C3S forecasts.

2. Rainy-season rainfall over the study area, from ERA5.

3. A straight-line fit between the two, with its uncertainty. This is the
   statistical summary of the teleconnection. It is estimated from data, not
   set by hand, and the scatter around the line matters as much as the line.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from .config import (
    EL_NINO_THRESHOLD,
    FIRST_SEASON,
    INDEX_BASE_PERIOD,
    INDEX_SCALING_PERIOD,
    INDEX_SEASON_MONTHS,
    LA_NINA_THRESHOLD,
    RAINY_SEASON_MONTHS,
)
from .data import load_daily_weather, load_monthly_sst

# ---------------------------------------------------------------------------
# The C3S forecast for the coming season. Fill this in from the chart.
# ---------------------------------------------------------------------------

# Read from the C3S multi-system plume for the relative Nino 3.4 index,
# initialised on 1 October 2026. Enter the lower and upper edge of the shaded
# band for each month, in degC, and say which percentiles the band shows.
C3S_FORECAST: Dict[str, object] = {
    "product": "C3S multi-system seasonal forecast, relative Nino 3.4 plume",
    "initialised": "1 October 2026",
    "url": (
        "https://climate.copernicus.eu/charts/packages/c3s_seasonal/products/"
        "c3s_seasonal_plume_mm?area=rel_nino34&base_time=202610010000"
        "&type=plumepercentiles"
    ),
    "band": None,  # for example "25th to 75th percentile"
    "monthly_range": {
        "Dec": (None, None),
        "Jan": (None, None),
        "Feb": (None, None),
    },
}


def forecast_djf_range(forecast: Dict[str, object] = C3S_FORECAST) -> Optional[Tuple[float, float]]:
    """
    The DJF range implied by the monthly forecast band, or None if not filled in.

    Averaging the monthly band edges is an approximation to the band of the DJF
    mean. It is a reasonable one here, because the forecast members that are
    warm in December are mostly also warm in January and February.
    """
    monthly = forecast["monthly_range"]
    lows = [monthly[m][0] for m in ("Dec", "Jan", "Feb")]
    highs = [monthly[m][1] for m in ("Dec", "Jan", "Feb")]
    if any(v is None for v in lows + highs):
        return None
    low, high = float(np.mean(lows)), float(np.mean(highs))
    return (min(low, high), max(low, high))


# ---------------------------------------------------------------------------
# Step 1: the relative Nino 3.4 index
# ---------------------------------------------------------------------------

def _in_years(index: pd.DatetimeIndex, period: Tuple[int, int]) -> np.ndarray:
    return (index.year >= period[0]) & (index.year <= period[1])


def _monthly_anomalies(series: pd.Series, base_period: Tuple[int, int]) -> pd.Series:
    """Anomalies from the mean of each calendar month over the base period."""
    in_base = _in_years(series.index, base_period)
    climatology = series[in_base].groupby(series[in_base].index.month).mean()
    return series - climatology.reindex(series.index.month).to_numpy()


def relative_index_scaling(
    traditional: pd.Series,
    unscaled_relative: pd.Series,
    period: Tuple[int, int] = INDEX_SCALING_PERIOD,
) -> pd.Series:
    """
    The C3S scaling factor for each calendar month.

    For each month of the year, the standard deviation of the traditional Nino
    3.4 anomaly divided by the standard deviation of the unscaled relative
    anomaly, both over `period`. Multiplying the relative anomaly by this
    factor gives it the same year-to-year variability as the traditional index.
    The factors are usually a little above 1.
    """
    in_period = _in_years(traditional.index, period)
    months = traditional.index.month[in_period]
    numerator = traditional[in_period].groupby(months).std()
    denominator = unscaled_relative[in_period].groupby(months).std()
    return (numerator / denominator).rename("scaling_factor").rename_axis("month")


def monthly_enso_indices(
    base_period: Tuple[int, int] = INDEX_BASE_PERIOD,
    scaling_period: Tuple[int, int] = INDEX_SCALING_PERIOD,
) -> pd.DataFrame:
    """
    Monthly traditional and relative Nino 3.4 indices, in degC.

    Columns: `traditional` (Nino 3.4 SST anomaly), `tropical` (anomaly of the
    20S-20N mean) and `relative`, following the C3S definition:

        relative = (traditional - tropical) * scaling factor for that month

    Anomalies are relative to `base_period`, and the scaling factors are
    computed over `scaling_period` (see `relative_index_scaling`).
    """
    sst = load_monthly_sst()
    traditional = _monthly_anomalies(sst["nino34"], base_period)
    tropical = _monthly_anomalies(sst["tropics"], base_period)
    unscaled = traditional - tropical
    factors = relative_index_scaling(traditional, unscaled, scaling_period)
    relative = unscaled * factors.reindex(unscaled.index.month).to_numpy()

    frame = pd.DataFrame(
        {"traditional": traditional, "tropical": tropical, "relative": relative}
    )
    frame.attrs["scaling_factors"] = factors
    return frame


def seasonal_mean(monthly: pd.Series, months: Tuple[int, ...]) -> pd.Series:
    """
    Average a monthly series over a set of calendar months, season by season.

    Seasons that wrap across New Year are labelled by the year their first month
    falls in, so DJF 2015 means December 2015 to February 2016. Incomplete
    seasons are dropped.
    """
    selected = monthly[monthly.index.month.isin(months)]
    label = selected.index.year.to_numpy()
    if months[-1] < months[0]:
        label = np.where(selected.index.month.to_numpy() >= months[0], label, label - 1)
    grouped = selected.groupby(label)
    complete = grouped.count() == len(months)
    return grouped.mean()[complete]


def classify_phase(value: float) -> str:
    """El Nino, La Nina or neutral, from a DJF relative Nino 3.4 value."""
    if value >= EL_NINO_THRESHOLD:
        return "El Nino"
    if value <= LA_NINA_THRESHOLD:
        return "La Nina"
    return "Neutral"


def load_enso_index(first_season: int = FIRST_SEASON) -> pd.DataFrame:
    """
    The DJF ENSO record, one row per season from `first_season` onwards.

    Columns: `relative` (the index used throughout), `traditional` and
    `tropical` for comparison, and `phase`.
    """
    monthly = monthly_enso_indices()
    seasonal = pd.DataFrame(
        {name: seasonal_mean(monthly[name], INDEX_SEASON_MONTHS) for name in monthly}
    )
    seasonal = seasonal[seasonal.index >= first_season].dropna()
    seasonal["phase"] = seasonal["relative"].map(classify_phase)
    seasonal.index.name = "season"
    return seasonal


# ---------------------------------------------------------------------------
# Step 2: rainy-season rainfall over the study area
# ---------------------------------------------------------------------------

def rainy_season_label(dates: pd.DatetimeIndex, months: Tuple[int, ...] = RAINY_SEASON_MONTHS) -> np.ndarray:
    """The season each date belongs to, labelled by the year the season starts."""
    return np.where(dates.month >= months[0], dates.year, dates.year - 1)


def rainy_season_totals(
    weather: Optional[pd.DataFrame] = None,
    first_season: int = FIRST_SEASON,
    months: Tuple[int, ...] = RAINY_SEASON_MONTHS,
) -> pd.Series:
    """Total rainfall (mm) over the rainy-season months, for each complete season."""
    weather = load_daily_weather() if weather is None else weather
    in_season = weather[np.isin(weather.index.month, months)]
    label = rainy_season_label(in_season.index, months)
    totals = in_season["precip"].groupby(label).sum()
    days = in_season["precip"].groupby(label).count()

    # A season is complete if it has every day from the first of its first month
    # to the last of its last month.
    expected = pd.Series(
        {
            year: len(pd.date_range(
                pd.Timestamp(year, months[0], 1),
                pd.Timestamp(year + int(months[-1] < months[0]), months[-1], 1)
                + pd.offsets.MonthEnd(0),
            ))
            for year in days.index
        }
    )
    totals = totals[days == expected]
    totals = totals[totals.index >= first_season]
    totals.index.name = "season"
    return totals.rename("rainfall")


# ---------------------------------------------------------------------------
# Step 3: the fitted relationship
# ---------------------------------------------------------------------------

@dataclass
class TeleconnectionFit:
    """
    A straight-line fit of rainy-season rainfall on the DJF relative Nino 3.4
    index, with what is needed to describe its uncertainty.

    `slope` is in mm of rainfall per degC of the index. The bootstrap arrays hold
    the slope and intercept refitted on resampled sets of seasons, which shows
    how much the line itself could differ with a different sample of seasons.
    """

    slope: float
    intercept: float
    r: float
    p_value: float
    slope_stderr: float
    n: int
    data: pd.DataFrame                       # index, rainfall, fitted, residual
    bootstrap_slopes: np.ndarray = field(repr=False)
    bootstrap_intercepts: np.ndarray = field(repr=False)

    @property
    def mean_rainfall(self) -> float:
        return float(self.data["rainfall"].mean())

    @property
    def r_squared(self) -> float:
        return self.r ** 2

    @property
    def slope_percent(self) -> float:
        """Slope as a percentage of mean rainy-season rainfall per degC."""
        return 100.0 * self.slope / self.mean_rainfall

    @property
    def residual_std(self) -> float:
        return float(self.data["residual"].std(ddof=2))

    def slope_interval(self, level: float = 0.9) -> Tuple[float, float]:
        tail = 100 * (1 - level) / 2
        low, high = np.percentile(self.bootstrap_slopes, [tail, 100 - tail])
        return float(low), float(high)

    def predict(self, index_value) -> np.ndarray:
        """The expected rainfall for a given index value, on the fitted line."""
        return self.intercept + self.slope * np.asarray(index_value, dtype=float)

    def sample(
        self,
        index_value: float,
        rng: np.random.Generator,
        line_uncertainty: bool = True,
        scatter: bool = True,
    ) -> float:
        """
        One possible rainy-season total for a given index value.

        With `line_uncertainty`, the slope and intercept come from a random
        bootstrap refit. With `scatter`, a residual from a random historical
        season is added: the part of seasonal rainfall that ENSO does not
        explain. The result is floored at 10% of mean rainfall.
        """
        if line_uncertainty:
            k = rng.integers(len(self.bootstrap_slopes))
            slope, intercept = self.bootstrap_slopes[k], self.bootstrap_intercepts[k]
        else:
            slope, intercept = self.slope, self.intercept
        total = intercept + slope * index_value
        if scatter:
            total += float(rng.choice(self.data["residual"].to_numpy()))
        return float(max(total, 0.1 * self.mean_rainfall))

    def summary(self) -> str:
        low, high = self.slope_interval()
        return (
            f"{self.slope:+.0f} mm per degC ({self.slope_percent:+.0f}% of the mean), "
            f"95% confidence interval {low:+.0f} to {high:+.0f}; r = {self.r:.2f}, "
            f"r2 = {self.r_squared:.2f}, p = {self.p_value:.5f}, n = {self.n}"
        )


def fit_teleconnection(
    index: Optional[pd.Series] = None,
    rainfall: Optional[pd.Series] = None,
    n_bootstrap: int = 2000,
    seed: int = 1979,
) -> TeleconnectionFit:
    """
    Fit rainy-season rainfall against the DJF relative Nino 3.4 index.

    By default uses the ERA5 rainfall for the study area and the ERA5-based
    relative index, over all complete seasons from 1979.
    """
    index = load_enso_index()["relative"] if index is None else index
    rainfall = rainy_season_totals() if rainfall is None else rainfall
    joined = pd.concat({"index": index, "rainfall": rainfall}, axis=1).dropna()
    if len(joined) < 10:
        raise ValueError(f"Need at least 10 seasons to fit, got {len(joined)}.")

    x = joined["index"].to_numpy()
    y = joined["rainfall"].to_numpy()
    fit = stats.linregress(x, y)

    rng = np.random.default_rng(seed)
    slopes = np.empty(n_bootstrap)
    intercepts = np.empty(n_bootstrap)
    for k in range(n_bootstrap):
        pick = rng.integers(0, len(x), len(x))
        if np.ptp(x[pick]) == 0:
            pick = np.arange(len(x))
        slope, intercept = np.polyfit(x[pick], y[pick], 1)
        slopes[k], intercepts[k] = slope, intercept

    joined["fitted"] = fit.intercept + fit.slope * x
    joined["residual"] = y - joined["fitted"]
    return TeleconnectionFit(
        slope=float(fit.slope),
        intercept=float(fit.intercept),
        r=float(fit.rvalue),
        p_value=float(fit.pvalue),
        slope_stderr=float(fit.stderr),
        n=len(joined),
        data=joined,
        bootstrap_slopes=slopes,
        bootstrap_intercepts=intercepts,
    )


def seasonal_record() -> pd.DataFrame:
    """The ENSO index and the rainy-season rainfall side by side, one row per season."""
    return load_enso_index().join(rainy_season_totals(), how="inner")

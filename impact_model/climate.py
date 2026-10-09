# -*- coding: utf-8 -*-
"""
The climate driver: an observed ocean index, and how it reaches the farm.

Two drivers are available, and the impact model does not care which one it is
given:

  * `enso` - the Nino 3.4 sea surface temperature anomaly, averaged over DJF.
  * `iod`  - the Indian Ocean Dipole Mode Index, averaged over SON.

Both are defined so that a *positive* index suppresses rainfall over
summer-rainfall southern Africa, so the phase labels `positive`, `negative` and
`neutral` mean the same thing downstream in both cases. Only the display names
change: a positive ENSO season is an El Nino, a positive IOD season is a
positive dipole.

This module is deliberately the thinnest part of the package, because it is
where the largest scientific uncertainty lives. The indices are observed. The
step from an index to seasonal rainfall at a specific site is a statistical
assumption, and the lecture should say so out loud rather than hiding it inside
a function.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

# Repository root, reached from teaching/egs4030-drought-impact/impact_model/.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE_DATA = Path(__file__).resolve().parent.parent / "data"


def _search_paths(filename: str) -> List[Path]:
    """Bundled copy first, then the parent research repository."""
    return [
        _PACKAGE_DATA / filename,
        _REPO_ROOT / filename,
        _REPO_ROOT / "data" / filename,
    ]


DMI_FILENAME = "dmi_son_annual_averages.csv"
NINO34_FILENAME = "nino34_monthly.csv"


# ---------------------------------------------------------------------------
# What NOAA CPC said about the season this lecture falls in.
# ---------------------------------------------------------------------------

# Recorded from the CPC ENSO Diagnostic Discussion of 8 October 2026 so that
# the dashboard can cite a source rather than a number someone typed in. Update
# the figures, and the date, if you re-run this in a later season. The next
# discussion is scheduled for 12 November 2026.
CPC_ADVISORY = {
    "issued": "8 October 2026",
    "status": "El Nino Advisory",
    "latest_month": "September 2026",
    "nino34_anomaly": 2.1,
    "nino3_anomaly": 3.0,
    "nino12_anomaly": 3.9,
    "eastern_pacific_anomaly": 4.0,
    "very_strong_probability": 0.83,
    "historic_probability_son": 0.54,
    "historic_probability_ond": 0.83,
    "historic_probability_ndj": 0.70,
    "roni_forecast_ond_median": 2.74,
    "roni_outlook": "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/outlook/",
    "url": (
        "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/"
        "enso_advisory/ensodisc.shtml"
    ),
    "summary": (
        "El Nino continues to strengthen, with a strong-to-very strong event "
        "likely through January-March 2027 (greater than an 83% chance), and "
        "an 83% chance that October-December exceeds any event since 1950."
    ),
}


@dataclass(frozen=True)
class ClimateDriver:
    """
    Description of one ocean index and the assumptions attached to using it.

    `site_scaling` is the relative strength of the teleconnection at each site,
    which is not the same for the two indices: ENSO reaches furthest into the
    tropical summer-rainfall zone, while the IOD signal is weaker and more
    concentrated in the southeast.
    """

    key: str
    name: str
    index_name: str
    units: str
    season_label: str
    season_months: Tuple[int, ...]
    event_threshold: float
    positive_label: str
    negative_label: str
    neutral_label: str
    default_sensitivity: float
    default_noise_std: float
    site_scaling: Dict[str, float]
    record_note: str
    description: str
    loader: Callable[[Optional[Path]], pd.DataFrame] = field(repr=False, default=None)

    def phase_label(self, phase: str) -> str:
        """Human-readable name for a canonical phase key."""
        return {
            "positive": self.positive_label,
            "negative": self.negative_label,
            "neutral": self.neutral_label,
        }.get(phase, phase)


# Named IOD event years from analysis_config.IOD_COMPOSITE_SON_YEARS, kept here
# so the teaching package matches the composites used in the research code.
IOD_COMPOSITE_SON_YEARS: Dict[str, list] = {
    "positive": [1994, 1997, 2006, 2012, 2015, 2018, 2019],
    "negative": [1980, 1981, 1992, 1996, 1998],
}

# The El Nino seasons that produced the best-documented southern African crop
# failures. Used by the dashboard to mark analogues for the current event; the
# year is the planting year, so 2015 means the 2015/16 season.
ENSO_ANALOGUE_SEASONS: Dict[str, list] = {
    "positive": [1965, 1972, 1982, 1987, 1991, 1997, 2002, 2009, 2015, 2023],
    "negative": [1973, 1975, 1988, 1998, 1999, 2007, 2010, 2020, 2021, 2022],
}


def _load_dmi_frame(path: Optional[Path] = None) -> pd.DataFrame:
    """
    Load the observed SON-mean Dipole Mode Index.

    The bundled file is already seasonally averaged, with one column per
    observational sea surface temperature product.
    """
    frame = _read_first_existing(path, DMI_FILENAME).set_index("Year")
    reference = _preferred_column(
        frame, ("DMI_ERA5_SON", "DMI_HadISST_SON", "DMI_ERSST_SON")
    )
    return pd.DataFrame({"index_value": reference}).rename_axis("year")


def _load_nino34_frame(path: Optional[Path] = None) -> pd.DataFrame:
    """
    Load monthly Nino 3.4 anomalies and average them over DJF.

    The season is labelled by the year the December falls in, which is also the
    planting year of the summer crop it affects: the 2015 season means December
    2015 to February 2016, the season of the 2015/16 maize failure.
    """
    monthly = _read_first_existing(path, NINO34_FILENAME)
    series = _monthly_series(monthly)
    seasonal = seasonal_mean(series, months=(12, 1, 2))
    return pd.DataFrame({"index_value": seasonal}).rename_axis("year")


def _monthly_series(monthly: pd.DataFrame) -> pd.Series:
    """Turn the bundled year/month/anomaly table into a date-indexed series."""
    dates = pd.to_datetime(
        dict(year=monthly["year"], month=monthly["month"], day=1)
    )
    return pd.Series(
        monthly["nino34_anom"].astype(float).to_numpy(), index=dates
    ).sort_index()


def seasonal_mean(monthly: pd.Series, months: Tuple[int, ...]) -> pd.Series:
    """
    Average a monthly series over a fixed set of calendar months, by season.

    Seasons that wrap across New Year, such as DJF, are labelled by the year
    their first month falls in, so DJF 2015 means December 2015 to February
    2016. Incomplete seasons at either end of the record are dropped.
    """
    wraps = months[-1] < months[0]
    selected = monthly[monthly.index.month.isin(months)]

    season_year = selected.index.year.to_numpy()
    if wraps:
        # Months at or after the start month open a new season; the rest close
        # the season that opened in the previous calendar year.
        season_year = np.where(
            selected.index.month.to_numpy() >= months[0],
            season_year,
            season_year - 1,
        )

    grouped = selected.groupby(season_year)
    complete = grouped.count() == len(months)
    return grouped.mean()[complete]


def _read_first_existing(path: Optional[Path], filename: str) -> pd.DataFrame:
    candidates = [Path(path)] if path is not None else _search_paths(filename)
    for candidate in candidates:
        if candidate.exists():
            frame = pd.read_csv(candidate)
            frame.attrs["source_file"] = str(candidate)
            return frame

    searched = "\n  ".join(str(c) for c in candidates)
    raise FileNotFoundError(
        f"Could not find {filename}. Looked in:\n  {searched}\n"
        f"Copy it into {_PACKAGE_DATA} or pass an explicit path."
    )


def _preferred_column(frame: pd.DataFrame, preferred: Tuple[str, ...]) -> pd.Series:
    for column in preferred:
        if column in frame.columns:
            return frame[column].astype(float)
    numeric = frame.select_dtypes("number")
    if numeric.empty:
        raise ValueError("No numeric index column found in the input file.")
    return numeric.iloc[:, 0].astype(float)


# ---------------------------------------------------------------------------
# Where the default teleconnection strengths come from.
# ---------------------------------------------------------------------------

DEFAULT_SENSITIVITY_NOTE = """
The default rainfall sensitivities are not fitted. They are order-of-magnitude
estimates built from two numbers that are well established in the literature:

    sensitivity = r * CV            noise = CV * sqrt(1 - r^2)

where `r` is the correlation between the seasonal index and growing-season
rainfall, and `CV` is the coefficient of variation of that rainfall. Over the
summer-rainfall zone of southern Africa CV is roughly 0.28, and r is about -0.50
for DJF Nino 3.4 and about -0.30 for the SON dipole.

That gives a sensitivity near -0.14 per standard deviation for ENSO and -0.09
for the IOD, with most of the seasonal variance left unexplained in both cases.
The unexplained part is not a defect. It is the reason a strong El Nino raises
the probability of a bad harvest without guaranteeing one, and it is the single
most important thing for the students to take away.

These numbers are the right order but the wrong precision for any specific site.
Replacing them with a fitted value from station or reanalysis rainfall, using
`fit_sensitivity`, is one of the assessment tasks.
"""


DRIVERS: Dict[str, ClimateDriver] = {
    "enso": ClimateDriver(
        key="enso",
        name="El Nino Southern Oscillation",
        index_name="Nino 3.4",
        units="degC",
        season_label="DJF",
        season_months=(12, 1, 2),
        # The conventional +/- 0.5 degC threshold used to declare an event.
        event_threshold=0.5,
        positive_label="El Nino",
        negative_label="La Nina",
        neutral_label="Neutral",
        # See DEFAULT_SENSITIVITY_NOTE: r about -0.50 against a rainfall
        # coefficient of variation of about 0.28.
        default_sensitivity=-0.14,
        default_noise_std=0.24,
        site_scaling={
            "limpopo": 1.00,
            "free_state": 0.90,
            "inkomati": 0.95,
            "swartland": 0.15,
            "zambezi": 1.00,
        },
        record_note="NOAA CPC ERSSTv5, 1950 to present, 1991-2020 base period.",
        description=(
            "Nino 3.4 is the sea surface temperature anomaly averaged over "
            "170-120 degW, 5 degS-5 degN. It peaks in DJF, inside the southern "
            "African maize growing season, so the signal is strong but the "
            "forecast lead time is short."
        ),
    ),
    "iod": ClimateDriver(
        key="iod",
        name="Indian Ocean Dipole",
        index_name="Dipole Mode Index",
        units="degC",
        season_label="SON",
        season_months=(9, 10, 11),
        event_threshold=0.5,
        positive_label="Positive IOD",
        negative_label="Negative IOD",
        neutral_label="Neutral",
        # r about -0.30, weaker than ENSO, against the same rainfall variability.
        default_sensitivity=-0.09,
        default_noise_std=0.27,
        site_scaling={
            "limpopo": 1.00,
            "free_state": 0.85,
            "inkomati": 0.95,
            "swartland": 0.25,
            "zambezi": 0.55,
        },
        record_note="ERA5, HadISST and ERSST, 1980-2020.",
        description=(
            "The Dipole Mode Index is the sea surface temperature anomaly "
            "difference between the western (50-70 degE, 10 degS-10 degN) and "
            "south-eastern (90-110 degE, 10 degS-0 deg) equatorial Indian "
            "Ocean, after Saji et al. (1999). It peaks in SON, before planting, "
            "so the signal is weaker but arrives earlier."
        ),
    ),
}

# Attach the loaders after construction to keep the dataclass definitions
# readable and avoid forward references.
object.__setattr__(DRIVERS["enso"], "loader", _load_nino34_frame)
object.__setattr__(DRIVERS["iod"], "loader", _load_dmi_frame)

DEFAULT_DRIVER = "enso"


def get_driver(driver: "str | ClimateDriver" = DEFAULT_DRIVER) -> ClimateDriver:
    """Resolve a driver key to its definition, passing definitions through."""
    if isinstance(driver, ClimateDriver):
        return driver
    if driver not in DRIVERS:
        raise KeyError(
            f"Unknown climate driver {driver!r}. Available: {sorted(DRIVERS)}"
        )
    return DRIVERS[driver]


def load_index(
    driver: "str | ClimateDriver" = DEFAULT_DRIVER,
    path: Optional[Path] = None,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
    baseline: str = "record",
) -> pd.DataFrame:
    """
    Load one seasonally averaged climate index, classified into phases.

    Returns a frame indexed by season year with `index_value`, the standardised
    index, and a `phase` of `positive`, `negative` or `neutral`. The frame
    carries its driver in `frame.attrs["driver"]` so that downstream code can
    label plots without being told separately.

    `baseline` controls what the event threshold is measured against:

      * `record` - anomalies relative to the mean of the years being analysed.
      * `file`   - the anomalies exactly as published.

    The distinction matters. NOAA publishes Nino 3.4 against a 1991-2020
    climatology, but the bundled record starts in 1950, so the published
    anomalies carry a cold offset of about -0.12 degC in the early decades and
    classify more seasons as La Nina than a like-for-like comparison would.
    `record` removes that offset. It also means the classification depends on
    the period you select, which is worth saying out loud to the students rather
    than leaving for them to trip over.
    """
    spec = get_driver(driver)
    frame = spec.loader(path)

    if min_year is not None:
        frame = frame[frame.index >= min_year]
    if max_year is not None:
        frame = frame[frame.index <= max_year]
    frame = frame.dropna(subset=["index_value"])

    if frame.empty:
        raise ValueError(f"No {spec.index_name} data left after filtering by year.")

    return _classify(frame, spec, baseline=baseline)


def _classify(frame: pd.DataFrame, spec: ClimateDriver, baseline: str = "record") -> pd.DataFrame:
    """Standardise the index and label each season with its phase."""
    if baseline not in ("record", "file"):
        raise ValueError(f"baseline must be 'record' or 'file', got {baseline!r}")

    values = frame["index_value"].astype(float)
    offset = values.mean() if baseline == "record" else 0.0
    referenced = values - offset

    # Events are declared on the referenced anomaly, but the raw published value
    # is kept so that plots and tables show the number students would download.
    phase = pd.Series("neutral", index=frame.index, dtype=object)
    phase[referenced >= spec.event_threshold] = "positive"
    phase[referenced <= -spec.event_threshold] = "negative"

    frame = frame.copy()
    frame["index_anomaly"] = referenced
    frame["index_standardized"] = referenced / values.std(ddof=1)
    frame["phase"] = phase
    frame.attrs["driver"] = spec
    frame.attrs["baseline"] = baseline
    frame.attrs["baseline_offset"] = float(offset)
    return frame


def load_dmi(path: Optional[Path] = None) -> pd.DataFrame:
    """Convenience wrapper: the SON Dipole Mode Index record."""
    return load_index("iod", path=path)


def load_nino34(path: Optional[Path] = None, min_year: Optional[int] = None) -> pd.DataFrame:
    """Convenience wrapper: the DJF Nino 3.4 record."""
    return load_index("enso", path=path, min_year=min_year)


def latest_observation(path: Optional[Path] = None) -> Dict[str, float]:
    """
    The most recent monthly Nino 3.4 anomaly in the bundled file.

    Reported alongside the CPC advisory in the dashboard so that students can
    see how current the bundled data actually is, rather than assuming it is up
    to date.
    """
    monthly = _monthly_series(_read_first_existing(path, NINO34_FILENAME))
    last = monthly.index[-1]
    recent_three = float(monthly.iloc[-3:].mean())
    return {
        "date": last,
        "label": last.strftime("%B %Y"),
        "value": float(monthly.iloc[-1]),
        "three_month_mean": recent_three,
    }


@dataclass
class TeleconnectionAssumption:
    """
    The index to local rainfall link, stated explicitly as an assumption.

    `rainfall_sensitivity` is the fractional change in growing-season rainfall
    per 1 standard deviation of the seasonal index. It is negative over most of
    summer-rainfall southern Africa for both drivers: an El Nino, or a positive
    dipole, suppresses rainfall in the affected season.

    The default values are order-of-magnitude estimates for teaching, not fitted
    results; see DEFAULT_SENSITIVITY_NOTE for how they were arrived at. Replace
    them by calling `fit_sensitivity` against observed station or reanalysis
    rainfall before drawing any scientific conclusion. Making students do
    exactly that is one of the suggested assessment tasks.
    """

    rainfall_sensitivity: float = -0.14
    noise_std: float = 0.24          # unexplained seasonal rainfall variability
    is_fitted: bool = False
    source: str = "Illustrative default, not fitted"
    driver_key: str = DEFAULT_DRIVER

    @classmethod
    def for_driver(cls, driver: "str | ClimateDriver" = DEFAULT_DRIVER) -> "TeleconnectionAssumption":
        """Illustrative defaults appropriate to the chosen index."""
        spec = get_driver(driver)
        return cls(
            rainfall_sensitivity=spec.default_sensitivity,
            noise_std=spec.default_noise_std,
            is_fitted=False,
            source=f"Illustrative default for {spec.name}, not fitted",
            driver_key=spec.key,
        )


def site_scaling(site_key: str, driver: "str | ClimateDriver" = DEFAULT_DRIVER) -> float:
    """Relative teleconnection strength at one site for one driver."""
    return get_driver(driver).site_scaling.get(site_key, 1.0)


def rainfall_anomaly_from_index(
    index_standardized: float,
    site_key: str,
    assumption: TeleconnectionAssumption,
    driver: "str | ClimateDriver" = DEFAULT_DRIVER,
    rng: Optional[np.random.Generator] = None,
) -> float:
    """
    Translate a standardised seasonal index into a growing-season rainfall anomaly.

    The deterministic part is the teleconnection. The stochastic part represents
    everything else that sets seasonal rainfall and that the index does not
    explain, which in reality is most of the variance. Students should notice
    that the noise term usually dominates, and that this is a physically honest
    result rather than a defect in the model.
    """
    scaling = site_scaling(site_key, driver)
    deterministic = assumption.rainfall_sensitivity * scaling * index_standardized

    noise = 0.0
    if rng is not None and assumption.noise_std > 0:
        noise = float(rng.normal(0.0, assumption.noise_std))

    # An anomaly below -0.95 would mean essentially no rain at all.
    return float(np.clip(deterministic + noise, -0.95, 2.0))


def fit_sensitivity(
    index_standardized: pd.Series,
    seasonal_rainfall: pd.Series,
    driver: "str | ClimateDriver" = DEFAULT_DRIVER,
) -> TeleconnectionAssumption:
    """
    Fit the teleconnection from observed data, replacing the illustrative default.

    `seasonal_rainfall` should be growing-season totals in mm, indexed by the
    same years as `index_standardized`. The returned assumption carries the
    regression slope expressed as a fractional rainfall change per standard
    deviation of the index.
    """
    spec = get_driver(driver)
    joined = pd.concat(
        {"index": index_standardized, "rain": seasonal_rainfall}, axis=1
    ).dropna()
    if len(joined) < 10:
        raise ValueError(
            f"Need at least 10 overlapping years to fit a teleconnection, got {len(joined)}."
        )

    regression = stats.linregress(joined["index"], joined["rain"])
    mean_rainfall = joined["rain"].mean()
    if mean_rainfall <= 0:
        raise ValueError("Mean seasonal rainfall must be positive.")

    residual_std = float(
        np.std(joined["rain"] - (regression.intercept + regression.slope * joined["index"]), ddof=2)
    )

    return TeleconnectionAssumption(
        rainfall_sensitivity=float(regression.slope / mean_rainfall),
        noise_std=residual_std / mean_rainfall,
        is_fitted=True,
        source=(
            f"Fitted on {len(joined)} years of {spec.index_name}: "
            f"r={regression.rvalue:.2f}, p={regression.pvalue:.3f}"
        ),
        driver_key=spec.key,
    )


def aligned_indices(min_year: Optional[int] = None) -> pd.DataFrame:
    """
    Both indices on their common years, for head-to-head comparison.

    The two records have different lengths, so any fair comparison of which
    index better predicts the modelled harvest has to be made on the overlap.
    This returns that overlap, which is what the comparison task in the student
    brief asks for.
    """
    enso = load_index("enso", min_year=min_year)
    iod = load_index("iod", min_year=min_year)

    combined = pd.DataFrame(
        {
            "enso_value": enso["index_value"],
            "enso_standardized": enso["index_standardized"],
            "enso_phase": enso["phase"],
            "iod_value": iod["index_value"],
            "iod_standardized": iod["index_standardized"],
            "iod_phase": iod["phase"],
        }
    ).dropna()

    combined.attrs["correlation"] = float(
        combined["enso_standardized"].corr(combined["iod_standardized"])
    )
    return combined

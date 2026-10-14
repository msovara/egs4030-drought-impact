# -*- coding: utf-8 -*-
"""
A small crop water-balance impact model for the EGS4030/5030S practical:
maize in the Mopani district of Limpopo, and its link to ENSO.

The modules follow the impact modelling chain, one link each:

    data.py        reading the ERA5 rainfall, temperature and SST files
    climate.py     the relative Nino 3.4 index, Mopani rainfall, and the fitted
                   relationship between them
    weather.py     reference evapotranspiration, and rescaling a season's rain
    crop.py        the impact model: soil water balance and yield response
    experiment.py  historical runs, the same-rainfall experiment, and the
                   uncertainty cascade for the season ahead
    indices.py     SPI and SPEI, for comparison with the modelled impact
    config.py      the study area, period, soils and crop
"""

from .climate import (
    C3S_FORECAST,
    TeleconnectionFit,
    fit_teleconnection,
    forecast_djf_range,
    load_enso_index,
    monthly_enso_indices,
    rainy_season_totals,
    seasonal_record,
)
from .config import MAIZE, PLANTING_DATES, SOILS, STAGE_LABELS, STAGE_ORDER, STUDY_AREA
from .crop import SeasonResult, run_season
from .data import MissingDataError, load_daily_weather, load_monthly_sst
from .experiment import (
    CASCADE_STAGES,
    CascadeResult,
    run_cascade,
    run_historical,
    run_one_season,
    same_total_experiment,
)

__version__ = "0.2.0"

__all__ = [
    "C3S_FORECAST",
    "CASCADE_STAGES",
    "CascadeResult",
    "MAIZE",
    "MissingDataError",
    "PLANTING_DATES",
    "SOILS",
    "STAGE_LABELS",
    "STAGE_ORDER",
    "STUDY_AREA",
    "SeasonResult",
    "TeleconnectionFit",
    "fit_teleconnection",
    "forecast_djf_range",
    "load_daily_weather",
    "load_enso_index",
    "load_monthly_sst",
    "monthly_enso_indices",
    "rainy_season_totals",
    "run_cascade",
    "run_historical",
    "run_one_season",
    "run_season",
    "same_total_experiment",
    "seasonal_record",
]

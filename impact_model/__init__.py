# -*- coding: utf-8 -*-
"""
A desktop-scale crop water-balance impact model for EGS4030/5030S.

The package is arranged to follow the impact modelling chain, one module per link:

    climate.py     observed ENSO or IOD state, and its assumed link to rainfall
    weather.py     daily rainfall and temperature, and reference evapotranspiration
    crop.py        the impact model: soil water balance and yield response
    indices.py     SPI and SPEI, for comparison against the modelled impact
    experiment.py  multi-season runs and compositing by climate phase
    config.py      site, soil and crop parameters

The climate driver is selectable. `enso` uses the DJF Nino 3.4 index and is the
default; `iod` uses the SON Dipole Mode Index. Everything downstream is the same
either way, which is the point of keeping the driver in its own module.
"""

from .climate import (
    CPC_ADVISORY,
    DEFAULT_DRIVER,
    DRIVERS,
    ClimateDriver,
    TeleconnectionAssumption,
    aligned_indices,
    fit_sensitivity,
    get_driver,
    latest_observation,
    load_dmi,
    load_index,
    load_nino34,
)
from .config import CROPS, SITES, SOILS
from .crop import SeasonResult, run_season
from .experiment import (
    ScenarioResult,
    analogue_seasons,
    composite_by_phase,
    diurnal_range_sweep,
    run_observed_record,
    run_scenario,
    run_single_season,
    sensitivity_sweep,
    temperature_bias_sweep,
)
from .indices import (
    classify_drought,
    standardized_precipitation_evapotranspiration_index,
    standardized_precipitation_index,
)
from .weather import WeatherGeneratorParams, generate_weather, reference_et_hargreaves

__version__ = "0.1.0"

__all__ = [
    "CPC_ADVISORY",
    "CROPS",
    "DEFAULT_DRIVER",
    "DRIVERS",
    "SITES",
    "SOILS",
    "ClimateDriver",
    "ScenarioResult",
    "SeasonResult",
    "TeleconnectionAssumption",
    "WeatherGeneratorParams",
    "aligned_indices",
    "analogue_seasons",
    "classify_drought",
    "composite_by_phase",
    "diurnal_range_sweep",
    "fit_sensitivity",
    "generate_weather",
    "get_driver",
    "latest_observation",
    "load_dmi",
    "load_index",
    "load_nino34",
    "reference_et_hargreaves",
    "run_observed_record",
    "run_scenario",
    "run_season",
    "run_single_season",
    "sensitivity_sweep",
    "standardized_precipitation_evapotranspiration_index",
    "standardized_precipitation_index",
    "temperature_bias_sweep",
]

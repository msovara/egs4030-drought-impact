# -*- coding: utf-8 -*-
"""
Site, soil and crop parameters for the EGS4030/5030S drought impact demonstration.

Crop coefficients and stage lengths follow FAO Irrigation and Drainage Paper 56
(Allen et al., 1998). Yield response factors follow FAO Irrigation and Drainage
Paper 33 (Doorenbos and Kassam, 1979).
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Soil:
    """Root-zone soil hydraulic properties."""

    name: str
    field_capacity: float       # m3/m3, water content at -33 kPa
    wilting_point: float        # m3/m3, water content at -1500 kPa
    curve_number: float         # SCS runoff curve number, AMC II

    @property
    def available_water_capacity(self) -> float:
        """Plant-available water per metre of soil depth (mm/m)."""
        return 1000.0 * (self.field_capacity - self.wilting_point)


@dataclass(frozen=True)
class Crop:
    """FAO-56 crop coefficient curve and FAO-33 yield response factors."""

    name: str
    stage_lengths: Dict[str, int]        # days in initial/development/mid/late
    kc_initial: float
    kc_mid: float
    kc_end: float
    ky_by_stage: Dict[str, float]        # FAO-33 yield response factor per stage
    rooting_depth_initial: float         # m
    rooting_depth_max: float             # m
    depletion_fraction: float            # p, fraction of TAW before stress begins
    potential_yield: float               # t/ha under non-limiting water

    @property
    def season_length(self) -> int:
        return sum(self.stage_lengths.values())


@dataclass(frozen=True)
class Site:
    """A location with its climatology and planting calendar."""

    name: str
    latitude: float
    longitude: float
    soil: str                            # key into SOILS
    planting_day_of_year: int
    annual_rainfall: float               # mm, long-term mean
    rainfall_seasonality: List[float]    # fraction of annual total per month, Jan..Dec
    temp_mean_annual: float              # degC
    temp_amplitude: float                # degC, half the annual range of daily mean
    diurnal_range: float                 # degC, mean Tmax - Tmin
    description: str = ""


SOILS: Dict[str, Soil] = {
    "sandy_loam": Soil(
        name="Sandy loam",
        field_capacity=0.22,
        wilting_point=0.10,
        curve_number=72.0,
    ),
    "loam": Soil(
        name="Loam",
        field_capacity=0.29,
        wilting_point=0.14,
        curve_number=78.0,
    ),
    "clay_loam": Soil(
        name="Clay loam",
        field_capacity=0.36,
        wilting_point=0.22,
        curve_number=84.0,
    ),
    "sand": Soil(
        name="Sand",
        field_capacity=0.14,
        wilting_point=0.06,
        curve_number=65.0,
    ),
}


CROPS: Dict[str, Crop] = {
    "maize": Crop(
        name="Maize (grain)",
        stage_lengths={"initial": 25, "development": 40, "mid": 45, "late": 30},
        kc_initial=0.30,
        kc_mid=1.20,
        kc_end=0.40,
        # Flowering is by far the most drought-sensitive stage in maize.
        ky_by_stage={"initial": 0.40, "development": 0.40, "mid": 1.50, "late": 0.50},
        rooting_depth_initial=0.30,
        rooting_depth_max=1.20,
        depletion_fraction=0.55,
        potential_yield=9.0,
    ),
    "sorghum": Crop(
        name="Sorghum",
        stage_lengths={"initial": 20, "development": 35, "mid": 40, "late": 30},
        kc_initial=0.30,
        kc_mid=1.05,
        kc_end=0.55,
        ky_by_stage={"initial": 0.20, "development": 0.30, "mid": 0.55, "late": 0.20},
        rooting_depth_initial=0.30,
        rooting_depth_max=1.50,
        depletion_fraction=0.55,
        potential_yield=5.5,
    ),
    "soybean": Crop(
        name="Soybean",
        stage_lengths={"initial": 20, "development": 35, "mid": 45, "late": 25},
        kc_initial=0.40,
        kc_mid=1.15,
        kc_end=0.50,
        ky_by_stage={"initial": 0.20, "development": 0.80, "mid": 1.00, "late": 0.40},
        rooting_depth_initial=0.25,
        rooting_depth_max=1.00,
        depletion_fraction=0.50,
        potential_yield=3.2,
    ),
    "wheat_winter": Crop(
        name="Winter wheat (rainfed)",
        stage_lengths={"initial": 30, "development": 45, "mid": 40, "late": 30},
        kc_initial=0.40,
        kc_mid=1.15,
        kc_end=0.35,
        ky_by_stage={"initial": 0.20, "development": 0.60, "mid": 0.50, "late": 0.40},
        rooting_depth_initial=0.25,
        rooting_depth_max=1.50,
        depletion_fraction=0.55,
        potential_yield=4.0,
    ),
}


# Monthly rainfall fractions are normalised on construction, so these only need to
# capture the shape of the seasonal cycle.
_SUMMER_RAINFALL = [0.18, 0.16, 0.14, 0.07, 0.03, 0.01, 0.01, 0.01, 0.03, 0.08, 0.13, 0.15]
_WINTER_RAINFALL = [0.03, 0.03, 0.04, 0.09, 0.15, 0.18, 0.18, 0.14, 0.09, 0.05, 0.03, 0.03]
_TROPICAL_RAINFALL = [0.19, 0.17, 0.15, 0.08, 0.02, 0.00, 0.00, 0.01, 0.03, 0.09, 0.12, 0.14]


SITES: Dict[str, Site] = {
    "limpopo": Site(
        name="Limpopo lowveld (Mopani)",
        latitude=-23.9,
        longitude=30.5,
        soil="sandy_loam",
        planting_day_of_year=330,          # late November
        annual_rainfall=520.0,
        rainfall_seasonality=_SUMMER_RAINFALL,
        temp_mean_annual=22.5,
        temp_amplitude=6.0,
        diurnal_range=13.0,
        description="Marginal summer-rainfall maize on sandy soil; highly drought exposed.",
    ),
    "free_state": Site(
        name="Eastern Free State (Maize Triangle)",
        latitude=-28.5,
        longitude=27.8,
        soil="clay_loam",
        planting_day_of_year=320,          # mid November
        annual_rainfall=680.0,
        rainfall_seasonality=_SUMMER_RAINFALL,
        temp_mean_annual=15.5,
        temp_amplitude=8.5,
        diurnal_range=15.0,
        description="South Africa's commercial maize core; deeper soils buffer dry spells.",
    ),
    "inkomati": Site(
        name="Inkomati catchment (Mpumalanga)",
        latitude=-25.4,
        longitude=31.2,
        soil="loam",
        planting_day_of_year=325,
        annual_rainfall=760.0,
        rainfall_seasonality=_SUMMER_RAINFALL,
        temp_mean_annual=21.0,
        temp_amplitude=5.5,
        diurnal_range=12.0,
        description="Same catchment as the WRF-Hydro configuration; wetter and more reliable.",
    ),
    "swartland": Site(
        name="Swartland (Western Cape)",
        latitude=-33.3,
        longitude=18.7,
        soil="loam",
        planting_day_of_year=135,          # mid May
        annual_rainfall=420.0,
        rainfall_seasonality=_WINTER_RAINFALL,
        temp_mean_annual=17.0,
        temp_amplitude=6.5,
        diurnal_range=11.0,
        description="Winter-rainfall dryland wheat; contrasting season to the maize sites.",
    ),
    "zambezi": Site(
        name="Southern Zambia (Zambezi valley)",
        latitude=-16.8,
        longitude=27.9,
        soil="sandy_loam",
        planting_day_of_year=335,
        annual_rainfall=800.0,
        rainfall_seasonality=_TROPICAL_RAINFALL,
        temp_mean_annual=23.0,
        temp_amplitude=4.5,
        diurnal_range=14.0,
        description="Smallholder maize north of the strongest IOD teleconnection.",
    ),
}


# Default crop for each site, used to prefill the dashboard.
DEFAULT_CROP: Dict[str, str] = {
    "limpopo": "maize",
    "free_state": "maize",
    "inkomati": "maize",
    "swartland": "wheat_winter",
    "zambezi": "maize",
}


STAGE_ORDER: List[str] = ["initial", "development", "mid", "late"]

STAGE_LABELS: Dict[str, str] = {
    "initial": "Establishment",
    "development": "Vegetative",
    "mid": "Flowering / grain fill",
    "late": "Ripening",
}

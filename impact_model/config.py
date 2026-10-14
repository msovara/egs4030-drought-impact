# -*- coding: utf-8 -*-
"""
Settings for the Mopani maize case study: the study area, the time period, the
soils and the crop.

Everything a student might reasonably want to change is collected here, so that
the other modules can be read without hunting for hidden numbers.

Crop coefficients and stage lengths follow FAO Irrigation and Drainage Paper 56
(Allen et al., 1998). Yield response factors follow FAO Irrigation and Drainage
Paper 33 (Doorenbos and Kassam, 1979).
"""

from dataclasses import dataclass, replace
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Study area and period
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StudyArea:
    """The box over which ERA5 rainfall and temperature are averaged."""

    name: str
    lat_north: float
    lat_south: float
    lon_west: float
    lon_east: float
    note: str = ""

    @property
    def centre_latitude(self) -> float:
        return 0.5 * (self.lat_north + self.lat_south)

    @property
    def cds_area(self) -> List[float]:
        """The box in the [north, west, south, east] order the CDS API expects."""
        return [self.lat_north, self.lon_west, self.lat_south, self.lon_east]


# The dryland maize areas of Mopani district (around Giyani, Letsitele and the
# Greater Letaba lowveld), east of the escarpment and west of the Kruger National
# Park. The edges sit on the 0.25 degree ERA5 grid, giving 5 x 3 grid points.
# ERA5 cannot resolve the escarpment, so including it would mix very different
# rainfall regimes into one average.
STUDY_AREA = StudyArea(
    name="Mopani district lowveld, Limpopo",
    lat_north=-23.0,
    lat_south=-24.0,
    lon_west=30.5,
    lon_east=31.0,
    note="Dryland maize areas east of the escarpment and west of the Kruger National Park.",
)

# The satellite era. Before 1979 sea surface temperatures over much of the
# tropical oceans, and the reanalysis rainfall that depends on them, are less
# well constrained by observations.
FIRST_SEASON = 1979

# Season labels follow the planting year: the 2015 season is planted in
# November 2015 and harvested in 2016. The DJF index for that season is
# December 2015 to February 2016.

# The months over which seasonal rainfall is totalled, both for fitting the
# ENSO-rainfall relationship and for scaling rainfall in the forward runs.
RAINY_SEASON_MONTHS: Tuple[int, ...] = (11, 12, 1, 2, 3)
RAINY_SEASON_LABEL = "Nov-Mar"

# The months over which the ENSO index is averaged.
INDEX_SEASON_MONTHS: Tuple[int, ...] = (12, 1, 2)
INDEX_SEASON_LABEL = "DJF"

# The climatology period for the relative Nino 3.4 index. The C3S seasonal
# forecasts express their anomalies relative to the 1993-2016 hindcast period,
# so using the same period here lets forecast values be compared directly with
# the historical record.
INDEX_BASE_PERIOD: Tuple[int, int] = (1993, 2016)

# The period over which C3S computes the scaling factor that restores the
# variance of the relative index (see climate.relative_index_scaling).
INDEX_SCALING_PERIOD: Tuple[int, int] = (1991, 2020)

# Thresholds for labelling a season as El Nino or La Nina, in degC of the DJF
# relative Nino 3.4 index.
EL_NINO_THRESHOLD = 0.5
LA_NINA_THRESHOLD = -0.5


# ---------------------------------------------------------------------------
# Soils
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Soil:
    """Root-zone soil water properties."""

    name: str
    field_capacity: float       # m3/m3, the wettest the soil stays after draining
    wilting_point: float        # m3/m3, the driest a plant can extract water to
    curve_number: float         # SCS runoff curve number

    @property
    def available_water_capacity(self) -> float:
        """Plant-available water per metre of soil depth (mm/m)."""
        return 1000.0 * (self.field_capacity - self.wilting_point)


SOILS: Dict[str, Soil] = {
    "sand": Soil(name="Sand", field_capacity=0.14, wilting_point=0.06, curve_number=65.0),
    "sandy_loam": Soil(name="Sandy loam", field_capacity=0.22, wilting_point=0.10, curve_number=72.0),
    "loam": Soil(name="Loam", field_capacity=0.29, wilting_point=0.14, curve_number=78.0),
}

# Sandy soils are common under dryland maize in the Mopani lowveld.
DEFAULT_SOIL = "sandy_loam"


# ---------------------------------------------------------------------------
# Crop
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Crop:
    """FAO-56 crop coefficient curve and FAO-33 yield response factors."""

    name: str
    stage_lengths: Dict[str, int]        # days in each growth stage
    kc_initial: float
    kc_mid: float
    kc_end: float
    ky_by_stage: Dict[str, float]        # how strongly a water deficit cuts yield
    rooting_depth_initial: float         # m
    rooting_depth_max: float             # m
    depletion_fraction: float            # share of available water used before stress
    potential_yield: float               # t/ha with no water shortage

    @property
    def season_length(self) -> int:
        return sum(self.stage_lengths.values())

    def with_flowering_ky(self, ky_mid: float) -> "Crop":
        """A copy of the crop with a different yield response at flowering."""
        return replace(self, ky_by_stage={**self.ky_by_stage, "mid": ky_mid})


STAGE_ORDER: List[str] = ["initial", "development", "mid", "late"]

STAGE_LABELS: Dict[str, str] = {
    "initial": "Establishment",
    "development": "Vegetative growth",
    "mid": "Flowering and grain fill",
    "late": "Ripening",
}

MAIZE = Crop(
    name="Maize (grain, medium season)",
    stage_lengths={"initial": 25, "development": 40, "mid": 45, "late": 30},
    kc_initial=0.30,
    kc_mid=1.20,
    kc_end=0.40,
    # Flowering is the most drought-sensitive stage in maize: a water shortage
    # around tasselling and silking reduces the number of kernels that set.
    ky_by_stage={"initial": 0.40, "development": 0.40, "mid": 1.50, "late": 0.50},
    rooting_depth_initial=0.30,
    rooting_depth_max=1.20,
    depletion_fraction=0.55,
    # Results are reported mainly as a percentage of this water-unlimited yield,
    # because the absolute figure for dryland maize in Mopani is uncertain.
    potential_yield=9.0,
)


# ---------------------------------------------------------------------------
# Planting dates
# ---------------------------------------------------------------------------

# (month, day). The standard date is used throughout the core task; the others
# are for the 5030S extension.
PLANTING_DATES: Dict[str, Tuple[int, int]] = {
    "early": (11, 1),
    "standard": (11, 25),
    "late": (12, 20),
}
DEFAULT_PLANTING = "standard"


# ---------------------------------------------------------------------------
# Plausible ranges for the soil and crop step of the uncertainty cascade
# ---------------------------------------------------------------------------

# These are illustrative ranges, not measured distributions. They represent the
# fact that soils vary across the district and that the FAO-33 response factor
# at flowering is a typical value rather than a property of a specific cultivar.
CASCADE_SOILS: List[str] = ["sand", "sandy_loam", "loam"]
CASCADE_FLOWERING_KY: List[float] = [1.3, 1.5, 1.7]

# -*- coding: utf-8 -*-
"""
Measured error in the environmental data that drives the impact model.

An impact model inherits every error in the information that drives it. This
module holds the verified skill of Mvula v5, a lightweight African weather model,
so the lecture can put a real number on that statement instead of gesturing at it.

READ THIS BEFORE USING THE NUMBERS
----------------------------------
These are **not** forecast lead times, and the four entries are not a decay
curve. The evaluation is analysis-forced: every entry is a *single* +6 h step
launched from a fresh ERA5 analysis initial condition, within a campaign
initialised at 00Z. What separates the four entries is the time of day, not how
far ahead they are forecasting.

    entry   IC taken at   valid at       what that is locally over Africa
    ------  ------------  -------------  --------------------------------
    1       00Z           06Z            dawn, near the daily minimum
    2       06Z           12Z            early afternoon, near peak heating
    3       12Z           18Z            evening, after sunset
    4       18Z           00Z next day   night

The giveaway is that RMSE is not monotonic: 1.38, then 7.80, then 4.38, then
3.23. Error growth with lead time cannot come back down. A diurnal cycle can,
and does.

So the story this module supports is not "error grows as you forecast further
ahead". It is "the model cannot reproduce the daily heating cycle": it is
essentially unbiased at dawn, 5.3 degC too cold in the early afternoon, and
1.3 degC too warm at night. That is a damped diurnal cycle, and it matters for
an impact model far more than a uniform offset would, because Hargreaves-Samani
estimates evaporative demand from the diurnal *range*.

All values are transcribed from the public evaluation listed in PROVENANCE.
Nothing here is estimated except the quantities in DERIVED_DIURNAL_BIAS, which
are marked as derived and show their working.
"""

from dataclasses import dataclass
from typing import Dict, List

PROVENANCE = {
    "model": "Mvula v5 (LapAIStudentCNN), freeze tag trackb-v5-c4e",
    "repository": "https://github.com/msovara/lapai-forecast-africa",
    "checkpoint": "models/student_global_stable_v5.ckpt (~8.8 MiB)",
    "skill_source": "reports/TRACKB_T2M_EXPANDED.md",
    "baseline_source": "reports/TRACKB_T2M_BASELINES.md",
    "evaluated": "2026-08-26 (skill), 2026-08-30 (baselines)",
    "protocol": (
        "Analysis-forced (Case A, Cout=3): initial condition taken from ERA5 "
        "analysis at init+(L-6)h, one single +6 h student step, scored at valid "
        "time init+L against ERA5. Campaign initialised at 00Z, so L indexes the "
        "time of day of the valid time, not a forecast lead. There is no "
        "autoregressive rollout anywhere in this evaluation."
    ),
    "domain": (
        "Cosine-latitude weighted over the Africa box, latitude -40 to 40, "
        "longitude -20 to 55."
    ),
    "sample": "61 initialisations spanning DJF, MAM, JJA and SON of 2023",
    "variable": (
        "2 m temperature. Precipitation is out of scope: the tp head collapsed "
        "to all-dry."
    ),
}


@dataclass(frozen=True)
class SingleStepSkill:
    """
    Verified skill of one +6 h analysis-forced step, at one time of day.

    `campaign_offset_hours` is the L value in the source table, kept so the
    numbers can be traced back. It is an index into the 00Z campaign, not a
    forecast lead time.
    """

    campaign_offset_hours: int
    ic_hour_utc: int
    valid_hour_utc: int
    local_phase: str
    rmse: float                  # degC, cosine-latitude weighted over Africa
    anomaly_correlation: float
    bias: float                  # degC, negative means the model runs cold
    persistence_rmse: float      # degC, analysis-forced persistence baseline
    skill_vs_persistence: float  # fraction, positive means better than persistence

    @property
    def beats_persistence(self) -> bool:
        return self.skill_vs_persistence > 0

    @property
    def label(self) -> str:
        return f"valid {self.valid_hour_utc:02d}Z"

    @property
    def long_label(self) -> str:
        return f"{self.label} ({self.local_phase})"


# From the lead-time table in TRACKB_T2M_EXPANDED.md and the baselines in
# TRACKB_T2M_BASELINES.md, re-indexed by valid time of day. Keys are the
# campaign offsets used in the source table so the two can be cross-checked.
MVULA_V5_AFRICA_T2M: Dict[int, SingleStepSkill] = {
    6: SingleStepSkill(
        campaign_offset_hours=6,
        ic_hour_utc=0,
        valid_hour_utc=6,
        local_phase="dawn",
        rmse=1.382,
        anomaly_correlation=0.965,
        bias=-0.115,
        persistence_rmse=2.373,
        skill_vs_persistence=0.418,
    ),
    12: SingleStepSkill(
        campaign_offset_hours=12,
        ic_hour_utc=6,
        valid_hour_utc=12,
        local_phase="early afternoon",
        rmse=7.800,
        anomaly_correlation=0.446,
        bias=-5.330,
        persistence_rmse=6.581,
        skill_vs_persistence=-0.185,
    ),
    18: SingleStepSkill(
        campaign_offset_hours=18,
        ic_hour_utc=12,
        valid_hour_utc=18,
        local_phase="evening",
        rmse=4.377,
        anomaly_correlation=0.749,
        bias=-1.115,
        persistence_rmse=3.691,
        skill_vs_persistence=-0.186,
    ),
    24: SingleStepSkill(
        campaign_offset_hours=24,
        ic_hour_utc=18,
        valid_hour_utc=0,
        local_phase="night",
        rmse=3.231,
        anomaly_correlation=0.835,
        bias=1.299,
        persistence_rmse=3.879,
        skill_vs_persistence=0.167,
    ),
}


# The 12Z cold bias is systematic rather than noise. It appears on every one of
# the 61 initialisations and in all four seasons, with a seasonal mean between
# -5.41 and -5.11 degC (DJF -5.395, JJA -5.409, MAM -5.403, SON -5.107). That it
# barely moves between midsummer and midwinter is itself evidence that it is a
# time-of-day error rather than a seasonal or synoptic one.
SYSTEMATIC_BIAS_NOTE = (
    "The 12Z cold bias appears on 61 of 61 initialisations and in every season, "
    "with a seasonal mean between -5.41 and -5.11 degC. It is a systematic error, "
    "not scatter, so an impact model driven by it would be wrong in the same "
    "direction every single time."
)

NON_MONOTONIC_NOTE = (
    "RMSE runs 1.38, 7.80, 4.38, 3.23 across the four entries. Error growth with "
    "forecast lead time cannot decrease, so this sequence cannot be a decay "
    "curve. It is the signature of a model that has not learnt the daily heating "
    "cycle."
)


# ---------------------------------------------------------------------------
# Derived quantities: what the diurnal error means for daily Tmax and Tmin.
# ---------------------------------------------------------------------------

# The impact model needs daily maximum and minimum temperature, but the
# evaluation samples every six hours, so neither Tmax nor Tmin is measured
# directly. These are the closest available proxies, and they are estimates.
#
#   Tmax  the daily maximum falls between 12Z and 18Z local over most of the
#         box, and the 12Z sample is the nearest to peak heating, so the 12Z
#         bias of -5.33 degC is used and is, if anything, conservative.
#   Tmin  the daily minimum falls near dawn. The 06Z sample sits closest to it
#         at -0.115 degC, and the 00Z night sample gives +1.299 degC. Their
#         mean is used.
#
# Both numbers are proxies from six-hourly sampling. Treat them as the right
# order of magnitude, not as measurements, and say so to the students.
DERIVED_DIURNAL_BIAS = {
    "t_max_bias": -5.330,
    "t_min_bias": 0.592,
    "basis": (
        "Tmax from the 12Z sample, nearest peak heating. Tmin from the mean of "
        "the 06Z dawn and 00Z night samples. Six-hourly sampling does not "
        "resolve the true daily extremes, so both are proxies."
    ),
}

DERIVED_DIURNAL_BIAS["diurnal_range_bias"] = (
    DERIVED_DIURNAL_BIAS["t_max_bias"] - DERIVED_DIURNAL_BIAS["t_min_bias"]
)
DERIVED_DIURNAL_BIAS["t_mean_bias"] = 0.5 * (
    DERIVED_DIURNAL_BIAS["t_max_bias"] + DERIVED_DIURNAL_BIAS["t_min_bias"]
)


WHY_THE_RANGE_MATTERS = (
    "Hargreaves-Samani estimates evaporative demand as ET0 proportional to "
    "(Tmean + 17.8) times the square root of (Tmax - Tmin). A damped diurnal "
    "cycle therefore hits the impact model twice: it lowers the mean, and it "
    "lowers the range under a square root. Driving the crop model with this "
    "weather makes the atmosphere look far less thirsty than it is, so the crop "
    "appears less water stressed and the modelled harvest comes out too high. "
    "A department acting on it would under-warn farmers in exactly the seasons "
    "when warning matters."
)


def ordered_entries() -> List[SingleStepSkill]:
    """Skill entries in campaign order: 06Z, 12Z, 18Z, then 00Z the next day."""
    return [MVULA_V5_AFRICA_T2M[offset] for offset in sorted(MVULA_V5_AFRICA_T2M)]


# Retained because the earlier version of this module used this name.
ordered_leads = ordered_entries


def summary_rows() -> List[Dict[str, object]]:
    """Flat rows for display in a table."""
    return [
        {
            "Valid time": entry.label,
            "Local phase": entry.local_phase,
            "IC": f"{entry.ic_hour_utc:02d}Z",
            "RMSE (degC)": entry.rmse,
            "Bias (degC)": entry.bias,
            "ACC": entry.anomaly_correlation,
            "Persistence RMSE (degC)": entry.persistence_rmse,
            "Skill vs persistence": entry.skill_vs_persistence,
            "Beats persistence": "yes" if entry.beats_persistence else "no",
        }
        for entry in ordered_entries()
    ]

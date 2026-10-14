# -*- coding: utf-8 -*-
"""
Figure 1: what happens inside one growing season (Task 1).

For each season listed, three panels: daily rainfall; the water held in the
root zone against the level below which the crop is stressed; and the crop's
water demand against what it actually managed to use. The growth stages are
shaded, so you can see when stress coincided with flowering.

Run from the repository root:
    python student_task/templates/fig1_one_season.py
"""

import _setup  # noqa: F401  (sets up paths)
import matplotlib.pyplot as plt

from impact_model.config import STAGE_LABELS, STAGE_ORDER
from impact_model.experiment import run_one_season

# --- Things you can change -------------------------------------------------
SEASONS = [2015, 1999]       # planting years; 2015 means the 2015/16 season
SOIL = "sandy_loam"          # "sand", "sandy_loam" or "loam"
PLANTING = "standard"        # "early", "standard" or "late"
FILENAME = "fig1_one_season.png"
# ---------------------------------------------------------------------------

fig, axes = plt.subplots(3, len(SEASONS), figsize=(5.5 * len(SEASONS), 8),
                         sharex="col", sharey="row", squeeze=False)

for col, season in enumerate(SEASONS):
    result, _ = run_one_season(season, soil_key=SOIL, planting=PLANTING)
    daily = result.daily
    days = daily["day_of_season"]

    ax = axes[0, col]
    ax.bar(days, daily["precip"], color="#2e86c1", width=1.0)
    ax.set_title(f"{_setup.season_label(season)}: yield {result.relative_yield:.0%} of potential", pad=16)

    ax = axes[1, col]
    ax.plot(days, daily["soil_water"], color="#1a5276", lw=2, label="Water in root zone")
    ax.plot(days, daily["total_available_water"], color="0.4", ls=":", label="Full (field capacity)")
    ax.plot(days, daily["total_available_water"] - daily["readily_available_water"],
            color="#e67e22", ls="--", label="Stress threshold")

    ax = axes[2, col]
    ax.plot(days, daily["et_potential"], color="#a04000", ls=":", label="Crop water demand")
    ax.plot(days, daily["et_actual"], color="#196f3d", lw=1.5, label="Water actually used")
    ax.fill_between(days, daily["et_actual"], daily["et_potential"], color="#c0392b", alpha=0.25,
                    label="Shortfall")
    ax.set_xlabel("Days after planting")

    # Shade the growth stages in every panel.
    for row in range(3):
        for stage in STAGE_ORDER:
            in_stage = days[daily["stage"] == stage]
            axes[row, col].axvspan(in_stage.min() - 0.5, in_stage.max() + 0.5,
                                   color=_setup.STAGE_COLOURS[stage], alpha=0.5, lw=0, zorder=0)
    for stage in STAGE_ORDER:
        in_stage = days[daily["stage"] == stage]
        axes[0, col].text(in_stage.mean(), 1.0, STAGE_LABELS[stage], transform=axes[0, col].get_xaxis_transform(),
                          ha="center", va="bottom", fontsize=7)

axes[0, 0].set_ylabel("Rainfall (mm/day)")
axes[1, 0].set_ylabel("Soil water (mm)")
axes[2, 0].set_ylabel("Water use (mm/day)")
axes[1, 0].legend(fontsize=8, loc="upper right")
axes[2, 0].legend(fontsize=8, loc="upper right")
fig.tight_layout()
_setup.save(fig, FILENAME)

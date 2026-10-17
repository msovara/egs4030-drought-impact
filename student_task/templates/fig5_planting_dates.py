# -*- coding: utf-8 -*-
"""
Figure 5 (5030S extension): does planting date change the odds?

Runs the full cascade (all four sources of uncertainty) for each planting date,
under the forecast range and under a neutral ENSO season.

Run from the repository root:
    python student_task/templates/fig5_planting_dates.py
"""

import _setup  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from impact_model.climate import forecast_djf_range
from impact_model.config import PLANTING_DATES
from impact_model.experiment import run_cascade

# --- Things you can change -------------------------------------------------
FORECAST_RANGE = None        # (low, high) in degC
MEMBERS = 500
SOIL = "sandy_loam"
SEED = 2026
FILENAME = "fig5_planting_dates.png"
# ---------------------------------------------------------------------------

index_range = FORECAST_RANGE #or forecast_djf_range()
if index_range is None:
    raise SystemExit("Set FORECAST_RANGE at the top of this file.")

rows, data, labels = [], [], []
for name, (month, day) in PLANTING_DATES.items():
    result = run_cascade(index_range, members=MEMBERS, soil_key=SOIL, planting=name, seed=SEED)
    forecast = result.members.loc[result.members["stage"] == "response", "relative_yield"]
    neutral = result.neutral["relative_yield"]
    # The poor-season threshold is set from the standard planting date's history,
    # so that all planting dates are judged against the same yardstick.
    if name == "standard":
        threshold = result.poor_threshold
    data += [100 * forecast, 100 * neutral]
    labels += [f"{name}\n({day} {['Nov', 'Dec'][month - 11]})\nforecast", f"{name}\nneutral"]
    rows.append({"planting": name, "forecast_median": forecast.median(), "neutral_median": neutral.median(),
                 "_forecast": forecast.to_numpy(), "_neutral": neutral.to_numpy()})

summary = pd.DataFrame(rows).set_index("planting")
summary["forecast_prob_poor"] = summary["_forecast"].map(lambda v: np.mean(v < threshold))
summary["neutral_prob_poor"] = summary["_neutral"].map(lambda v: np.mean(v < threshold))
summary = summary.drop(columns=["_forecast", "_neutral"])
print(summary.round(2).to_string())

fig, ax = plt.subplots(figsize=(11, 5))
box = ax.boxplot(data, whis=(10, 90), showfliers=False, patch_artist=True, widths=0.55)
for k, patch in enumerate(box["boxes"]):
    patch.set_facecolor("#cb4335" if k % 2 == 0 else "#bdc3c7")
ax.set_xticks(range(1, len(labels) + 1), labels, fontsize=8)
ax.axhline(100 * threshold, color="k", ls="--", lw=1)
ax.set_ylabel("Modelled yield (% of potential)")
ax.set_title("Planting date under the 2026/27 forecast range (red) and a neutral season (grey)")
fig.tight_layout()
_setup.save(fig, FILENAME)

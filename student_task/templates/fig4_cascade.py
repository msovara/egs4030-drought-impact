# -*- coding: utf-8 -*-
"""
Figure 4: the 2026/27 season as a cascade of uncertainty (Task 4).

Each box shows the spread of modelled yields as one more source of
uncertainty is added. The last two boxes are references: the same full
calculation for a neutral ENSO season, and the model run on the actual
seasons since 1979. The dashed line marks a "poor" season (the worst third
of the historical seasons) and the numbers give the chance of falling below it.

Run from the repository root:
    python student_task/templates/fig4_cascade.py
"""

import _setup  # noqa: F401
import matplotlib.pyplot as plt

from impact_model.climate import forecast_djf_range
from impact_model.experiment import CASCADE_STAGES, run_cascade

# --- Things you can change -------------------------------------------------
# The DJF range you read from the C3S plume, in degC, as (low, high).
# None uses the range entered by the lecturer in impact_model/climate.py.
FORECAST_RANGE = None
MEMBERS = 500                # ensemble members per box
SOIL = "sandy_loam"
PLANTING = "standard"
SEED = 2026                  # change to check how much the answer depends on chance
FILENAME = "fig4_cascade.png"
# ---------------------------------------------------------------------------

index_range = FORECAST_RANGE or forecast_djf_range()
if index_range is None:
    raise SystemExit("Set FORECAST_RANGE at the top of this file to the DJF range you read from the C3S chart.")

result = run_cascade(index_range, members=MEMBERS, soil_key=SOIL, planting=PLANTING, seed=SEED)
summary = result.stage_summary()
print(summary.round(2).to_string())

groups = [result.members.loc[result.members["stage"] == key, "relative_yield"] for key, _ in CASCADE_STAGES]
groups += [result.neutral["relative_yield"], result.historical["relative_yield"]]
labels = [label.replace(" + ", "\n+ ") for _, label in CASCADE_STAGES]
labels += ["Neutral ENSO\n(all uncertainty)", "Historical\nseasons"]

fig, ax = plt.subplots(figsize=(12, 5.5))
box = ax.boxplot([100 * g for g in groups], whis=(10, 90), showfliers=False, patch_artist=True,
                 widths=0.55)
colours = ["#f5b7b1", "#f1948a", "#ec7063", "#cb4335", "#bdc3c7", "#d5dbdb"]
for patch, colour in zip(box["boxes"], colours):
    patch.set_facecolor(colour)
ax.set_xticks(range(1, len(labels) + 1), labels, fontsize=8)
ax.axhline(100 * result.poor_threshold, color="k", ls="--", lw=1)
ax.text(len(labels) + 0.45, 100 * result.poor_threshold, "poor", va="center", fontsize=8)
for k, (_, row) in enumerate(summary.iterrows(), start=1):
    ax.text(k, 101, f"P(poor)\n{row['prob_poor']:.0%}", ha="center", va="bottom", fontsize=8)
ax.axvline(4.5, color="0.5", lw=0.8)
ax.set_ylim(0, 112)
ax.set_ylabel("Modelled yield (% of potential)\nboxes 25th-75th, whiskers 10th-90th percentile")
ax.set_title(f"2026/27 maize, Mopani: DJF relative Nino 3.4 between {index_range[0]:+.1f} "
             f"and {index_range[1]:+.1f} degC", pad=30)
fig.tight_layout()
_setup.save(fig, FILENAME)

summary.to_csv(_setup.FIGURE_DIR / "fig4_cascade_summary.csv")
print(f"\nPast seasons with an index in this range: "
      f"{', '.join(_setup.season_label(s) for s in result.historical_in_range().index) or 'none'}")

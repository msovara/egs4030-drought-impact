# -*- coding: utf-8 -*-
"""
Figure 3: from rainfall to modelled yield (Task 3).

(a) Modelled yield against the ENSO index.
(b) Modelled yield against Nov-Mar rainfall.
(c) Every historical season given the same Nov-Mar total, keeping its own
    day-to-day timing. Any difference between the bars is due to timing alone.

Run from the repository root:
    python student_task/templates/fig3_rainfall_to_yield.py
"""

import _setup  # noqa: F401
import matplotlib.pyplot as plt

from impact_model.experiment import run_historical, same_total_experiment

# --- Things you can change -------------------------------------------------
SOIL = "sandy_loam"
PLANTING = "standard"
SAME_TOTAL_MM = None         # None uses the median Nov-Mar total; or give a number in mm
FILENAME = "fig3_rainfall_to_yield.png"
# ---------------------------------------------------------------------------

history = run_historical(SOIL, PLANTING)
same = same_total_experiment(SAME_TOTAL_MM, SOIL, PLANTING)

r_index = history["relative_yield"].corr(history["relative_index"])
r_rain = history["relative_yield"].corr(history["rainfall"])
print(f"Correlation of yield with the ENSO index: r = {r_index:.2f} (r2 = {r_index ** 2:.2f})")
print(f"Correlation of yield with Nov-Mar rainfall: r = {r_rain:.2f} (r2 = {r_rain ** 2:.2f})")

fig = plt.figure(figsize=(13, 8))
ax_a = fig.add_subplot(2, 2, 1)
ax_b = fig.add_subplot(2, 2, 2, sharey=ax_a)
ax_c = fig.add_subplot(2, 1, 2)

for phase, colour in _setup.PHASE_COLOURS.items():
    rows = history[history["phase"] == phase]
    ax_a.scatter(rows["relative_index"], 100 * rows["relative_yield"], color=colour, label=phase,
                 edgecolor="k", lw=0.4)
    ax_b.scatter(rows["rainfall"], 100 * rows["relative_yield"], color=colour, edgecolor="k", lw=0.4)
ax_a.set_xlabel("DJF relative Nino 3.4 (degC)")
ax_a.set_ylabel("Modelled yield (% of potential)")
ax_a.set_title(f"(a) Yield and ENSO: r = {r_index:.2f}")
ax_a.legend(fontsize=8)
ax_b.set_xlabel("Nov-Mar rainfall (mm)")
ax_b.set_title(f"(b) Yield and seasonal rainfall: r = {r_rain:.2f}")

ordered = same.sort_values("relative_yield")
labels = [_setup.season_label(s) for s in ordered.index]
colours = [_setup.PHASE_COLOURS[history.loc[s, "phase"]] for s in ordered.index]
ax_c.bar(labels, 100 * ordered["relative_yield"], color=colours)
ax_c.set_ylabel("Modelled yield (% of potential)")
ax_c.set_title(f"(c) Every season given the same Nov-Mar rainfall ({same.attrs['total_mm']:.0f} mm), "
               "keeping its own timing")
ax_c.tick_params(axis="x", rotation=90, labelsize=7)
fig.tight_layout()
_setup.save(fig, FILENAME)

print("\nLowest and highest yields at the same rainfall total:")
print(ordered.iloc[[0, 1, 2, -3, -2, -1]][["relative_yield", "flowering_rainfall", "flowering_dry_spell"]]
      .round(2).to_string())

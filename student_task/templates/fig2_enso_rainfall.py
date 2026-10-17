# -*- coding: utf-8 -*-
"""
Figure 2: ENSO and Mopani rainfall in the historical record (Task 2).

Left: DJF relative Nino 3.4 against Nov-Mar ERA5 rainfall for each season since
1979, with the fitted line and the range of lines from refitting on resampled
seasons. Right: the same two quantities through time.

Run from the repository root:
    python student_task/templates/fig2_enso_rainfall.py
"""

import _setup  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np

from impact_model.climate import fit_teleconnection, seasonal_record

# --- Things you can change -------------------------------------------------
LABEL_SEASONS = "El Nino"    # label these seasons on the scatter: "El Nino", "La Nina", "all" or "none"
FILENAME = "fig2_enso_rainfall.png"
# ---------------------------------------------------------------------------

record = seasonal_record()
fit = fit_teleconnection()
print("Fitted relationship:", fit.summary())

fig, (ax, ax_time) = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={"width_ratios": [1, 1.4]})

for phase, colour in _setup.PHASE_COLOURS.items():
    rows = record[record["phase"] == phase]
    ax.scatter(rows["relative"], rows["rainfall"], color=colour, label=f"{phase} ({len(rows)})",
               edgecolor="k", lw=0.4, zorder=3)
x = np.linspace(record["relative"].min() - 0.2, record["relative"].max() + 0.2, 50)
lines = fit.bootstrap_intercepts[:, None] + fit.bootstrap_slopes[:, None] * x[None, :]
ax.fill_between(x, *np.percentile(lines, [2.5, 97.5], axis=0), color="0.6", alpha=0.3,
                label="95% CI for fitted lines")
ax.plot(x, fit.predict(x), color="k", lw=1.5, label="Fitted line")
for season, row in record.iterrows():
    if LABEL_SEASONS == "all" or row["phase"] == LABEL_SEASONS:
        ax.annotate(_setup.season_label(season), (row["relative"], row["rainfall"]),
                    fontsize=7, xytext=(3, 3), textcoords="offset points")
ax.set_xlabel("DJF relative Nino 3.4 (°C)")
ax.set_ylabel("Nov-Mar rainfall (mm)")
ax.set_title(r"R^2 = f"{fit.r**2:.2f}, p = {fit.p_value:.5f}, slope {fit.slope:+.0f} mm per °C")
ax.legend(fontsize=8)

anomaly = record["rainfall"] - record["rainfall"].mean()
ax_time.bar(record.index, anomaly, color=np.where(anomaly < 0, "#d35400", "#2e86c1"), alpha=0.7)
ax_time.set_ylabel("Nov-Mar rainfall anomaly (mm)")
twin = ax_time.twinx()
twin.plot(record.index, record["relative"], color="k", marker="o", ms=3, lw=1)
twin.axhline(0.5, color=_setup.PHASE_COLOURS["El Nino"], ls="--", lw=0.8)
twin.axhline(-0.5, color=_setup.PHASE_COLOURS["La Nina"], ls="--", lw=0.8)
twin.set_ylabel("DJF relative Nino 3.4 (°C, black line)")
twin.invert_yaxis()   # inverted so that El Nino and below-average rain both point down
ax_time.set_xlabel("Season (planting year)")
ax_time.set_title("Through time (index axis inverted)")
fig.tight_layout()
_setup.save(fig, FILENAME)

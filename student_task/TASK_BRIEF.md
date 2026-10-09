# EGS4030/5030S — Climate impact modelling assignment

**Set:** guest lecture on climate impact modelling
**Weighting:** to be confirmed by the course convenor
**Submission:** one PDF report of no more than 2000 words plus figures, and your
modified code

---

## The situation

You work for a provincial department of agriculture. It is mid-October 2026.
NOAA's Climate Prediction Center has the ENSO alert system at El Niño Advisory.
As of its 8 October discussion, Niño 3.4 had reached +2.1 °C in September, with
an 83% chance that October–December would exceed any event since 1950. Planting
in the summer-rainfall zone is four to six weeks away. Your director asks a
simple question:

> *Should we be warning maize farmers, and if so, which ones?*

Your job is to answer that with an impact model rather than with an index, and
to be honest about how much confidence your answer deserves. "Probably a bad
season" is not an answer. Neither is a single number with no uncertainty
attached to it.

---

## What you are given

The `impact_model` package, which runs a complete chain from observed ocean
state to crop yield:

- a daily soil water balance following FAO-56
- a stage-weighted yield response following FAO-33
- SPI and SPEI for comparison
- 76 years of observed DJF Niño 3.4, and 41 years of SON Dipole Mode Index
- a forward scenario facility, so you can run seasons that have not happened

Everything runs on a laptop in seconds. Start with:

```bash
python scripts/check_install.py
python scripts/run_demo.py --site limpopo --observed
python scripts/run_demo.py --site limpopo --scenario 2.5
streamlit run app.py
```

If Python will not install, the dashboard is also hosted at
<https://msovara-egs4030-drought-impact-app-ylw3zh.streamlit.app/>.

---

## Core tasks

Each student is assigned **one site** and **one crop** from the table circulated
separately, so no two reports are the same.

### Task 1 — Understand your system (20%)

Run a single season at your assigned site under normal rainfall, and again at
−40%. Using the stage table and the daily water balance plot, explain **where**
in the growing season your crop lost yield and **why** the loss was concentrated
there. Refer to the crop coefficient curve, the rooting depth, the soil's
available water capacity and the yield response factor.

Do not simply report that a drier season gives a lower yield. Explain the
mechanism.

### Task 2 — Timing against totals (20%)

Construct an experiment that isolates the effect of rainfall *timing* from
rainfall *total*. Use the ensemble facility in `sensitivity_sweep`, or write
your own driver.

Report the range of yields you obtain at a fixed seasonal rainfall total, and
identify the characteristic of the wet-day sequence that separates the good
outcomes from the bad ones. Support your answer with at least one figure of your
own construction.

### Task 3 — Index against impact (20%)

Compare SPI3 with your modelled yield across the observed record.

- How much of the yield variance does SPI3 explain at your site?
- Identify every season in the worst yield quartile that SPI3 would **not** have
  classified as at least a moderate drought, and explain what happened in each.
- Would SPEI3 have performed better? Test it rather than speculating, and
  explain the result in terms of what SPEI adds.

Conclude with a recommendation: if the department could monitor only one
quantity, which should it be, and what would it miss?

### Task 4 — Which ocean should the department watch? (20%)

The model can be driven by either ENSO or the IOD. Switch between them with
`--driver` on the command line, or in the dashboard sidebar.

Restrict both to the years they have in common, then answer:

- Which index is the better predictor of modelled yield at **your** site? Support
  this with a correlation and a significance test, not an impression.
- The two indices are correlated at about r = 0.61. What does that do to your
  ability to attribute a bad season to one of them rather than the other?
- ENSO peaks in DJF, during the growing season. The IOD peaks in SON, which is
  now. Which property matters more to a department that has to issue a warning
  in October, and why is that not the same question as which index correlates
  better?

Then run the forward scenario at the value CPC is forecasting, and report the
resulting distribution of harvests rather than its mean alone. State the
probability you would attach to a failed harvest at your site, define what you
mean by failed, and say what would have to be true for that number to be wrong.

### Task 5 — Interrogate the weakest assumption (20%)

The link between the ocean index and rainfall at your site is the least
defensible part of the model. It is an assumed sensitivity, not a fitted one, and
`climate.DEFAULT_SENSITIVITY_NOTE` shows exactly how the default was constructed.

Do at least **one** of the following:

**(a) Fit it.** Obtain observed growing-season rainfall for your site from a
reanalysis or station record, and use `climate.fit_sensitivity` to replace the
default. Report the fitted slope, its correlation and its p-value, and rerun the
composite analysis. Does your answer to the director change?

**(b) Bound it.** Treat the sensitivity as unknown and sweep it across a
plausible range. Determine the value at which the El Niño yield signal becomes
indistinguishable from natural variability, and state whether the literature
supports a sensitivity above or below that value.

**(c) Break it.** Design a test that would reveal the model giving a confidently
wrong answer, run it, and report what you found.

Whichever you choose, finish with a direct statement of how much weight the
director should place on your recommendation, and why.

---

### Task 6 — How good does the weather data have to be? (bonus, up to 10%)

The dashboard's sixth tab shows the verified skill of
[Mvula v5](https://github.com/msovara/lapai-forecast-africa), a lightweight
African weather model, and what its temperature error does to the impact
prediction.

Read the skill table carefully before you use it. Its four rows are **not**
forecast lead times: every one is a single 6-hour step from a fresh ERA5
analysis, and what separates them is the time of day. The error is a damped
daily heating cycle, not a uniform cold bias.

Then, for **your** site and crop:

- Determine the largest error in the daily temperature *range* the driving data
  could carry before your recommendation to the director would change. State
  that threshold as a number in degrees.
- Do the same for a uniform temperature offset. The two thresholds will not be
  the same. Explain why, in terms of the Hargreaves–Samani formula.
- The published RMSE for the afternoon step is 7.8 °C. Could you have predicted
  the size of the yield error from that number alone? If not, what would you
  have needed instead?

Finish with the question it raises: is a weather model "good enough" a property
of the weather model, or of something else?

Note that this is a sensitivity experiment rather than a real coupling. You
cannot drive a 140-day season with a 6-hour step, the Tmax and Tmin biases are
inferred from six-hourly samples rather than measured, and Mvula does not
predict rainfall at all. Say so in your answer.

---

## Extension for 5030S students

Replace the stochastic weather generator with observed daily ERA5 or station
data for your site, and rerun Tasks 1 and 3. Quantify how much of your original
conclusion was an artefact of the generator rather than a property of the
climate. Comment specifically on whether the generator's treatment of dry-spell
length was adequate.

---

## What earns marks

- **Mechanism over description.** "Yield fell because rainfall fell" earns
  little. "Yield fell because a 12-day dry spell coincided with silking, when Ky
  is 1.5 and the root zone had already been drawn below RAW" earns a great deal.
- **Evidence you generated yourself.** Figures from your own runs, not
  screenshots of the dashboard.
- **Honest uncertainty.** A report that states clearly what it cannot conclude
  is worth more than one that overclaims.
- **Reproducibility.** Your code should run. Include the commands.

## What loses marks

- Reporting model output to three decimal places as though it were measured
- Treating the modelled yields as predictions of actual tonnage
- Ignoring the sample size when compositing seven positive IOD seasons
- Presenting the scenario as a forecast of the 2026/27 harvest
- Any claim about the real world that rests entirely on the unfitted
  teleconnection assumption

---

## A note on the model's limits

This model has no nutrients, no pests, no lateral flow, no farmer decisions and
no spatial extent. Real yield gaps in southern Africa are frequently set by
nitrogen availability and planting date rather than by water.

You are not being asked to pretend otherwise. You are being asked to work out
what a deliberately simple model can and cannot tell you, which is the central
skill in impact modelling.

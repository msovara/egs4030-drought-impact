# EGS4030/5030S: ENSO and maize in the Mopani district

**Practical assignment following the guest lecture on climate impact modelling**

**Total:** 100 marks 

**Submission:** one PDF report of approximately 1300 words (EGS4030S) to 1500 words (5030S), the requested figures and your modified your code 

**DUE** With portfolio submission (no feedback submission for this task)

---

## The situation

It is mid-October 2026. A strong El Niño is developing in the tropical
Pacific. It started already in June 2026.  The seasonal forecasts from all major seasonal forecasting
centres suggest it will reach or approach record strength by the start of 2026/27 Austral (Southern Hemisphere) summer. In the
summer-rainfall region of South Africa, maize planting generally occurs between late October and mid-December.

Imagine you are asked by the Limpopo Department of Agriculture and Land Reform:

> *Should we be warning dryland maize farmers in the Mopani district about the
> coming season, and if so, how confidently?*

In this assignment you use a simple crop model to work towards an answer. The
aim is to propose a reasonable range of plausible outcomes, and to demonstrate an understanding of where the uncertainty in that range
comes from.

---

## What the model does

The model follows a chain of steps from the Pacific Ocean to the crop:

1. **The ENSO index.** The state of El Niño-Southern Oscillation (ENSO) is summarised by the relative Niño 3.4
   index (see [the Copernicus discussion on using a relative Niño index] (https://doi.org/10.21957/d05ccfe150)), averaged over December to February (DJF). It is calculated from ERA5
   sea surface temperatures in the same way as the index in the [C3S seasonal forecast plots](https://climate.copernicus.eu/charts/packages/c3s_seasonal/products/c3s_seasonal_plume_mm?area=rel_nino34&base_time=202610010000&type=plumepercentiles).
2. **Mopani District rainfall.** November to March rainfall over the dryland maize areas
   of the Mopani district comes from ERA5, from 1979 to the present. The link
   between the index and this rainfall is fitted from the historical record, estimate from the ERA5 reanalysis area average.
3. **Soil water.** A daily soil water balance tracks how much water is
   available to the crop's roots.
4. **Maize yield.** The crop's yield is reduced when it cannot get enough
   water, and more so at some growth stages than others.

Yields are given as a percentage of what the crop would produce with no water
shortage. Please treat them that way and not as predictions of tonnes per
hectare (see "A note on the model's limits").

<!--### A short primer on soil water and maize -- produced by Claude, currently not included in task description

You are not expected to have studied soil physics or crop physiology. The
following, together with the lecture, is all you need for this assignment.

**The soil as a bucket.** Think of the soil around the roots as a bucket. Rain
fills it, although some runs off the surface in heavy storms. The crop empties
it by drawing up water and losing it through its leaves (transpiration). When
the bucket is full, extra water drains away below the roots. Sandy soils make
small buckets, and loams make larger ones. As the roots grow deeper during the
season, the bucket gets bigger.

**Water stress.** While the bucket is reasonably full, the crop can take up as
much water as the weather demands. Once it falls below a threshold (in this
model, when a little over half of the available water has been used), the crop
cannot draw water fast enough. It closes the pores in its leaves, uses less
water than it needs, and grows less. In the model, the shortfall between the
water the crop needed and the water it actually used is what reduces yield.

**Why timing matters.** Maize is most sensitive to water shortage around
flowering, when the tassels shed pollen and the silks must be fertilised for
kernels to form. A shortage at this stage reduces the number of kernels, and the
plant cannot make up for it later. A shortage of the same size earlier in the
season costs much less. In the model this is represented by a yield response
factor, Ky, which is 1.5 around flowering compared with 0.4 during early growth.
A dry spell of two or three weeks in February, when a crop planted in late
November is flowering, can therefore matter more than a
dry December.-->

### Three ideas to keep in mind

These run through the whole assignment:

- **Mechanisms matter.** Understand the physical reasons why El Niño affects
  rainfall over north-eastern South Africa, and why rainfall affects maize,
  to inform your interpretation of statistical relationships.
- **An ENSO index is not an impact.** The index describes the ocean state in a particular area. What
  happens to a maize crop in Mopani depends on several further steps, each of
  which adds variation.
- **A strong El Niño shifts the odds.** It makes a poor season more likely, but
  it does not decide the outcome of any single season.

---

## Setting up

Work in WSL with the miniforge/conda installation you have. The
repository includes an `environment.yml` file, which builds a new conda environment
called `impact` with every package from conda-forge. The ERA5 data the model
needs are already in the repository, so you do not need a Copernicus account to download and access them.

Create the environment once, from the repository root:

```bash
git clone https://github.com/msovara/egs4030-drought-impact.git
cd egs4030-drought-impact
conda env create -f environment.yml
```

Then, at the start of each session:

```bash
conda activate impact
python scripts/check_install.py
```

The check takes a few seconds and ends with a line saying whether your machine
is ready. A `FAIL` means the model will not run, so please sort that out first
(ask if you are stuck). A `WARN` about a package means the model still works,
and the message tells you how to fix it.

### The dashboard and the figure templates

There are two ways to use the model.

- **The dashboard**, for exploring: run `streamlit run app.py` in your terminal from the directory that you have cloned the GitHub repository to and open the
  address it prints (usually <http://localhost:8501>) in your web browser.
  Its tabs follow the task outline below.
- **The figure templates**, for your report: one script per figure, in
  `student_task/templates/`. Each runs as it is and saves a PNG to
  `student_task/figures/`. The settings you might want to change, such as which
  seasons to plot, are at the top of each script. You are welcome to change the
  figures further, if you feel it helps you communicate the message better.

```bash
python student_task/templates/fig1_one_season.py
python student_task/templates/fig2_enso_rainfall.py
python student_task/templates/fig3_rainfall_to_yield.py
python student_task/templates/fig4_cascade.py
python student_task/templates/fig5_planting_dates.py   # 5030S extension
```

For a quick text summary, `python scripts/run_demo.py --help` lists some
command-line views.

If your environment will not build, the hosted dashboard lets you follow the
practical in the meantime. You will still need a working environment for the
figures in your report.

---

## Report structure 

| Section | Name | Marks available | Suggested word count |
|---|---|---|---|
| 1 | Introduction | 20 | 300 words |
| 2 | Data and methodology | 20 | 300 |
| 3 | Results - general | 15 |150-200|
| 4 | Results & discussion - 2026/27 | 30 | 300 - 450 |
| 5 | Concluding message to the Dept | 15 | 250 |
| | **Total** | **100** | 1300-1500|

The suggested word counts are guides to the depth expected, not strict limits.

### Introduction: points to consider

**(a)** Justify briefly why the Department should be considering potential impacts of the developing El Niño conditions in the tropical
Pacific. In this description, note the observed relationship between Limpopo rainfall and ENSO and the sensitivity of rain-fed maize to climate variability. Explain briefly why it is justified under a climate change regime to prefer a *relative* Niño 3.4 index rather than the traditional one. 


### Task 2: What the historical record shows (20 marks)

Run `fig2_enso_rainfall.py`. It plots the DJF relative Niño 3.4 index against
November to March rainfall over the study area for each season since 1979, and
prints the fitted relationship.

**(a)** Report the fitted slope (in mm/K), its 90% range, the correlation and the p-value. In plain words, how
much of the year-to-year variation in Mopani rainfall is associated with ENSO?

**(b)** Identify the El Niño seasons that had close to or above-median rainfall,
and the seasons with well below-median rainfall that were not El Niño seasons.
Suggest, with reasons, what else might have influenced rainfall in some of
those seasons. You can draw on the lecture and on what you know of other
influences on southern African rainfall.

**(c)** Give two limitations of this evidence. For example, consider the number
of seasons and of strong El Niño events, the fact that ERA5 rainfall comes from
a weather model constrained by observations rather than from rain gauges, and
the use of an average over the whole study area.

(About 400 words in total, with Figure 2.)

### Results: General

**(b)** Run `fig1_one_season.py`, which compares the 2015/16 season with
1999/00 by default. You may replace 1999/00 with another season if you prefer.
For each season, describe when during the growing season the crop was short of
water, and explain why a shortage around flowering reduced the yield more than
one earlier in the season.  (About 200 words, with Figure 1.)


Run `fig3_rainfall_to_yield.py`.

**(a)** Compare how closely modelled yield follows the ENSO index with how
closely it follows November to March rainfall. Explain the difference in terms
of the chain of steps from ocean to crop.

**(b)** Panel (c) gives every historical season the same November to March
rainfall total, keeping each season's own pattern of wet and dry days. Report
the range of yields this produces. Pick one season with a low yield and one
with a high yield, plot them with `fig1_one_season.py`, and explain the
difference using the timing of rain and dry spells relative to flowering.

**(c)** In two or three sentences, what does this suggest about using a
seasonal rainfall forecast, or an ENSO index on its own, to anticipate effects
on maize?

(About 400 words in total, with Figure 3 and a second version of Figure 1.)

### Task 4: The 2026/27 season as a range of outcomes (30 marks)

**(a) Read the forecast.** Open the
[C3S multi-system plume for the relative Niño 3.4 index](https://climate.copernicus.eu/charts/packages/c3s_seasonal/products/c3s_seasonal_plume_mm?area=rel_nino34&base_time=202610010000&type=plumepercentiles),
initialised on 1 October 2026. Briefly describe what the chart shows: what the
shaded band represents and where the forecasts come from. Read off the band
for December, January and February, and take the average of each edge as your
DJF range. The index in the model is calculated in the same way as the C3S
one, with anomalies relative to 1993–2016 and the same scaling, so the two can
be compared directly. If your range differs from the one the lecturer has
entered, set `FORECAST_RANGE` at the top of `fig4_cascade.py` to your own
values and say which you used.

**(b) Run the cascade.** Run `fig4_cascade.py`. The figure shows the spread of
modelled yields as sources of uncertainty are added one at a time:

1. the range of the ENSO forecast;
2. the uncertain response of Mopani rainfall to ENSO, including the scatter of
   real seasons about the fitted line;
3. the day-to-day sequence of rainfall within the season;
4. differences in soil and in the crop's sensitivity to water shortage.

The last two boxes are for comparison: the same full calculation for a neutral
ENSO season, and the model run on the actual seasons since 1979. A "poor"
season is one in the worst third of the historical seasons.

Describe how the range of outcomes changes at each step, and which step adds
the most spread. Report the median and the chance of a poor season under the
forecast, and compare them with the neutral case.

**(c) How firm are the numbers?** Change `SEED` and run the script again. How
much do the results change? What does this suggest about how precisely you
should report them? Then look at the list of past seasons with an index inside
your forecast range. How many are there, and what does that mean for how far
the fitted relationship is being stretched?

**(d) The wider cascade.** Uncertainty about local impacts builds up at every
link in the chain, from the ocean through the regional atmosphere and the
weather within the season to the soil and the crop. Sketch this cascade (a
hand-drawn diagram is fine) or describe it in words. Name at least two sources
of uncertainty the model does *not* include, and say whether you would expect
each to widen, narrow or shift the range of outcomes.

(About 600 words in total, with Figure 4 and your sketch if you make one.)

### Task 5: A note to the director (15 marks)

Write a short note (no more than 300 words) answering the director's question
in plain language for someone who is not a climate scientist. It should say:

- whether you would issue a warning, to whom, and how confident you are;
- what the analysis can and cannot tell the department;
- what new information over the next two or three months could change your
  advice.

Use the language of likelihood ("more likely than usual", "about a two in three
chance") rather than certainty. Round any numbers sensibly.

### Extension for EGS5030S students: planting date (15 marks)

Planting date is one of the few decisions a dryland farmer can adjust. Run
`fig5_planting_dates.py`, which repeats the full cascade for early (1 November),
standard (25 November) and late (20 December) planting, under the forecast and
under a neutral season.

- Does planting date change the chance of a poor season under the forecast? Is
  the effect larger or smaller than under neutral conditions?
- Explain the result using where flowering falls in each case relative to the
  rainfall season and to typical dry spells. Figure 1, run with a different
  `PLANTING`, may help.
- Discuss whether this could be turned into practical advice, bearing in mind
  that planting in practice depends on the onset of the rains, seed and labour,
  and on things the model leaves out.

(About 500 words, with Figure 5.)

---

## What to submit

- **One PDF report.** About 1 500 words of text for EGS4030 and about 2 000 for
  EGS5030S, plus figures. Number your answers to match the tasks.
- **Your code.** Any template scripts you changed, and a short list of the
  commands you ran to produce each figure, so that someone else could repeat
  your results.

## What the marking looks for

- **Explanation of mechanisms.** For example, "yield fell mainly because a
  three-week dry spell coincided with flowering, after the soil water had
  already dropped below the stress threshold" shows more understanding than
  "yield fell because rainfall was low".
- **Evidence from your own runs.** Figures and numbers you produced, rather than
  screenshots of the dashboard.
- **Honesty about uncertainty.** A clear statement of what the analysis cannot
  conclude is worth more than a confident claim it cannot support.
- **Sensible precision.** Modelled yields reported to the nearest 5 or 10%,
  and no more decimal places than the evidence supports.
- **Clear writing.** Especially in Task 5.

Common pitfalls are presenting the cascade as a forecast of the 2026/27
harvest, treating the modelled percentages as tonnes per hectare, and reading
too much into a handful of strong El Niño seasons.

---

## A note on the model's limits

The model deliberately leaves out a great deal: nutrients, pests and diseases,
weeds, differences in soil and rainfall across the district, irrigation, and
nearly all farmer decisions. In southern Africa, yields on smallholder farms are
often limited more by nitrogen and management than by water. The relationship
between ENSO and rainfall is a straight line fitted to fewer than fifty seasons,
and ERA5 rainfall has its own errors.

None of this makes the exercise pointless. Working out what a simple model can
and cannot tell you is a large part of impact modelling in practice.

---

## Suggested reading

- Lindesay, J.A. (1988). South African rainfall, the Southern Oscillation and a
  Southern Hemisphere semi-annual cycle. *Journal of Climatology*, 8(1), 17–30.
- Reason, C.J.C. and Jagadheesha, D. (2005). A model investigation of recent
  ENSO impacts over southern Africa. *Meteorology and Atmospheric Physics*, 89,
  181–205.
- Hoell, A., Funk, C., Magadzire, T., Zinke, J. and Husak, G. (2015). El
  Niño–Southern Oscillation diversity and Southern Africa teleconnections during
  austral summer. *Climate Dynamics*, 45, 1583–1599.
- Archer, E.R.M., Landman, W.A., Tadross, M.A., Malherbe, J., Weepener, H.,
  Maluleke, P. and Marumbwa, F.M. (2017). Understanding the evolution of the
  2014–2016 summer rainfall seasons in southern Africa: key lessons. *Climate
  Risk Management*, 16, 22–28.
- van Oldenborgh, G.J., Hendon, H., Stockdale, T., L'Heureux, M., Coughlan de
  Perez, E., Singh, R. and van Aalst, M. (2021). Defining El Niño indices in a
  warming climate. *Environmental Research Letters*, 16(4), 044003.
- L'Heureux, M.L., Tippett, M.K., Wheeler, M.C., Nguyen, H., Narsey, S.,
  Johnson, N., Hu, Z.-Z., Watkins, A.B., Lucas, C., Ganter, C., Becker, E.,
  Wang, W. and Di Liberto, T. (2024). A relative sea surface temperature index
  for classifying ENSO events in a changing climate. *Journal of Climate*,
  37(4), 1197–1211.
- For the crop water balance, if you want more detail: Allen, R.G., Pereira,
  L.S., Raes, D. and Smith, M. (1998). *Crop evapotranspiration: guidelines for
  computing crop water requirements*. FAO Irrigation and Drainage Paper 56.
  Chapters 1 and 8 are the most relevant.

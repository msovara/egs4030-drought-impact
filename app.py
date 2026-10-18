# -*- coding: utf-8 -*-
"""
EGS4030/5030S: ENSO and maize in the Mopani district, Limpopo.

Run with:
    streamlit run app.py

The tabs follow the practical: one season in detail, the role of rainfall
timing, what the historical record shows about ENSO and Mopani rainfall, and
finally the 2026/27 season as a range of outcomes.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent))

from impact_model.climate import (  # noqa: E402
    C3S_FORECAST,
    fit_teleconnection,
    forecast_djf_range,
    load_enso_index,
    rainy_season_totals,
)
from impact_model.config import (  # noqa: E402
    CASCADE_FLOWERING_KY,
    CASCADE_SOILS,
    DEFAULT_PLANTING,
    DEFAULT_SOIL,
    EL_NINO_THRESHOLD,
    INDEX_BASE_PERIOD,
    INDEX_SCALING_PERIOD,
    LA_NINA_THRESHOLD,
    MAIZE,
    PLANTING_DATES,
    SOILS,
    STAGE_LABELS,
    STAGE_ORDER,
    STUDY_AREA,
)
from impact_model.data import MissingDataError, data_summary  # noqa: E402
from impact_model.experiment import (  # noqa: E402
    CASCADE_STAGES,
    run_cascade,
    run_historical,
    run_one_season,
    same_total_experiment,
)

st.set_page_config(
    page_title="ENSO and maize in Mopani | EGS4030/5030S",
    page_icon="🌽",
    layout="wide",
)

PHASE_COLOURS = {"El Nino": "#c0392b", "Neutral": "#909497", "La Nina": "#2471a3"}
PHASE_NAMES = {"El Nino": "El Niño", "Neutral": "Neutral", "La Nina": "La Niña"}
STAGE_COLOURS = {"initial": "#a9dfbf", "development": "#7dcea0", "mid": "#f5b041", "late": "#d7bde2"}

# Red, amber, green stops for table shading. Interpolated by hand rather than
# through a matplotlib colormap: pandas' background_gradient needs matplotlib,
# which is 60 MB of dependency for two shaded columns and one more thing to go
# wrong on a student laptop or a hosted deployment.
_SHADE_STOPS = ((231, 76, 60), (244, 208, 63), (88, 171, 110))


def shade_column(series, vmin=None, vmax=None, reverse=False):
    """
    Red-to-green background shading for one column of a Styler.

    Written for `Styler.apply`, which takes a Series and returns one CSS string
    per row. That API is stable across pandas 2.x, unlike `Styler.map`, which
    only arrived in 2.1 and replaced a now-deprecated `applymap`.
    """
    values = pd.to_numeric(series, errors="coerce")
    low = values.min() if vmin is None else vmin
    high = values.max() if vmax is None else vmax
    span = high - low

    styles = []
    for value in values:
        if pd.isna(value):
            styles.append("")
            continue

        fraction = 0.5 if span <= 0 else float(np.clip((value - low) / span, 0.0, 1.0))
        if reverse:
            fraction = 1.0 - fraction

        # Two linear segments: red to amber below the midpoint, amber to green above.
        if fraction <= 0.5:
            start, end, local = _SHADE_STOPS[0], _SHADE_STOPS[1], fraction * 2.0
        else:
            start, end, local = _SHADE_STOPS[1], _SHADE_STOPS[2], (fraction - 0.5) * 2.0

        rgb = tuple(round(a + (b - a) * local) for a, b in zip(start, end))
        # Pale enough that the cell text stays readable at any point on the ramp.
        styles.append(f"background-color: rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, 0.45)")
    return styles


def show_table(frame, formats=None, shade=None, hide_index=True):
    """
    Render a dataframe without letting pandas Styler take the whole app down.

    Styler needs jinja2, which is an optional pandas extra and is not always
    present on a Streamlit Cloud image. Every tab in this script runs on every
    rerun, so a missing import in Tab 1 would red-screen Tab 2. Format and
    shade when we can; fall back to a plain table when we cannot.
    """
    try:
        styler = frame.style
        if formats:
            styler = styler.format(formats)
        for column, kwargs in (shade or {}).items():
            if column in frame.columns:
                styler = styler.apply(shade_column, subset=[column], **kwargs)
        st.dataframe(styler, width="stretch", hide_index=hide_index)
        return
    except Exception:
        pass

    config = {}
    for column, spec in (formats or {}).items():
        if column in frame.columns:
            config[column] = st.column_config.NumberColumn(format=_printf_format(spec))
    st.dataframe(frame, width="stretch", hide_index=hide_index, column_config=config)


def _printf_format(pandas_spec: str) -> str:
    """Turn a pandas Styler format, e.g. '{:.2f}', into a printf / d3 string."""
    inner = pandas_spec.strip()
    if inner.startswith("{") and inner.endswith("}") and ":" in inner:
        inner = inner[inner.index(":") + 1 : -1]
    return f"%{inner}" if not inner.startswith("%") else inner



def season_label(season: int) -> str:
    return f"{season}/{(season + 1) % 100:02d}"


# --------------------------------------------------------------------------
# Cached model runs
# --------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def cached_history(soil, planting):
    return run_historical(soil, planting)


@st.cache_data(show_spinner=False)
def cached_season(season, soil, planting, factor):
    result, weather = run_one_season(season, soil, planting, rain_factor=factor)
    return result, weather


@st.cache_data(show_spinner=False)
def cached_same_total(total, soil, planting):
    return same_total_experiment(total, soil, planting)


@st.cache_resource(show_spinner=False)
def cached_fit():
    return fit_teleconnection()


@st.cache_resource(show_spinner=False)
def cached_cascade(low, high, members, soil, planting, seed):
    return run_cascade((low, high), members=members, soil_key=soil, planting=planting, seed=seed)


# --------------------------------------------------------------------------
# Data, and the sidebar
# --------------------------------------------------------------------------

try:
    summary = data_summary()
    enso = load_enso_index()
    rain_totals = rainy_season_totals()
except MissingDataError as error:
    st.error(str(error))
    st.stop()

st.sidebar.title("Model setup")
soil_key = st.sidebar.selectbox(
    "Soil", list(SOILS), index=list(SOILS).index(DEFAULT_SOIL),
    format_func=lambda k: f"{SOILS[k].name} ({SOILS[k].available_water_capacity:.0f} mm/m)",
    help="The number is the plant-available water each metre of soil can hold.",
)
planting = st.sidebar.selectbox(
    "Planting date", list(PLANTING_DATES), index=list(PLANTING_DATES).index(DEFAULT_PLANTING),
    format_func=lambda k: f"{k.capitalize()} ({pd.Timestamp(2000, *PLANTING_DATES[k]):%d %b})",
)
st.sidebar.divider()
st.sidebar.markdown(f"**Study area:** {STUDY_AREA.name}")
st.sidebar.caption(
    f"{abs(STUDY_AREA.lat_north):.2f}–{abs(STUDY_AREA.lat_south):.2f}°S, "
    f"{STUDY_AREA.lon_west:.2f}–{STUDY_AREA.lon_east:.2f}°E. {STUDY_AREA.note}"
)
st.sidebar.caption(
    f"Weather: ERA5, {summary['daily_start']:%b %Y} to {summary['daily_end']:%b %Y}. "
    f"Sea surface temperature: ERA5, to {summary['sst_end']:%b %Y}."
)
st.sidebar.link_button("C3S relative Niño 3.4 plume", C3S_FORECAST["url"])

history = cached_history(soil_key, planting)

st.title("ENSO and maize in the Mopani district")
st.caption(
    "A small crop water-balance model driven by ERA5 weather, used to explore how "
    "El Niño affects dryland maize in Limpopo, and how uncertain that effect is."
)
st.link_button("C3S relative Niño 3.4 plume", C3S_FORECAST["url"])

tab_season, tab_timing, tab_record, tab_ahead, tab_model = st.tabs([
    "1. One season",
    "2. Same rain, different harvests",
    "3. ENSO and Mopani rainfall",
    "4. The 2026/27 season",
    "5. About the model",
])


# --------------------------------------------------------------------------
# Tab 1: one season
# --------------------------------------------------------------------------

with tab_season:
    st.subheader("Inside one growing season")
    st.markdown(
        "Choose a past season to see how its rainfall filled and drained the root "
        "zone, and when the crop ran short of water. The rainfall slider scales that "
        "season's rain up or down while keeping the timing of each rain event."
    )
    options = list(history.index)
    default = options.index(2015) if 2015 in options else len(options) - 1
    controls = st.columns([2, 2])
    with controls[0]:
        season = st.selectbox(
            "Season", options, index=default,
            format_func=lambda s: (f"{season_label(s)}  ·  {PHASE_NAMES[history.loc[s, 'phase']]} "
                                   f"({history.loc[s, 'relative_index']:+.1f} °C)  ·  "
                                   f"{history.loc[s, 'rainfall']:.0f} mm"),
        )
    with controls[1]:
        factor = st.slider("Scale this season's rainfall (%)", 50, 150, 100, 5) / 100

    result, weather = cached_season(season, soil_key, planting, factor)
    daily = result.daily

    metrics = st.columns(4)
    metrics[0].metric("Rain, planting to harvest", f"{result.season_rainfall:.0f} mm")
    metrics[1].metric("Crop water demand met",
                      f"{result.season_et_actual / result.season_et_potential:.0%}")
    metrics[2].metric("Days with water stress", f"{result.water_stress_days}")
    metrics[3].metric("Modelled yield", f"{result.relative_yield:.0%} of potential")

    figure = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07, row_heights=[0.28, 0.38, 0.34],
        subplot_titles=("Daily rainfall", "Water in the root zone, and the level below which the crop is stressed",
                        "Crop water demand, and what the crop actually used"),
    )
    figure.add_trace(go.Bar(x=daily.index, y=daily["precip"], name="Rainfall", marker_color="#2e86c1"), 1, 1)
    figure.add_trace(go.Scatter(x=daily.index, y=daily["total_available_water"], name="Full",
                                line=dict(color="#5d6d7e", dash="dot")), 2, 1)
    figure.add_trace(go.Scatter(x=daily.index,
                                y=daily["total_available_water"] - daily["readily_available_water"],
                                name="Stress threshold", line=dict(color="#e67e22", dash="dash")), 2, 1)
    figure.add_trace(go.Scatter(x=daily.index, y=daily["soil_water"], name="Soil water",
                                line=dict(color="#1a5276", width=2.5)), 2, 1)
    figure.add_trace(go.Scatter(x=daily.index, y=daily["et_potential"], name="Demand",
                                line=dict(color="#a04000", dash="dot")), 3, 1)
    figure.add_trace(go.Scatter(x=daily.index, y=daily["et_actual"], name="Actual use",
                                line=dict(color="#196f3d", width=2), fill="tonexty",
                                fillcolor="rgba(192,57,43,0.22)"), 3, 1)
    for stage in STAGE_ORDER:
        days = daily.index[daily["stage"] == stage]
        for row in (1, 2, 3):
            label = {"annotation_text": STAGE_LABELS[stage], "annotation_position": "top left",
                     "annotation_font_size": 10} if row == 1 else {}
            figure.add_vrect(x0=days[0], x1=days[-1], fillcolor=STAGE_COLOURS[stage], opacity=0.15,
                             line_width=0, row=row, col=1, **label)
    figure.update_layout(height=700, hovermode="x unified", margin=dict(t=60, b=30),
                         legend=dict(orientation="h", y=1.06, x=0))
    figure.update_yaxes(title_text="mm", row=1, col=1)
    figure.update_yaxes(title_text="mm", row=2, col=1)
    figure.update_yaxes(title_text="mm/day", row=3, col=1)
    st.plotly_chart(figure, width="stretch")

    st.markdown("#### Where the yield was lost")
    st.caption(
        "For each growth stage: the share of the crop's water demand that was not met, "
        "and how strongly that shortfall reduces yield (Ky). Maize is most sensitive "
        "around flowering, so the same shortfall costs more there than earlier in the season."
    )
    table = result.stage_summary.copy()
    table["Stage"] = table["stage"].map(STAGE_LABELS)
    table = table[["Stage", "days", "rainfall", "et_potential", "et_actual", "deficit_ratio", "ky",
                   "stage_yield_factor"]].rename(columns={
        "days": "Days", "rainfall": "Rain (mm)", "et_potential": "Demand (mm)", "et_actual": "Used (mm)",
        "deficit_ratio": "Shortfall", "ky": "Ky", "stage_yield_factor": "Yield multiplier"})
    show_table(table, formats={"Rain (mm)": "{:.0f}", "Demand (mm)": "{:.0f}", "Used (mm)": "{:.0f}",
                               "Shortfall": "{:.0%}", "Ky": "{:.1f}", "Yield multiplier": "{:.2f}"},
               shade={"Yield multiplier": dict(vmin=0.0, vmax=1.0)})


# --------------------------------------------------------------------------
# Tab 2: timing against totals
# --------------------------------------------------------------------------

with tab_timing:
    st.subheader("The same seasonal rainfall can give very different harvests")
    st.markdown(
        "Here every past season is given the same November to March total, by scaling "
        "its daily rainfall up or down. Each season keeps its own pattern of wet days and "
        "dry spells, so any difference in yield comes from the timing of the rain."
    )
    lo, hi = float(rain_totals.quantile(0.1)), float(rain_totals.quantile(0.9))
    total = st.slider("Nov–Mar rainfall given to every season (mm)", int(lo), int(hi),
                      int(rain_totals.median()), 10)
    same = cached_same_total(float(total), soil_key, planting)
    ordered = same.sort_values("relative_yield")
    bar = go.Figure(go.Bar(
        x=[season_label(s) for s in ordered.index], y=100 * ordered["relative_yield"],
        marker_color=[PHASE_COLOURS[history.loc[s, "phase"]] for s in ordered.index],
        customdata=np.stack([ordered["flowering_rainfall"], ordered["flowering_dry_spell"]], axis=1),
        hovertemplate=("%{x}: %{y:.0f}%<br>rain during flowering %{customdata[0]:.0f} mm"
                       "<br>longest dry spell during flowering %{customdata[1]:.0f} days<extra></extra>"),
    ))
    bar.update_layout(height=420, yaxis_title="Modelled yield (% of potential)",
                      xaxis_tickangle=-90, margin=dict(t=20))
    st.plotly_chart(bar, width="stretch")
    st.caption("Bar colours show the ENSO phase of each season: red El Niño, grey neutral, blue La Niña.")
    columns = st.columns(2)
    for column, title, rows in ((columns[0], "Lowest yields", ordered.head(5)),
                                (columns[1], "Highest yields", ordered.tail(5).iloc[::-1])):
        with column:
            st.markdown(f"**{title}**")
            show_table(
                rows.reset_index().assign(Season=lambda f: f["season"].map(season_label))[
                    ["Season", "relative_yield", "flowering_rainfall", "flowering_dry_spell"]].rename(
                    columns={"relative_yield": "Yield", "flowering_rainfall": "Rain at flowering (mm)",
                             "flowering_dry_spell": "Longest dry spell at flowering (days)"}),
                formats={"Yield": "{:.0%}", "Rain at flowering (mm)": "{:.0f}",
                         "Longest dry spell at flowering (days)": "{:.0f}"},
            )


# --------------------------------------------------------------------------
# Tab 3: the historical record
# --------------------------------------------------------------------------

with tab_record:
    fit = cached_fit()
    st.subheader("What the record since 1979 shows")
    st.markdown(
        "Each point is one season: the December–February relative Niño 3.4 index against "
        "November–March ERA5 rainfall over the study area. The line is fitted to these "
        "seasons; the shaded band shows how much the line changes when it is refitted on "
        "resampled sets of seasons."
    )
    m = st.columns(4)
    m[0].metric("Slope", f"{fit.slope:+.0f} mm per °C", f"{fit.slope_percent:+.0f}% of mean", delta_color="off")
    m[1].metric("Correlation r", f"{fit.r:.2f}")
    m[2].metric("Variance explained (r²)", f"{fit.r_squared:.0%}")
    m[3].metric("Seasons", f"{fit.n}", f"p = {fit.p_value:.3f}", delta_color="off")

    left, right = st.columns(2)
    with left:
        scatter = go.Figure()
        x = np.linspace(history["relative_index"].min() - 0.2, history["relative_index"].max() + 0.2, 60)
        lines = fit.bootstrap_intercepts[:, None] + fit.bootstrap_slopes[:, None] * x[None, :]
        band_lo, band_hi = np.percentile(lines, [5, 95], axis=0)
        scatter.add_trace(go.Scatter(x=np.r_[x, x[::-1]], y=np.r_[band_hi, band_lo[::-1]], fill="toself",
                                     fillcolor="rgba(120,120,120,0.2)", line=dict(width=0),
                                     name="90% range of fitted lines", hoverinfo="skip"))
        scatter.add_trace(go.Scatter(x=x, y=fit.predict(x), line=dict(color="black"), name="Fitted line"))
        for phase, colour in PHASE_COLOURS.items():
            rows = history[history["phase"] == phase]
            scatter.add_trace(go.Scatter(
                x=rows["relative_index"], y=rows["rainfall"], mode="markers", name=PHASE_NAMES[phase],
                marker=dict(color=colour, size=9, line=dict(width=0.5, color="black")),
                text=[season_label(s) for s in rows.index],
                hovertemplate="%{text}: %{x:+.2f} °C, %{y:.0f} mm<extra></extra>"))
        scatter.update_layout(height=430, xaxis_title="DJF relative Niño 3.4 (°C)",
                              yaxis_title="Nov–Mar rainfall (mm)", margin=dict(t=20))
        st.plotly_chart(scatter, width="stretch")
    with right:
        yield_fig = go.Figure()
        for phase, colour in PHASE_COLOURS.items():
            rows = history[history["phase"] == phase]
            yield_fig.add_trace(go.Scatter(
                x=rows["relative_index"], y=100 * rows["relative_yield"], mode="markers",
                name=PHASE_NAMES[phase], marker=dict(color=colour, size=9, line=dict(width=0.5, color="black")),
                text=[season_label(s) for s in rows.index], showlegend=False,
                hovertemplate="%{text}: %{x:+.2f} °C, yield %{y:.0f}%<extra></extra>"))
        r_yield = history["relative_yield"].corr(history["relative_index"])
        yield_fig.update_layout(height=430, xaxis_title="DJF relative Niño 3.4 (°C)",
                                yaxis_title="Modelled yield (% of potential)", margin=dict(t=40),
                                title=dict(text=f"Modelled yield against the index: r = {r_yield:.2f}",
                                           font=dict(size=14)))
        st.plotly_chart(yield_fig, width="stretch")

    st.markdown("#### El Niño seasons in the record")
    st.caption(
        f"Seasons with a DJF relative index of at least +{EL_NINO_THRESHOLD} °C. "
        "Compare their rainfall and modelled yield with the long-term median."
    )
    el_nino = history[history["phase"] == "El Nino"].sort_values("relative_index", ascending=False)
    show_table(
        el_nino.reset_index().assign(Season=lambda f: f["season"].map(season_label))[
            ["Season", "relative_index", "traditional_index", "rainfall", "flowering_dry_spell", "relative_yield"]
        ].rename(columns={"relative_index": "Relative index (°C)", "traditional_index": "Traditional index (°C)",
                          "rainfall": "Nov–Mar rain (mm)", "flowering_dry_spell": "Dry spell at flowering (days)",
                          "relative_yield": "Yield"}),
        formats={"Relative index (°C)": "{:+.2f}", "Traditional index (°C)": "{:+.2f}",
                 "Nov–Mar rain (mm)": "{:.0f}", "Dry spell at flowering (days)": "{:.0f}", "Yield": "{:.0%}"},
        shade={"Yield": dict(vmin=0.0, vmax=1.0)},
    )
    st.caption(
        f"Median of all seasons: {history['rainfall'].median():.0f} mm rainfall, "
        f"{history['relative_yield'].median():.0%} yield. Index anomalies are relative to "
        f"{INDEX_BASE_PERIOD[0]}–{INDEX_BASE_PERIOD[1]}."
    )

    with st.expander("Relative and traditional Niño 3.4 through time"):
        index_fig = go.Figure()
        index_fig.add_trace(go.Scatter(x=enso.index, y=enso["traditional"], name="Traditional",
                                       line=dict(color="#d35400")))
        index_fig.add_trace(go.Scatter(x=enso.index, y=enso["relative"], name="Relative",
                                       line=dict(color="black")))
        index_fig.add_trace(go.Scatter(x=enso.index, y=enso["tropical"], name="Tropical-mean anomaly",
                                       line=dict(color="#7f8c8d", dash="dot")))
        index_fig.update_layout(height=320, yaxis_title="DJF anomaly (°C)", margin=dict(t=20))
        st.plotly_chart(index_fig, width="stretch")
        st.caption(
            "The relative index is the traditional index minus the anomaly of the whole tropical "
            "band, rescaled so that it varies by about as much as the traditional index. Where "
            "the tropics as a whole are unusually warm or cool, the two indices differ."
        )


# --------------------------------------------------------------------------
# Tab 4: the season ahead
# --------------------------------------------------------------------------

with tab_ahead:
    st.subheader("The 2026/27 season as a range of outcomes")
    st.markdown(
        "This is not a forecast of the harvest. It asks: if the DJF relative Niño 3.4 index "
        "falls somewhere in the range suggested by the C3S seasonal forecasts, what range of "
        "yields does the model give, and how does that range build up as more sources of "
        "uncertainty are included?"
    )
    preset = forecast_djf_range()
    inputs = st.columns([1, 1, 1, 1])
    with inputs[0]:
        low = st.number_input("Lower edge of DJF range (°C)", value=preset[0] if preset else None,
                              step=0.1, format="%.2f", placeholder="from the C3S chart")
    with inputs[1]:
        high = st.number_input("Upper edge of DJF range (°C)", value=preset[1] if preset else None,
                               step=0.1, format="%.2f", placeholder="from the C3S chart")
    with inputs[2]:
        members = st.select_slider("Members per box", [100, 200, 300, 500], value=300)
    with inputs[3]:
        seed = st.number_input("Random seed", value=2026, step=1)
    st.caption(
        f"Source: [{C3S_FORECAST['product']}]({C3S_FORECAST['url']}), initialised "
        f"{C3S_FORECAST['initialised']}."
        + (f" Band shown: {C3S_FORECAST['band']}." if C3S_FORECAST.get("band") else "")
    )

    if low is None or high is None:
        st.info("Enter the DJF range you read from the C3S chart to run the experiment.")
    else:
        low, high = sorted((float(low), float(high)))
        with st.spinner("Running the cascade"):
            cascade = cached_cascade(low, high, int(members), soil_key, planting, int(seed))
        table = cascade.stage_summary()

        box = go.Figure()
        labels = [label for _, label in CASCADE_STAGES] + ["Neutral ENSO (all uncertainty)", "Historical seasons"]
        colours = ["#f5b7b1", "#f1948a", "#ec7063", "#cb4335", "#bdc3c7", "#d5dbdb"]
        groups = [cascade.members.loc[cascade.members["stage"] == key, "relative_yield"] for key, _ in CASCADE_STAGES]
        groups += [cascade.neutral["relative_yield"], cascade.historical["relative_yield"]]
        for label, colour, values in zip(labels, colours, groups):
            q = np.percentile(100 * values, [10, 25, 50, 75, 90])
            box.add_trace(go.Box(x=[label], q1=[q[1]], median=[q[2]], q3=[q[3]], lowerfence=[q[0]],
                                 upperfence=[q[4]], fillcolor=colour, line=dict(color="#555"),
                                 name=label, showlegend=False))
        box.add_hline(y=100 * cascade.poor_threshold, line_dash="dash",
                      annotation_text="poor season", annotation_position="top left")
        for label, (_, row) in zip(labels, table.iterrows()):
            box.add_annotation(x=label, y=105, text=f"P(poor) {row['prob_poor']:.0%}", showarrow=False)
        box.update_layout(height=470, yaxis=dict(title="Modelled yield (% of potential)", range=[0, 110]),
                          margin=dict(t=20))
        st.plotly_chart(box, width="stretch")
        st.caption(
            f"Boxes span the 25th to 75th percentile, whiskers the 10th to 90th. A poor season "
            f"is a yield below {cascade.poor_threshold:.0%} of potential, which is the worst third "
            "of the historical seasons, so about one season in three is poor in the historical record."
        )

        show_table(
            table.reset_index().rename(columns={
                "case": "Case", "members": "Members", "p10": "10th", "median": "Median", "p90": "90th",
                "spread_p10_p90": "Spread (10th–90th)", "prob_poor": "P(poor)"}),
            formats={"10th": "{:.0%}", "Median": "{:.0%}", "90th": "{:.0%}",
                     "Spread (10th–90th)": "{:.0%}", "P(poor)": "{:.0%}"},
        )

        with st.expander("What each box adds"):
            st.markdown(
                f"""
1. **ENSO forecast range.** The DJF index is drawn at random from {low:+.2f} to {high:+.2f} °C.
   Rainfall is read off the fitted line in Tab 3, and every member uses the same daily rainfall
   pattern (from {season_label(cascade.reference_season)}, a season with close to median rainfall),
   scaled to that total.
2. **+ Mopani rainfall response.** The fitted line is itself uncertain, and real seasons scatter
   around it. Each member uses a refitted line and adds the scatter of a randomly chosen past season.
3. **+ day-to-day weather.** Each member borrows the daily rainfall pattern of a different past
   season with a broadly similar total, scaled to its own total.
4. **+ soil and crop response.** Each member also draws a soil
   ({", ".join(SOILS[k].name.lower() for k in CASCADE_SOILS)}) and a yield response at flowering
   (Ky of {", ".join(f"{k:.1f}" for k in CASCADE_FLOWERING_KY)}).

The neutral case runs step 4 with the index between {LA_NINA_THRESHOLD:+.1f} and
{EL_NINO_THRESHOLD:+.1f} °C. Several sources of uncertainty are not included at all; see Tab 5.
"""
            )

        within = cascade.historical_in_range()
        if within.empty:
            st.warning(
                "No past season had an index inside this range, so the fitted line is being "
                "extended beyond the data it was fitted to."
            )
        else:
            st.markdown(
                "**Past seasons with an index in this range:** "
                + "; ".join(f"{season_label(s)} ({r['relative_index']:+.2f} °C, {r['rainfall']:.0f} mm, "
                            f"yield {r['relative_yield']:.0%})" for s, r in within.iterrows())
            )


# --------------------------------------------------------------------------
# Tab 5: the model
# --------------------------------------------------------------------------

with tab_model:
    st.subheader("What is in the model, and what is not")
    st.markdown(
        f"""
**The chain.** Sea surface temperature → DJF relative Niño 3.4 → Nov–Mar rainfall over the
study area → daily soil water → maize yield.

**Data.** ERA5 reanalysis (Copernicus Climate Change Service): daily rainfall and maximum and
minimum temperature averaged over {STUDY_AREA.name}, and monthly sea surface temperature for
the index. ERA5 rainfall is produced by a weather forecast model constrained by observations,
not measured directly, so it is best described as semi-empirical. It tends to have too many
days of light rain, which affects dry-spell statistics.

**The relative Niño 3.4 index.** The Niño 3.4 SST anomaly (5°S–5°N, 170°W–120°W) minus the
anomaly of the whole 20°S–20°N band, both relative to {INDEX_BASE_PERIOD[0]}–{INDEX_BASE_PERIOD[1]}.
Following the C3S definition, the difference is then rescaled for each calendar month so that it
varies by as much as the traditional index did over {INDEX_SCALING_PERIOD[0]}–{INDEX_SCALING_PERIOD[1]}:
"""
    )
    st.latex(
        r"I_\mathrm{rel}(y, m) = \frac{\sigma_m\!\left(S'_{3.4}\right)}"
        r"{\sigma_m\!\left(S'_{3.4} - S'_\mathrm{trop}\right)}"
        r"\left[ S'_{3.4}(y, m) - S'_\mathrm{trop}(y, m) \right]"
    )
    st.markdown(
        f"where $S'_{{3.4}}$ and $S'_\\mathrm{{trop}}$ are the Niño 3.4 and tropical-mean SST "
        f"anomalies in year $y$ and calendar month $m$, and $\\sigma_m$ is the standard deviation "
        f"of a month's values over {INDEX_SCALING_PERIOD[0]}–{INDEX_SCALING_PERIOD[1]}. The DJF "
        "index is the mean of the December, January and February values. Its link with rainfall "
        "is a straight line fitted to the seasons since 1979,"
    )
    st.latex(r"P_\mathrm{NDJFM} = a + b \, I_\mathrm{rel,DJF} + \varepsilon")
    st.markdown(
        "where $P_\\mathrm{NDJFM}$ is November–March rainfall, $a$ and $b$ are fitted, and "
        "$\\varepsilon$ is the part of each season's rainfall that ENSO does not explain."
    )

    st.markdown(
        "**Atmospheric demand.** Reference evapotranspiration from temperature and latitude "
        "(Hargreaves and Samani, 1985):"
    )
    st.latex(
        r"\mathrm{ET}_0 = 0.0023 \times 0.408 \, R_\mathrm{a}"
        r"\left( T_\mathrm{mean} + 17.8 \right) \sqrt{T_\mathrm{max} - T_\mathrm{min}}"
    )
    st.markdown(
        "where $\\mathrm{ET}_0$ is in mm d$^{-1}$, temperatures are in °C, $R_\\mathrm{a}$ is "
        "the solar radiation at the top of the atmosphere in MJ m$^{-2}$ d$^{-1}$, and the factor 0.408 converts "
        "that radiation into an equivalent depth of evaporated water."
    )

    st.markdown(
        f"""
**Soil water.** A single root-zone "bucket" following FAO-56 (Allen et al., 1998). Rain fills
it (less runoff, by the SCS curve number method), the crop draws it down, and water above
field capacity drains away. The bucket deepens as the roots grow. Once more than a fraction p
= {MAIZE.depletion_fraction} of the available water has been used, the crop can no longer
draw water fast enough and its water use falls below demand.

The state variable is the root-zone depletion $D_\\mathrm{{r}}$ (mm below field capacity),
updated each day $i$ from rainfall $P$, runoff $\\mathrm{{RO}}$, actual evapotranspiration
$\\mathrm{{ET}}_\\mathrm{{a}}$ and deep percolation $\\mathrm{{DP}}$:
"""
    )
    st.latex(
        r"D_{\mathrm{r},i} = D_{\mathrm{r},i-1} - \left( P_i - \mathrm{RO}_i \right)"
        r" + \mathrm{ET}_{\mathrm{a},i} + \mathrm{DP}_i , \qquad "
        r"D_{\mathrm{r},i} \ge 0"
    )
    st.markdown(
        "Deep percolation is whatever would take $D_\\mathrm{r}$ below zero. Runoff is "
        "estimated from the soil's curve number $\\mathrm{CN}$:"
    )
    st.latex(
        r"\mathrm{RO}_i = \begin{cases} \dfrac{\left( P_i - 0.2\,S \right)^2}{P_i + 0.8\,S}, "
        r"& P_i > 0.2\,S \\[1ex] 0, & \text{otherwise} \end{cases} \qquad "
        r"S = \frac{25\,400}{\mathrm{CN}} - 254"
    )
    st.markdown(
        "with $P$, $\\mathrm{RO}$ and the retention parameter $S$ in mm. The size of the bucket "
        "is the total available water, and the stress threshold is a fraction $p$ of it:"
    )
    st.latex(
        r"\mathrm{TAW} = 1000 \left( \theta_\mathrm{FC} - \theta_\mathrm{WP} \right) Z_\mathrm{r}, "
        r"\qquad \mathrm{RAW} = p \, \mathrm{TAW}"
    )
    st.markdown(
        "where $\\theta_\\mathrm{FC}$ and $\\theta_\\mathrm{WP}$ are the volumetric water "
        "contents at field capacity and wilting point and $Z_\\mathrm{r}$ is the rooting depth "
        "in metres. Soil newly reached by the growing roots is assumed to be at field capacity, "
        "so root growth enlarges $\\mathrm{TAW}$ without changing $D_\\mathrm{r}$. The crop's "
        "water demand follows the crop coefficient $K_\\mathrm{c}$, and once depletion passes "
        "$\\mathrm{RAW}$ the stress coefficient $K_\\mathrm{s}$ reduces actual water use below it:"
    )
    st.latex(
        r"\mathrm{ET}_\mathrm{c} = K_\mathrm{c} \, \mathrm{ET}_0, \qquad "
        r"K_\mathrm{s} = \begin{cases} 1, & D_\mathrm{r} \le \mathrm{RAW} \\[1ex] "
        r"\dfrac{\mathrm{TAW} - D_\mathrm{r}}{\mathrm{TAW} - \mathrm{RAW}}, "
        r"& D_\mathrm{r} > \mathrm{RAW} \end{cases}, \qquad "
        r"\mathrm{ET}_\mathrm{a} = K_\mathrm{s} \, \mathrm{ET}_\mathrm{c}"
    )
    st.markdown(
        "Actual water use is also capped at the water left in the profile that day."
    )

    st.markdown(
        "**Yield.** In each growth stage $s$ the relative shortfall in water use is multiplied "
        "by a yield response factor $K_{\\mathrm{y},s}$ (FAO-33; Doorenbos and Kassam, 1979), "
        "and the stage effects are multiplied together:"
    )
    st.latex(
        r"\frac{Y_\mathrm{a}}{Y_\mathrm{m}} = \prod_{s} \max \left[ 0, \; 1 - K_{\mathrm{y},s}"
        r"\left( 1 - \frac{\mathrm{ET}_{\mathrm{a},s}}{\mathrm{ET}_{\mathrm{c},s}} \right) \right]"
    )
    st.markdown(
        "where $\\mathrm{ET}_{\\mathrm{a},s}$ and $\\mathrm{ET}_{\\mathrm{c},s}$ are totals over "
        "stage $s$, and $Y_\\mathrm{a}/Y_\\mathrm{m}$ is the yield as a fraction of the yield with "
        "no water shortage, which is how results are reported. The stage-dependent "
        "$K_\\mathrm{y}$ is what makes timing matter. For maize it is 1.5 during flowering and "
        "grain fill against 0.4 during vegetative growth, so the same relative shortfall costs "
        "nearly four times as much yield if it falls during flowering."
    )

    left, right = st.columns(2)
    with left:
        st.markdown("**Crop stages**")
        params = pd.DataFrame({
            "Stage": [STAGE_LABELS[s] for s in STAGE_ORDER],
            "Days": [MAIZE.stage_lengths[s] for s in STAGE_ORDER],
            "Ky": [MAIZE.ky_by_stage[s] for s in STAGE_ORDER],
        })
        show_table(params, formats={"Ky": "{:.1f}"})
    with right:
        st.markdown("**Soils**")
        soils = pd.DataFrame({
            "Soil": [soil.name for soil in SOILS.values()],
            "θ at field capacity": [soil.field_capacity for soil in SOILS.values()],
            "θ at wilting point": [soil.wilting_point for soil in SOILS.values()],
            "Available water (mm/m)": [soil.available_water_capacity for soil in SOILS.values()],
            "Curve number": [soil.curve_number for soil in SOILS.values()],
        })
        show_table(soils, formats={"θ at field capacity": "{:.2f}", "θ at wilting point": "{:.2f}",
                                   "Available water (mm/m)": "{:.0f}", "Curve number": "{:.0f}"})

    st.markdown(
        """
**Not included.** Nutrients, pests and diseases, weeds, farmer decisions other than planting
date, irrigation, differences across the district, and the many other influences on rainfall
besides ENSO except as unexplained scatter. The crop model's structure is also a source of
uncertainty in its own right: a different crop model would give somewhat different answers.
Real yield gaps in the region are often set by nitrogen and management rather than by water.
"""
    )

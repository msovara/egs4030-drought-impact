# -*- coding: utf-8 -*-
"""
EGS4030/5030S drought impact modelling dashboard.

Run with:
    streamlit run app.py

The tabs follow the order of the lecture: one season in detail, then the role of
rainfall timing, then the observed ocean index record driven through the model,
then the season ahead, and finally the gap between a drought index and an actual
impact.

The climate driver is chosen in the sidebar. ENSO (DJF Nino 3.4) is the default;
the Indian Ocean Dipole (SON DMI) is the alternative. Nothing downstream of the
first tab changes when you switch, which is itself worth pointing out.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))

from impact_model.climate import (
    CPC_ADVISORY,
    DRIVERS,
    TeleconnectionAssumption,
    get_driver,
    latest_observation,
    site_scaling,
)
from impact_model.config import CROPS, DEFAULT_CROP, SITES, SOILS, STAGE_LABELS, STAGE_ORDER
from impact_model.driver_error import (
    DERIVED_DIURNAL_BIAS,
    MVULA_V5_AFRICA_T2M,
    NON_MONOTONIC_NOTE,
    PROVENANCE,
    SYSTEMATIC_BIAS_NOTE,
    WHY_THE_RANGE_MATTERS,
    summary_rows,
)
from impact_model.experiment import (
    composite_by_phase,
    diurnal_range_sweep,
    run_observed_record,
    run_scenario,
    run_single_season,
    sensitivity_sweep,
    temperature_bias_sweep,
)
from impact_model.indices import classify_drought

st.set_page_config(
    page_title="Drought Impact Model | EGS4030/5030S",
    page_icon="*",
    layout="wide",
)

PHASE_COLOURS = {"positive": "#c0392b", "negative": "#2471a3", "neutral": "#909497"}

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


STAGE_COLOURS = {
    "initial": "#a9dfbf",
    "development": "#7dcea0",
    "mid": "#f5b041",
    "late": "#d7bde2",
}


# --------------------------------------------------------------------------
# Cached model runs. The model is fast, but caching keeps the sliders responsive.
# --------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def cached_single_season(site_key, crop_key, anomaly, temp_shift, irrigation, seed):
    result, weather = run_single_season(
        SITES[site_key],
        CROPS[crop_key],
        rainfall_anomaly=anomaly,
        temperature_shift=temp_shift,
        irrigation_mm_per_week=irrigation,
        seed=seed,
    )
    return result, weather


@st.cache_data(show_spinner=False)
def cached_sweep(site_key, crop_key, members, temp_shift, irrigation):
    anomalies = np.arange(-0.60, 0.61, 0.10)
    return sensitivity_sweep(
        site_key,
        crop_key,
        anomalies,
        members=members,
        temperature_shift=temp_shift,
        irrigation_mm_per_week=irrigation,
    )


@st.cache_data(show_spinner=False)
def cached_temperature_sweep(site_key, crop_key, members, rainfall_anomaly, irrigation):
    biases = np.arange(-6.0, 4.01, 0.5)
    return temperature_bias_sweep(
        site_key,
        crop_key,
        biases,
        members=members,
        rainfall_anomaly=rainfall_anomaly,
        irrigation_mm_per_week=irrigation,
    )


@st.cache_data(show_spinner=False)
def cached_diurnal_sweep(site_key, crop_key, members, rainfall_anomaly, irrigation, temp_shift):
    range_biases = np.arange(-8.0, 2.01, 0.5)
    return diurnal_range_sweep(
        site_key,
        crop_key,
        range_biases,
        members=members,
        rainfall_anomaly=rainfall_anomaly,
        irrigation_mm_per_week=irrigation,
        temperature_shift=temp_shift,
    )


@st.cache_data(show_spinner=False)
def cached_driver_cases(site_key, crop_key, rainfall_anomaly, irrigation, members):
    """Perfect driver, naive uniform offset, and the full measured error."""
    seeds = np.random.default_rng(17).integers(0, 2**31 - 1, members)
    cases = {
        "perfect": dict(temperature_shift=0.0, diurnal_range_shift=0.0),
        "uniform": dict(
            temperature_shift=DERIVED_DIURNAL_BIAS["t_mean_bias"],
            diurnal_range_shift=0.0,
        ),
        "full": dict(
            temperature_shift=DERIVED_DIURNAL_BIAS["t_mean_bias"],
            diurnal_range_shift=DERIVED_DIURNAL_BIAS["diurnal_range_bias"],
        ),
    }

    summary = {}
    for name, kwargs in cases.items():
        runs = [
            run_single_season(
                SITES[site_key], CROPS[crop_key],
                rainfall_anomaly=rainfall_anomaly,
                irrigation_mm_per_week=irrigation,
                seed=int(seed), **kwargs,
            )
            for seed in seeds
        ]
        results = [r for r, _ in runs]
        weather = [w for _, w in runs]
        summary[name] = {
            "yield": float(np.mean([r.actual_yield for r in results])),
            "et0": float(np.mean([r.season_et_potential for r in results])),
            "stress": float(np.mean([r.water_stress_days for r in results])),
            "dtr": float(np.mean([(w["t_max"] - w["t_min"]).mean() for w in weather])),
        }
    return summary


@st.cache_data(show_spinner=False)
def cached_observed(site_key, crop_key, driver_key, sensitivity, noise, temp_shift, irrigation, seed):
    assumption = TeleconnectionAssumption(
        rainfall_sensitivity=sensitivity, noise_std=noise, driver_key=driver_key
    )
    return run_observed_record(
        site_key,
        crop_key,
        driver=driver_key,
        assumption=assumption,
        temperature_shift=temp_shift,
        irrigation_mm_per_week=irrigation,
        seed=seed,
    )


@st.cache_data(show_spinner=False)
def cached_scenario(
    site_key, crop_key, driver_key, index_value, sensitivity, noise,
    temp_shift, irrigation, members,
):
    assumption = TeleconnectionAssumption(
        rainfall_sensitivity=sensitivity, noise_std=noise, driver_key=driver_key
    )
    return run_scenario(
        site_key,
        crop_key,
        index_value=index_value,
        driver=driver_key,
        assumption=assumption,
        members=members,
        temperature_shift=temp_shift,
        irrigation_mm_per_week=irrigation,
    )


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------

st.sidebar.title("Model setup")

site_key = st.sidebar.selectbox(
    "Site", options=list(SITES), format_func=lambda k: SITES[k].name
)
site = SITES[site_key]
soil = SOILS[site.soil]

crop_key = st.sidebar.selectbox(
    "Crop",
    options=list(CROPS),
    index=list(CROPS).index(DEFAULT_CROP.get(site_key, "maize")),
    format_func=lambda k: CROPS[k].name,
)
crop = CROPS[crop_key]

st.sidebar.caption(site.description)
st.sidebar.markdown(
    f"**Soil** {soil.name}  \n"
    f"**Available water** {soil.available_water_capacity:.0f} mm/m  \n"
    f"**Season length** {crop.season_length} days  \n"
    f"**Rainfed potential** {crop.potential_yield:.1f} t/ha"
)

st.sidebar.divider()
st.sidebar.subheader("Management and climate")

irrigation = st.sidebar.slider(
    "Supplementary irrigation (mm/week)", 0.0, 40.0, 0.0, 5.0,
    help="Applied every seventh day. Set to zero for a purely rainfed system.",
)
temp_shift = st.sidebar.slider(
    "Temperature offset (degC)", -6.0, 4.0, 0.0, 0.5,
    help=(
        "Added to every day of the record, changing evaporative demand through "
        "ET0. Use positive values for a warming scenario and negative values to "
        "reproduce a cold bias in the weather data driving the model."
    ),
)

st.sidebar.divider()
st.sidebar.subheader("Climate driver")

driver_key = st.sidebar.radio(
    "Ocean index",
    options=list(DRIVERS),
    format_func=lambda k: f"{DRIVERS[k].name} ({DRIVERS[k].season_label})",
    help=(
        "Which mode of ocean variability drives the model. Switching it changes "
        "nothing downstream, which is the point of keeping the driver separate."
    ),
)
driver = get_driver(driver_key)
st.sidebar.caption(driver.description)

st.sidebar.markdown("**Teleconnection assumption**")
st.sidebar.caption(
    f"How strongly {driver.name} is assumed to modulate rainfall at this site. "
    "These are teaching defaults, not fitted values."
)
sensitivity = st.sidebar.slider(
    f"Rainfall change per 1 sd of {driver.index_name}",
    -0.40, 0.10, driver.default_sensitivity, 0.01,
    key=f"sensitivity_{driver_key}",
    help=f"Negative means a {driver.positive_label} suppresses rainfall.",
)
noise = st.sidebar.slider(
    "Unexplained rainfall variability (sd)",
    0.0, 0.50, driver.default_noise_std, 0.01,
    key=f"noise_{driver_key}",
    help=f"Everything other than {driver.index_name} that sets seasonal rainfall.",
)
st.sidebar.caption(
    f"Regional scaling for this site: {site_scaling(site_key, driver):.2f} "
    f"&nbsp;|&nbsp; record: {driver.record_note}"
)


# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------

st.title("From the ocean to the maize field")
st.markdown(
    "**EGS4030/5030S Climate Modelling** &nbsp;|&nbsp; guest lecture on climate impact modelling. "
    "Every number on this page comes from a water balance and a yield model running "
    "live on this laptop, in milliseconds per season."
)

tab_season, tab_timing, tab_record, tab_ahead, tab_index, tab_driver, tab_model = st.tabs(
    [
        "1. One season, day by day",
        "2. Why timing beats totals",
        f"3. The observed {driver.index_name} record",
        "4. The season ahead",
        "5. Index is not impact",
        "6. When the driver is wrong",
        "7. The model itself",
    ]
)


# --------------------------------------------------------------------------
# Tab 1: a single season
# --------------------------------------------------------------------------

with tab_season:
    st.subheader("A single growing season")
    st.markdown(
        "Move the rainfall slider and watch the soil water store, the transpiration "
        "deficit and the final yield respond. This is the entire impact model."
    )

    controls = st.columns([2, 2, 1])
    with controls[0]:
        anomaly_percent = st.slider(
            "Seasonal rainfall anomaly (%)", -80, 60, -30, 5,
            key="season_anomaly",
        )
        anomaly = anomaly_percent / 100.0
    with controls[1]:
        seed = st.slider(
            "Weather realisation", 1, 50, 7, 1,
            help="Same seasonal total, different day-to-day sequence.",
            key="season_seed",
        )
    with controls[2]:
        st.metric("Target rainfall", f"{site.annual_rainfall * (1 + anomaly):.0f} mm")
        st.caption("for the year")

    result, weather = cached_single_season(
        site_key, crop_key, anomaly, temp_shift, irrigation, seed
    )

    unmet_fraction = 1 - result.season_et_actual / result.season_et_potential

    metrics = st.columns(5)
    metrics[0].metric("Season rainfall", f"{result.season_rainfall:.0f} mm")
    metrics[0].caption(f"of {site.annual_rainfall * (1 + anomaly):.0f} mm for the year")
    metrics[1].metric(
        "Water deficit", f"{result.season_et_potential - result.season_et_actual:.0f} mm"
    )
    metrics[1].caption(f"{unmet_fraction:.0%} of crop demand unmet")
    metrics[2].metric("Days under stress", f"{result.water_stress_days}")
    metrics[2].caption(f"of {crop.season_length} in the season")
    metrics[3].metric("Yield", f"{result.actual_yield:.2f} t/ha")
    metrics[3].caption(f"potential {crop.potential_yield:.1f} t/ha")
    metrics[4].metric("Yield loss", f"{result.yield_loss_fraction:.0%}")
    metrics[4].caption(f"relative yield {result.relative_yield:.0%}")

    daily = result.daily
    figure = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
        row_heights=[0.28, 0.38, 0.34],
        subplot_titles=(
            "Daily rainfall",
            "Root zone soil water (mm) against the stress threshold",
            "Transpiration: potential demand against what the crop actually got",
        ),
    )

    figure.add_trace(
        go.Bar(
            x=daily.index, y=daily["precip"], name="Rainfall",
            marker_color="#2e86c1", hovertemplate="%{y:.1f} mm<extra></extra>",
        ),
        row=1, col=1,
    )

    figure.add_trace(
        go.Scatter(
            x=daily.index, y=daily["total_available_water"], name="Field capacity",
            line=dict(color="#5d6d7e", dash="dot"),
        ),
        row=2, col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=daily.index,
            y=daily["total_available_water"] - daily["readily_available_water"],
            name="Stress threshold", line=dict(color="#e67e22", dash="dash"),
        ),
        row=2, col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=daily.index, y=daily["soil_water"], name="Soil water",
            line=dict(color="#1a5276", width=2.5), fill="tozeroy",
            fillcolor="rgba(26,82,118,0.18)",
        ),
        row=2, col=1,
    )

    figure.add_trace(
        go.Scatter(
            x=daily.index, y=daily["et_potential"], name="Potential (ETc)",
            line=dict(color="#a04000", dash="dot"),
        ),
        row=3, col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=daily.index, y=daily["et_actual"], name="Actual (ETa)",
            line=dict(color="#196f3d", width=2), fill="tonexty",
            fillcolor="rgba(192,57,43,0.22)",
        ),
        row=3, col=1,
    )

    # Shade the growth stages so the flowering window is visually obvious.
    for stage in STAGE_ORDER:
        stage_days = daily.index[daily["stage"] == stage]
        if len(stage_days) == 0:
            continue
        figure.add_vrect(
            x0=stage_days[0], x1=stage_days[-1],
            fillcolor=STAGE_COLOURS[stage], opacity=0.18, line_width=0,
            annotation_text=STAGE_LABELS[stage], annotation_position="top left",
            annotation_font_size=10, row=1, col=1,
        )
        figure.add_vrect(
            x0=stage_days[0], x1=stage_days[-1],
            fillcolor=STAGE_COLOURS[stage], opacity=0.12, line_width=0, row=3, col=1,
        )

    figure.update_layout(
        height=720, hovermode="x unified", margin=dict(t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0),
    )
    figure.update_yaxes(title_text="mm", row=1, col=1)
    figure.update_yaxes(title_text="mm", row=2, col=1)
    figure.update_yaxes(title_text="mm/day", row=3, col=1)
    st.plotly_chart(figure, width="stretch")

    st.markdown("#### Where the yield was actually lost")
    st.caption(
        "FAO-33 weights the water deficit in each growth stage by a yield response "
        "factor Ky. For maize, Ky at flowering is 1.5 against 0.4 during vegetative "
        "growth, so the same deficit costs nearly four times as much yield if it "
        "lands in January rather than November."
    )

    stage_table = result.stage_summary.copy()
    stage_table["Stage"] = stage_table["stage"].map(STAGE_LABELS)
    display = stage_table[
        ["Stage", "days", "rainfall", "et_potential", "et_actual",
         "deficit_ratio", "ky", "stage_yield_factor"]
    ].rename(
        columns={
            "days": "Days", "rainfall": "Rain (mm)", "et_potential": "ETc (mm)",
            "et_actual": "ETa (mm)", "deficit_ratio": "Deficit",
            "ky": "Ky", "stage_yield_factor": "Yield multiplier",
        }
    )
    show_table(
        display,
        formats={
            "Rain (mm)": "{:.0f}", "ETc (mm)": "{:.0f}", "ETa (mm)": "{:.0f}",
            "Deficit": "{:.0%}", "Ky": "{:.2f}", "Yield multiplier": "{:.3f}",
        },
        shade={"Yield multiplier": dict(vmin=0.0, vmax=1.0)},
    )


# --------------------------------------------------------------------------
# Tab 2: timing versus totals
# --------------------------------------------------------------------------

with tab_timing:
    st.subheader("Two seasons with the same rainfall can give very different yields")
    st.markdown(
        "Each rainfall anomaly below is run as an ensemble. The only thing that "
        "differs between members is the day-to-day sequence of the rain. The spread "
        "you see is therefore caused entirely by timing."
    )

    members = st.slider("Ensemble members per anomaly", 5, 60, 25, 5)
    sweep = cached_sweep(site_key, crop_key, members, temp_shift, irrigation)

    summary = sweep.groupby("rainfall_anomaly").agg(
        rainfall=("season_rainfall", "mean"),
        mean_yield=("actual_yield", "mean"),
        p10=("actual_yield", lambda s: s.quantile(0.10)),
        p90=("actual_yield", lambda s: s.quantile(0.90)),
    ).reset_index()

    response = go.Figure()
    response.add_trace(
        go.Scatter(
            x=summary["rainfall_anomaly"], y=summary["p90"],
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        )
    )
    response.add_trace(
        go.Scatter(
            x=summary["rainfall_anomaly"], y=summary["p10"],
            fill="tonexty", fillcolor="rgba(41,128,185,0.22)",
            line=dict(width=0), name="10th to 90th percentile",
        )
    )
    response.add_trace(
        go.Scatter(
            x=summary["rainfall_anomaly"], y=summary["mean_yield"],
            line=dict(color="#1b4f72", width=3), mode="lines+markers",
            name="Ensemble mean",
        )
    )
    response.add_trace(
        go.Scatter(
            x=sweep["rainfall_anomaly"], y=sweep["actual_yield"],
            mode="markers", marker=dict(size=4, color="#34495e", opacity=0.35),
            name="Individual seasons",
        )
    )
    response.update_layout(
        height=520, xaxis_title="Seasonal rainfall anomaly",
        yaxis_title=f"{crop.name} yield (t/ha)",
        xaxis=dict(tickformat="+.0%"), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    st.plotly_chart(response, width="stretch")

    columns = st.columns(2)
    with columns[0]:
        st.markdown("**The response is not a straight line**")
        st.caption(
            "Yield saturates once water stops being the limiting factor, and "
            "collapses non-linearly once deficits reach the flowering stage. A "
            "linear rainfall-to-yield regression, which is what most impact "
            "assessments still use, will get both tails wrong."
        )
    with columns[1]:
        worst = sweep.loc[sweep["actual_yield"].idxmin()]
        best_at_same = sweep[
            np.isclose(sweep["rainfall_anomaly"], worst["rainfall_anomaly"])
        ]["actual_yield"].max()
        st.markdown("**Spread at a single anomaly**")
        st.caption(
            f"At an anomaly of {worst['rainfall_anomaly']:+.0%}, modelled yield "
            f"ranges from {worst['actual_yield']:.2f} to {best_at_same:.2f} t/ha "
            "across the ensemble. Identical seasonal totals, different outcomes."
        )


# --------------------------------------------------------------------------
# Tab 3: the observed index record
# --------------------------------------------------------------------------

with tab_record:
    run = cached_observed(
        site_key, crop_key, driver_key, sensitivity, noise, temp_shift, irrigation, 42
    )
    seasons = run.seasons
    composite = composite_by_phase(seasons)

    st.subheader(
        f"Driving the impact model with {len(seasons)} years of observed "
        f"{driver.index_name}"
    )
    st.markdown(
        f"The {driver.season_label}-mean {driver.index_name} below is observed "
        f"({driver.record_note}) Everything downstream of it is modelled."
    )

    chain = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
        subplot_titles=(
            f"Observed {driver.season_label} {driver.index_name}",
            "Modelled growing season rainfall",
            "Modelled yield",
        ),
    )

    chain.add_trace(
        go.Bar(
            x=seasons.index, y=seasons["index_value"],
            marker_color=[PHASE_COLOURS[p] for p in seasons["phase"]],
            name=driver.index_name,
            hovertemplate="%{x}: %{y:.2f} degC<extra></extra>",
        ),
        row=1, col=1,
    )
    # Phases are declared on the anomaly relative to the record mean, so the
    # event thresholds sit either side of that mean rather than either side of
    # zero. The offset is small but the lines would otherwise disagree with the
    # bar colours.
    record_mean = float(seasons["index_value"].mean())
    chain.add_hline(
        y=record_mean + driver.event_threshold,
        line_dash="dot", line_color="#c0392b", row=1, col=1,
    )
    chain.add_hline(
        y=record_mean - driver.event_threshold,
        line_dash="dot", line_color="#2471a3", row=1, col=1,
    )

    chain.add_trace(
        go.Scatter(
            x=seasons.index, y=seasons["season_rainfall"], name="Rainfall",
            line=dict(color="#2e86c1", width=2), mode="lines+markers",
        ),
        row=2, col=1,
    )
    chain.add_hline(
        y=seasons["season_rainfall"].mean(), line_dash="dash",
        line_color="#5d6d7e", row=2, col=1,
    )

    chain.add_trace(
        go.Bar(
            x=seasons.index, y=seasons["actual_yield"],
            marker_color=[PHASE_COLOURS[p] for p in seasons["phase"]],
            name="Yield", hovertemplate="%{x}: %{y:.2f} t/ha<extra></extra>",
        ),
        row=3, col=1,
    )
    chain.add_hline(
        y=seasons["actual_yield"].mean(), line_dash="dash",
        line_color="#5d6d7e", row=3, col=1,
    )

    chain.update_layout(height=760, showlegend=False, margin=dict(t=60))
    chain.update_yaxes(title_text="degC", row=1, col=1)
    chain.update_yaxes(title_text="mm", row=2, col=1)
    chain.update_yaxes(title_text="t/ha", row=3, col=1)
    st.plotly_chart(chain, width="stretch")

    st.markdown(f"#### Composite by {driver.name} phase")
    composite_display = composite.rename(index=driver.phase_label).rename(
        columns={
            "seasons": "Seasons", "mean_yield": "Mean yield (t/ha)",
            "median_yield": "Median (t/ha)", "yield_std": "Std dev",
            "mean_rainfall": "Rainfall (mm)", "mean_stress_days": "Stress days",
            "mean_spi3": "Mean SPI3", "yield_anomaly_percent": "Yield anomaly (%)",
        }
    )
    show_table(
        composite_display,
        formats={
            "Mean yield (t/ha)": "{:.2f}", "Median (t/ha)": "{:.2f}",
            "Std dev": "{:.2f}", "Rainfall (mm)": "{:.0f}",
            "Stress days": "{:.1f}", "Mean SPI3": "{:.2f}",
            "Yield anomaly (%)": "{:+.1f}",
        },
        hide_index=False,
    )

    positive_yields = seasons.loc[seasons["phase"] == "positive", "actual_yield"]
    negative_yields = seasons.loc[seasons["phase"] == "negative", "actual_yield"]

    if len(positive_yields) >= 2 and len(negative_yields) >= 2:
        test = stats.ttest_ind(positive_yields, negative_yields, equal_var=False)
        anomaly = composite.loc["positive", "yield_anomaly_percent"]
        verdict = (
            f"Across {len(positive_yields)} {driver.positive_label} seasons the model "
            f"gives a mean yield anomaly of {anomaly:+.1f}%, and the difference from "
            f"the {len(negative_yields)} {driver.negative_label} seasons has "
            f"p = {test.pvalue:.3f}."
        )
        if test.pvalue < 0.05:
            st.info(
                verdict + " That separation survives a significance test. Ask the "
                "students what it would take to break it: a different site, a "
                "shorter record, or a weaker assumed teleconnection."
            )
        else:
            st.warning(
                verdict + " That is not a significant separation. The teleconnection "
                "is real in the model, because it was put there deliberately, but "
                "this record is too short and too noisy to recover it. Switching "
                "the driver in the sidebar is the fastest way to see how much "
                "difference the length of the record and the strength of the "
                "signal make."
            )

    st.markdown("#### The worst modelled seasons")
    worst = seasons.nsmallest(8, "actual_yield")[
        ["index_value", "phase", "rainfall_anomaly", "season_rainfall",
         "actual_yield", "water_stress_days", "spi3"]
    ].assign(phase=lambda f: f["phase"].map(driver.phase_label)).rename(
        columns={
            "index_value": driver.index_name, "phase": "Phase",
            "rainfall_anomaly": "Rain anomaly",
            "season_rainfall": "Rainfall (mm)", "actual_yield": "Yield (t/ha)",
            "water_stress_days": "Stress days", "spi3": "SPI3",
        }
    )
    show_table(
        worst,
        formats={
            driver.index_name: "{:.2f}", "Rain anomaly": "{:+.0%}",
            "Rainfall (mm)": "{:.0f}", "Yield (t/ha)": "{:.2f}", "SPI3": "{:.2f}",
        },
        hide_index=False,
    )
    st.caption(
        f"Look for a bad season that was not a {driver.positive_label} year. Those "
        "are the cases that show why a seasonal forecast based on one index will "
        "always miss some of the failures that matter most."
    )


# --------------------------------------------------------------------------
# Tab 4: the season ahead
# --------------------------------------------------------------------------

with tab_ahead:
    st.subheader("Running the model forward on a season that has not happened yet")

    if driver_key == "enso":
        latest = latest_observation()
        st.markdown(
            f"As of its **{CPC_ADVISORY['issued']}** diagnostic discussion, NOAA's "
            f"Climate Prediction Center had the ENSO alert system at "
            f"**{CPC_ADVISORY['status']}**, with Nino 3.4 at "
            f"**{CPC_ADVISORY['nino34_anomaly']:+.1f} degC** in "
            f"{CPC_ADVISORY['latest_month']}. It gave a "
            f"**{CPC_ADVISORY['historic_probability_ond']:.0%} chance** that "
            "October-December would exceed any event since 1950, with a forecast "
            f"RONI near **{CPC_ADVISORY['roni_forecast_ond_median']:+.2f} degC**. "
            f"([source]({CPC_ADVISORY['url']}))"
        )
        st.caption(
            f"The bundled monthly file ends in {latest['label']} at "
            f"{latest['value']:+.2f} degC; CPC's discussion is ahead of that "
            "file. RONI and the raw Nino 3.4 anomaly are not the same quantity: "
            "RONI subtracts the tropical mean sea surface temperature, so it is "
            "the smaller number in a warming ocean. Treat the slider below as a "
            "scenario, not as a forecast I am issuing. The default of +2.5 degC "
            "is the historic-event threshold CPC is now giving an 83% chance."
        )
        default_scenario = 2.5
    else:
        st.markdown(
            "Set a dipole state and run the impact model forward on it. The same "
            "machinery works for any index; the ENSO driver is the one with a "
            "live event attached to it this season."
        )
        default_scenario = 1.0

    scenario_value = st.slider(
        f"Scenario {driver.season_label} {driver.index_name} (degC)",
        -2.5, 3.0, default_scenario, 0.1,
        key=f"scenario_{driver_key}",
    )

    scenario = cached_scenario(
        site_key, crop_key, driver_key, scenario_value,
        sensitivity, noise, temp_shift, irrigation, 120,
    )

    members = scenario.members["actual_yield"]
    baseline = scenario.baseline["actual_yield"]
    failure_threshold = 0.5 * baseline.median()

    metrics = st.columns(4)
    metrics[0].metric("Phase", driver.phase_label(scenario.phase))
    metrics[0].caption(f"{scenario.index_standardized:+.2f} sd above the record mean")

    metrics[1].metric("Median modelled yield", f"{members.median():.2f} t/ha")
    metrics[1].caption(f"Neutral season: {baseline.median():.2f} t/ha")

    metrics[2].metric(
        "Change vs neutral", f"{scenario.yield_loss_percent:+.0f}%",
    )
    metrics[2].caption("Mean over the ensemble")

    failure_risk = float((members < failure_threshold).mean())
    metrics[3].metric("Chance of a failed harvest", f"{failure_risk:.0%}")
    metrics[3].caption(
        f"Below {failure_threshold:.2f} t/ha, half the neutral median"
    )

    distribution = go.Figure()
    distribution.add_trace(
        go.Histogram(
            x=baseline, name="Neutral season", opacity=0.65,
            marker_color=PHASE_COLOURS["neutral"], nbinsx=24,
        )
    )
    distribution.add_trace(
        go.Histogram(
            x=members, name=driver.phase_label(scenario.phase), opacity=0.65,
            marker_color=PHASE_COLOURS[scenario.phase], nbinsx=24,
        )
    )
    distribution.add_vline(
        x=baseline.median(), line_dash="dash", line_color=PHASE_COLOURS["neutral"],
    )
    distribution.add_vline(
        x=members.median(), line_dash="dash",
        line_color=PHASE_COLOURS[scenario.phase],
    )
    distribution.update_layout(
        barmode="overlay", height=430,
        xaxis_title=f"{crop.name} yield (t/ha)",
        yaxis_title="Ensemble members",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(t=60),
    )
    st.plotly_chart(distribution, width="stretch")

    overlap = float((members > baseline.median()).mean())
    st.warning(
        f"The two distributions overlap. {overlap:.0%} of the scenario members "
        f"still come in above the median neutral season. An event of this size "
        "shifts the odds hard, but it does not determine the outcome of any "
        "single season. This is the difference between a forecast and a prophecy, "
        "and it is the hardest thing to communicate to someone who has to decide "
        "what to plant."
    )

    st.markdown("#### The closest observed analogues")
    analogues = scenario.analogues[
        ["index_value", "season_rainfall", "actual_yield", "water_stress_days", "spi3"]
    ].rename(
        columns={
            "index_value": driver.index_name,
            "season_rainfall": "Rainfall (mm)",
            "actual_yield": "Modelled yield (t/ha)",
            "water_stress_days": "Stress days",
            "spi3": "SPI3",
        }
    )
    show_table(
        analogues,
        formats={
            driver.index_name: "{:.2f}", "Rainfall (mm)": "{:.0f}",
            "Modelled yield (t/ha)": "{:.2f}", "SPI3": "{:.2f}",
        },
        hide_index=False,
    )
    st.info(
        "The seasons in this table are real and their index values are observed, "
        "but the yields beside them are modelled, not measured. That is the "
        "check worth making: look up what those harvests actually did. Where the "
        "model matches, you have some reason to trust it. Where it does not, you "
        "have found something more interesting than a working model."
    )


# --------------------------------------------------------------------------
# Tab 5: index versus impact
# --------------------------------------------------------------------------

with tab_index:
    st.subheader("A drought index is not a drought impact")
    st.markdown(
        "SPI tells you how unusual the rainfall was. It does not know what was "
        "planted, when it flowered, or what the soil could hold. Below, every point "
        "is one modelled season."
    )

    run = cached_observed(
        site_key, crop_key, driver_key, sensitivity, noise, temp_shift, irrigation, 42
    )
    seasons = run.seasons.dropna(subset=["spi3"])

    if len(seasons) < 5:
        st.warning("Not enough seasons with a valid SPI value to draw the comparison.")
    else:
        regression = stats.linregress(seasons["spi3"], seasons["actual_yield"])
        line_x = np.linspace(seasons["spi3"].min(), seasons["spi3"].max(), 50)

        scatter = go.Figure()
        for phase in ("negative", "neutral", "positive"):
            subset = seasons[seasons["phase"] == phase]
            if subset.empty:
                continue
            scatter.add_trace(
                go.Scatter(
                    x=subset["spi3"], y=subset["actual_yield"], mode="markers+text",
                    text=[str(y) for y in subset.index], textposition="top center",
                    textfont=dict(size=8, color="#566573"),
                    marker=dict(size=11, color=PHASE_COLOURS[phase],
                                line=dict(width=1, color="white")),
                    name=driver.phase_label(phase),
                    hovertemplate="%{text}<br>SPI3 %{x:.2f}<br>%{y:.2f} t/ha<extra></extra>",
                )
            )
        scatter.add_trace(
            go.Scatter(
                x=line_x, y=regression.intercept + regression.slope * line_x,
                line=dict(color="#34495e", dash="dash"),
                name=f"Linear fit (r squared = {regression.rvalue ** 2:.2f})",
            )
        )
        scatter.add_vline(x=-1.0, line_dash="dot", line_color="#e67e22")
        scatter.add_annotation(
            x=-1.0, y=seasons["actual_yield"].max(), text="Moderate drought threshold",
            showarrow=False, xanchor="left", font=dict(size=10, color="#e67e22"),
        )
        scatter.update_layout(
            height=560, xaxis_title="SPI3 at the end of flowering",
            yaxis_title=f"{crop.name} yield (t/ha)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        )
        st.plotly_chart(scatter, width="stretch")

        # Seasons the index would classify as normal but the model calls a failure.
        threshold = seasons["actual_yield"].quantile(0.25)
        bad_seasons = seasons[seasons["actual_yield"] <= threshold]
        missed = bad_seasons[bad_seasons["spi3"] > -1.0]

        columns = st.columns(3)
        columns[0].metric("SPI3 explains", f"{regression.rvalue ** 2:.0%}")
        columns[0].caption("of the variance in modelled yield")
        columns[1].metric("Correlation", f"{regression.rvalue:.2f}")
        columns[1].caption("SPI3 against yield")
        columns[2].metric("Failures SPI would miss", f"{len(missed)}")
        columns[2].caption(f"of {len(bad_seasons)} seasons in the worst yield quartile")

        if not missed.empty:
            st.warning(
                "Seasons in the worst yield quartile that SPI3 would not have "
                "flagged as even a moderate drought: "
                + ", ".join(str(y) for y in missed.index)
                + ". In each of these the rainfall total was acceptable but it "
                "arrived at the wrong time."
            )

        st.info(
            f"**Do not let the students take that {regression.rvalue ** 2:.0%} at "
            "face value, and do not be caught out by it yourself.** The correlation "
            "is high here largely because rainfall is the *only* thing the weather "
            "generator varies, so SPI is measuring almost exactly the model's own "
            "forcing. Real yields also respond to heat, nutrients, pests, disease "
            "and management, none of which are represented, so an observed "
            "SPI-to-yield relationship is invariably much weaker than this. The "
            "durable point is the one on the right: even at this correlation, the "
            "conventional SPI drought threshold still fails to flag most of the "
            "bad seasons."
        )

        st.markdown("#### The same seasons ranked two different ways")
        comparison = seasons.assign(
            spi_class=seasons["spi3"].map(classify_drought),
            spi_rank=seasons["spi3"].rank(),
            yield_rank=seasons["actual_yield"].rank(),
        )
        comparison["rank_disagreement"] = (
            comparison["spi_rank"] - comparison["yield_rank"]
        ).abs()
        biggest = comparison.nlargest(8, "rank_disagreement")[
            ["spi3", "spi_class", "spi_rank", "actual_yield", "yield_rank", "rank_disagreement"]
        ].rename(
            columns={
                "spi3": "SPI3", "spi_class": "SPI says", "spi_rank": "SPI rank",
                "actual_yield": "Yield (t/ha)", "yield_rank": "Yield rank",
                "rank_disagreement": "Disagreement",
            }
        )
        show_table(
            biggest,
            formats={
                "SPI3": "{:.2f}", "SPI rank": "{:.0f}", "Yield (t/ha)": "{:.2f}",
                "Yield rank": "{:.0f}", "Disagreement": "{:.0f}",
            },
            hide_index=False,
        )


# --------------------------------------------------------------------------
# Tab 5: driver error
# --------------------------------------------------------------------------

with tab_driver:
    st.subheader("An impact model inherits every error in what drives it")
    st.markdown(
        "Everything so far assumed the weather was known. It is not. In practice "
        "an impact model is driven by a forecast or a reanalysis, and both carry "
        "measurable error. Below, that error is not hypothetical: it is the "
        "verified skill of **Mvula v5**, the lightweight African weather model "
        "built in this project, which runs a forecast step on a laptop CPU in "
        "about 2.5 seconds."
    )

    st.markdown("#### What the weather model actually achieves")
    skill_frame = pd.DataFrame(summary_rows())
    show_table(
        skill_frame,
        formats={
            "RMSE (degC)": "{:.3f}",
            "Bias (degC)": "{:+.3f}",
            "ACC": "{:.3f}",
            "Persistence RMSE (degC)": "{:.3f}",
            "Skill vs persistence": "{:+.1%}",
        },
        shade={"RMSE (degC)": dict(reverse=True)},
    )
    st.caption(
        f"{PROVENANCE['model']}. {PROVENANCE['sample']}. {PROVENANCE['protocol']} "
        f"Source: [{PROVENANCE['repository']}]({PROVENANCE['repository']}), "
        f"{PROVENANCE['skill_source']} and {PROVENANCE['baseline_source']}."
    )

    st.error(
        "**These four rows are not a forecast decay curve, and reading them as "
        "one is the mistake worth spending five minutes on.** Every row is a "
        "single 6-hour step launched from a fresh ERA5 analysis. Nothing here "
        "runs autoregressively. What separates the rows is the time of day: the "
        "campaign starts at 00Z, so they are valid at dawn, early afternoon, "
        "evening and night. " + NON_MONOTONIC_NOTE,
        icon=":material/warning:",
    )

    st.markdown(
        "Once you read them as times of day, the pattern is obvious and it is a "
        "single coherent fault. The model is essentially unbiased at dawn "
        "(−0.12 °C), far too cold in the early afternoon (−5.33 °C), still "
        "slightly cold in the evening (−1.12 °C), and too warm at night "
        "(+1.30 °C). **It has not learnt the daily heating cycle.** It damps it."
    )
    st.caption(SYSTEMATIC_BIAS_NOTE)

    st.divider()
    st.markdown("#### Why a damped daily cycle is worse than a cold bias")

    st.markdown(
        "The impact model never sees a 6-hourly temperature. It sees a daily "
        "maximum and minimum, and turns them into evaporative demand through "
        "Hargreaves-Samani:"
    )
    st.latex(r"ET_0 \;\propto\; (T_{mean} + 17.8)\,\sqrt{T_{max} - T_{min}}")
    st.markdown(WHY_THE_RANGE_MATTERS)

    derived = DERIVED_DIURNAL_BIAS
    derived_cols = st.columns(3)
    derived_cols[0].metric("Implied Tmax bias", f"{derived['t_max_bias']:+.2f} °C")
    derived_cols[0].caption("from the 12Z sample, nearest peak heating")
    derived_cols[1].metric("Implied Tmin bias", f"{derived['t_min_bias']:+.2f} °C")
    derived_cols[1].caption("mean of the 06Z dawn and 00Z night samples")
    derived_cols[2].metric(
        "Implied range error", f"{derived['diurnal_range_bias']:+.2f} °C"
    )
    derived_cols[2].caption("what actually reaches ET0, under a square root")

    st.caption(
        "These three are **derived, not measured**: the evaluation samples every "
        "six hours, so it does not resolve the true daily extremes. " + derived["basis"]
    )

    st.divider()
    st.markdown("#### What that error does to the impact")
    st.markdown(
        "The curve below holds rainfall fixed and varies only the daily "
        "temperature *range* of the driving weather, so any change in yield is "
        "caused by the driver error alone. Each point is an ensemble, and every "
        "member uses the same weather seeds at every bias, which removes sampling "
        "noise from the comparison."
    )

    driver_controls = st.columns([2, 2])
    with driver_controls[0]:
        driver_members = st.slider("Ensemble members per bias", 5, 40, 15, 5)
    with driver_controls[1]:
        driver_rain = st.slider(
            "Rainfall anomaly for this experiment (%)", -60, 40, -20, 10,
            help="A season already under some water stress shows the effect most clearly.",
        ) / 100.0

    sweep = cached_diurnal_sweep(
        site_key, crop_key, driver_members, driver_rain, irrigation,
        derived["t_mean_bias"],
    )
    curve = sweep.groupby("diurnal_range_bias").agg(
        mean_yield=("actual_yield", "mean"),
        p10=("actual_yield", lambda s: s.quantile(0.10)),
        p90=("actual_yield", lambda s: s.quantile(0.90)),
    ).reset_index()

    cases = cached_driver_cases(site_key, crop_key, driver_rain, irrigation, 30)
    truth_yield = cases["perfect"]["yield"]
    mvula_yield = cases["full"]["yield"]
    naive_yield = cases["uniform"]["yield"]

    driver_figure = go.Figure()
    driver_figure.add_trace(
        go.Scatter(
            x=curve["diurnal_range_bias"], y=curve["p90"],
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        )
    )
    driver_figure.add_trace(
        go.Scatter(
            x=curve["diurnal_range_bias"], y=curve["p10"],
            fill="tonexty", fillcolor="rgba(41,128,185,0.20)",
            line=dict(width=0), name="10th to 90th percentile",
        )
    )
    driver_figure.add_trace(
        go.Scatter(
            x=curve["diurnal_range_bias"], y=curve["mean_yield"],
            line=dict(color="#1b4f72", width=3), mode="lines",
            name="Ensemble mean yield",
        )
    )
    driver_figure.add_trace(
        go.Scatter(
            x=[0.0], y=[truth_yield], mode="markers",
            marker=dict(size=15, color="#196f3d", symbol="circle",
                        line=dict(width=2, color="white")),
            name="Perfect weather data",
        )
    )
    driver_figure.add_trace(
        go.Scatter(
            x=[derived["diurnal_range_bias"]], y=[mvula_yield], mode="markers",
            marker=dict(size=17, color="#c0392b", symbol="x",
                        line=dict(width=2, color="white")),
            name=f"Driven by Mvula (range {derived['diurnal_range_bias']:+.2f} °C)",
        )
    )
    driver_figure.add_hline(
        y=truth_yield, line_dash="dash", line_color="#196f3d",
        annotation_text="Yield with perfect weather data", annotation_position="right",
    )
    driver_figure.update_layout(
        height=560,
        xaxis_title="Error in the daily temperature range of the driving weather (°C)",
        yaxis_title=f"{crop.name} yield (t/ha)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified",
    )
    st.plotly_chart(driver_figure, width="stretch")

    def error_percent(value: float) -> float:
        return 100.0 * (value - truth_yield) / max(truth_yield, 1e-6)

    driver_metrics = st.columns(3)
    driver_metrics[0].metric("Perfect weather data", f"{truth_yield:.2f} t/ha")
    driver_metrics[0].caption(
        f"the answer you are trying to get · demand {cases['perfect']['et0']:.0f} mm"
    )
    # Inverse colouring: an error away from the truth is bad in either direction,
    # so a positive yield error must not render as green good news.
    driver_metrics[1].metric(
        "If the error were a uniform offset", f"{naive_yield:.2f} t/ha",
        f"{error_percent(naive_yield):+.0f}%", delta_color="inverse",
    )
    driver_metrics[1].caption(
        f"the naive assumption · mean shifted {derived['t_mean_bias']:+.2f} °C only"
    )
    driver_metrics[2].metric(
        "Driven by the real Mvula error", f"{mvula_yield:.2f} t/ha",
        f"{error_percent(mvula_yield):+.0f}%", delta_color="inverse",
    )
    driver_metrics[2].caption(
        f"demand collapses to {cases['full']['et0']:.0f} mm · "
        f"range {cases['full']['dtr']:.1f} °C against {cases['perfect']['dtr']:.1f} °C"
    )

    understated = abs(error_percent(mvula_yield)) / max(abs(error_percent(naive_yield)), 1e-6)
    st.error(
        f"**The consequence points the wrong way, and the obvious diagnosis "
        f"understates it.** Damping the daily cycle cuts modelled evaporative "
        f"demand from {cases['perfect']['et0']:.0f} mm to "
        f"{cases['full']['et0']:.0f} mm and water-stressed days from "
        f"{cases['perfect']['stress']:.0f} to {cases['full']['stress']:.0f}, so the "
        f"impact model reports {mvula_yield:.2f} t/ha against a true "
        f"{truth_yield:.2f} t/ha — it **over-estimates the harvest by "
        f"{error_percent(mvula_yield):.0f}%**. A department relying on it would "
        f"conclude the season was far less damaging than it was, and would "
        f"under-warn farmers. Had you treated the same error as a simple cold "
        f"bias you would have predicted an error {understated:.0f} times smaller "
        f"and concluded it was tolerable.",
        icon=":material/warning:",
    )

    st.info(
        "**The lesson worth taking away.** Whether a weather model is good enough "
        "is not a property of the weather model. It is a property of three things "
        "together: the driver, the impact model it feeds, and the decision that "
        "rests on it. The headline skill number here is an RMSE, and the RMSE "
        "never told you about the diurnal cycle. What mattered was the *structure* "
        "of the error, not its size, because the impact model happened to depend "
        "on a difference rather than on a level. You cannot know which error "
        "structure matters until you know what the data will be used for."
    )

    st.warning(
        "**Be honest with the class about what this is.** This is a sensitivity "
        "experiment, not a coupling. Mvula produces single 6-hour analysis-forced "
        "steps, and you cannot drive a 140-day growing season with them. What is "
        "being done here is taking the *magnitude and structure* of a real, "
        "measured bias and asking what an error like it would do if it were "
        "present in the driving data. The bias is real; the pathway is "
        "illustrative. The Tmax and Tmin biases are inferred from six-hourly "
        "samples rather than measured. And Mvula does not forecast rainfall at "
        "all, which is what dominates this impact in the first place.",
        icon=":material/info:",
    )


# --------------------------------------------------------------------------
# Tab 6: the model
# --------------------------------------------------------------------------

with tab_model:
    st.subheader("What is actually being solved")

    st.markdown(
        "The model has three layers, and the whole thing is about 400 lines of Python."
    )

    st.markdown(
        "**1. Atmospheric demand.** Reference evapotranspiration comes from "
        "Hargreaves and Samani (1985), which needs only daily minimum and maximum "
        "temperature plus the latitude, so it can be run anywhere without hunting "
        "for humidity, wind and radiation data."
    )
    st.latex(r"ET_0 = 0.0023 \, R_a \, (T_{mean} + 17.8) \sqrt{T_{max} - T_{min}}")

    st.markdown(
        "**2. Root zone water balance.** FAO-56 (Allen et al., 1998) tracks the "
        "depletion $D_r$ of the root zone each day, where $P$ is rainfall, $RO$ "
        "runoff, $I$ irrigation and $DP$ deep percolation."
    )
    st.latex(r"D_{r,i} = D_{r,i-1} - (P_i - RO_i) - I_i + ET_{a,i} + DP_i")

    st.markdown(
        "Crop water demand is $ET_c = K_c \\, ET_0$. Once depletion passes the "
        "readily available water $RAW = p \\cdot TAW$, the crop can no longer meet "
        "that demand and transpiration is throttled by a stress coefficient $K_s$."
    )
    st.latex(r"K_s = \frac{TAW - D_r}{TAW - RAW}, \qquad ET_a = K_s \, ET_c")

    st.markdown(
        "**3. Yield response.** FAO-33 (Doorenbos and Kassam, 1979) converts the "
        "seasonal water deficit into a yield loss, stage by stage."
    )
    st.latex(
        r"\frac{Y_a}{Y_m} = \prod_{\text{stages}} \left[ 1 - K_{y,s} "
        r"\left( 1 - \frac{ET_{a,s}}{ET_{c,s}} \right) \right]"
    )

    st.markdown(
        "The stage-dependent $K_y$ is what makes timing matter. For maize it is "
        "1.5 during flowering against 0.4 during vegetative growth, so the same "
        "water deficit costs nearly four times as much yield if it lands in "
        "January rather than November."
    )

    st.divider()
    st.markdown("#### Current parameters")

    left, right = st.columns(2)
    with left:
        st.markdown(f"**Site: {site.name}**")
        st.dataframe(
            pd.DataFrame(
                {
                    "Property": ["Latitude", "Longitude", "Soil", "Field capacity",
                                 "Wilting point", "Available water", "Curve number",
                                 "Mean annual rainfall", "Planting"],
                    "Value": [
                        f"{site.latitude:.1f}", f"{site.longitude:.1f}", soil.name,
                        f"{soil.field_capacity:.2f} m3/m3",
                        f"{soil.wilting_point:.2f} m3/m3",
                        f"{soil.available_water_capacity:.0f} mm/m",
                        f"{soil.curve_number:.0f}",
                        f"{site.annual_rainfall:.0f} mm",
                        f"day {site.planting_day_of_year}",
                    ],
                }
            ),
            width="stretch", hide_index=True,
        )
    with right:
        st.markdown(f"**Crop: {crop.name}**")
        st.dataframe(
            pd.DataFrame(
                {
                    "Stage": [STAGE_LABELS[s] for s in STAGE_ORDER],
                    "Days": [crop.stage_lengths[s] for s in STAGE_ORDER],
                    "Ky": [crop.ky_by_stage[s] for s in STAGE_ORDER],
                }
            ),
            width="stretch", hide_index=True,
        )
        st.caption(
            f"Kc rises from {crop.kc_initial} to {crop.kc_mid} and falls to "
            f"{crop.kc_end}. Roots grow from {crop.rooting_depth_initial} m to "
            f"{crop.rooting_depth_max} m. Depletion fraction p = {crop.depletion_fraction}."
        )

    st.divider()
    st.error(
        f"**The honest caveat, which belongs in the lecture.** The "
        f"{driver.index_name} is observed. The crop model is standard and "
        f"defensible. The weak link is the step between them: the assumed "
        f"sensitivity of local rainfall to {driver.name} is an illustrative "
        f"default, not a fitted result. Replacing it with a regression against "
        f"observed station or reanalysis rainfall is the first thing anyone "
        f"should do before treating any of these numbers as a finding.",
        icon=":material/warning:",
    )

# -*- coding: utf-8 -*-
"""
Verify the package works before relying on it in front of a class.

Exercises every site and crop, both observed climate index records, irrigation,
warming, the forward scenario and the drought indices, and checks the results are
physically sensible rather than merely non-crashing. Run it on the lecture room
machine and on a couple of student laptops during the practical.

    python scripts/check_install.py
"""

import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from impact_model.climate import (
    CPC_ADVISORY,
    DRIVERS,
    TeleconnectionAssumption,
    aligned_indices,
    get_driver,
    load_index,
)
from impact_model.config import CROPS, DEFAULT_CROP, SITES, SOILS
from impact_model.experiment import (
    composite_by_phase,
    run_observed_record,
    run_scenario,
    run_single_season,
    sensitivity_sweep,
)

failures: list[str] = []
checks = 0


def check(condition: bool, message: str) -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(message)
        print(f"  FAIL  {message}")


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * 74)


print("=" * 74)
print("EGS4030/5030S drought impact model: installation check")
print("=" * 74)

started = time.perf_counter()

section("Dependencies")
for module in ("numpy", "pandas", "scipy", "plotly", "streamlit"):
    try:
        imported = __import__(module)
        print(f"  ok    {module:<12} {getattr(imported, '__version__', 'unknown')}")
        checks += 1
    except ImportError:
        failures.append(f"{module} is not installed")
        print(f"  FAIL  {module} is not installed")

section("Observed climate index records")
for driver_key, spec in DRIVERS.items():
    try:
        record = load_index(driver_key)
        check(len(record) > 30, f"{driver_key}: record should cover more than 30 years")
        check("phase" in record.columns, f"{driver_key}: missing the phase classification")

        counts = record["phase"].value_counts()
        check(counts.get("positive", 0) >= 3,
              f"{driver_key}: expected at least 3 {spec.positive_label} seasons")
        check(counts.get("negative", 0) >= 3,
              f"{driver_key}: expected at least 3 {spec.negative_label} seasons")

        standardized = record["index_standardized"]
        check(abs(float(standardized.mean())) < 0.05,
              f"{driver_key}: standardised index mean {standardized.mean():.2f} is not near zero")

        print(f"  ok    {spec.index_name:<18} {record.index.min()}-{record.index.max()} "
              f"({len(record)} seasons)  "
              + ", ".join(f"{spec.phase_label(k)} {v}" for k, v in counts.items()))
    except Exception:
        failures.append(f"Could not load the {driver_key} record")
        traceback.print_exc()

try:
    overlap = aligned_indices()
    correlation = overlap.attrs["correlation"]
    check(0.2 < correlation < 0.9,
          f"ENSO-IOD correlation {correlation:.2f} is outside the expected range")
    print(f"  ok    the two indices overlap over {len(overlap)} seasons, r = {correlation:.2f}")
except Exception:
    failures.append("Could not align the two index records")
    traceback.print_exc()

section("Current El Nino advisory (the live event)")
try:
    check(CPC_ADVISORY["nino34_anomaly"] >= 1.5,
          "CPC Nino 3.4 in the advisory should still be a strong El Nino")
    check(CPC_ADVISORY["historic_probability_ond"] >= 0.5,
          "The October-December historic-event probability should be at least even odds")
    check("October" in CPC_ADVISORY["issued"] or "November" in CPC_ADVISORY["issued"],
          "The cited CPC discussion should be the October or November 2026 issue")
    print(
        f"  ok    CPC {CPC_ADVISORY['issued']}: Nino 3.4 "
        f"{CPC_ADVISORY['nino34_anomaly']:+.1f} degC, historic OND "
        f"{CPC_ADVISORY['historic_probability_ond']:.0%}"
    )
except Exception:
    failures.append("CPC advisory check raised an exception")
    traceback.print_exc()

section("Single seasons: every site with its default crop")
for site_key, site in SITES.items():
    crop_key = DEFAULT_CROP[site_key]
    crop = CROPS[crop_key]
    try:
        wet, _ = run_single_season(site, crop, rainfall_anomaly=0.30, seed=11)
        dry, _ = run_single_season(site, crop, rainfall_anomaly=-0.60, seed=11)

        check(
            dry.actual_yield < wet.actual_yield,
            f"{site_key}: a dry season should not out-yield a wet one",
        )
        check(
            0.0 <= dry.relative_yield <= 1.0 and 0.0 <= wet.relative_yield <= 1.0,
            f"{site_key}: relative yield outside 0-1",
        )
        check(
            wet.season_et_actual <= wet.season_et_potential + 1e-6,
            f"{site_key}: actual transpiration exceeded potential",
        )
        check(
            dry.water_stress_days >= wet.water_stress_days,
            f"{site_key}: dry season had fewer stress days than the wet one",
        )
        print(
            f"  ok    {site.name:<38} wet {wet.actual_yield:5.2f}  "
            f"dry {dry.actual_yield:5.2f} t/ha"
        )
    except Exception:
        failures.append(f"{site_key} single season raised an exception")
        traceback.print_exc()

section("Every crop runs at a single site")
for crop_key, crop in CROPS.items():
    try:
        result, _ = run_single_season(SITES["free_state"], crop, rainfall_anomaly=-0.2, seed=3)
        check(result.actual_yield >= 0, f"{crop_key}: negative yield")
        print(f"  ok    {crop.name:<38} {result.actual_yield:5.2f} t/ha")
    except Exception:
        failures.append(f"{crop_key} raised an exception")
        traceback.print_exc()

section("Water balance closes")
try:
    result, _ = run_single_season(SITES["limpopo"], CROPS["maize"], -0.2, seed=5)
    daily = result.daily
    # Storage is measured against the initial root zone, and root growth is an
    # explicit input, so every term is accounted for and the residual must vanish.
    storage_change = float(
        daily["soil_water"].iloc[-1] - result.metadata["initial_soil_water"]
    )
    inputs = float(
        daily["precip"].sum() - daily["runoff"].sum() + daily["root_zone_gain"].sum()
    )
    outputs = float(daily["et_actual"].sum() + daily["deep_percolation"].sum())
    residual = inputs - outputs - storage_change
    check(
        abs(residual) < 0.5,
        f"Water balance residual {residual:.2f} mm should be within 0.5 mm of zero",
    )
    print(f"  ok    inputs {inputs:.0f} mm (of which {daily['root_zone_gain'].sum():.0f} mm "
          f"from root growth), outputs {outputs:.0f} mm, "
          f"storage change {storage_change:+.0f} mm, residual {residual:+.3f} mm")
except Exception:
    failures.append("Water balance check raised an exception")
    traceback.print_exc()

section("Irrigation and warming behave in the right direction")
try:
    rainfed, _ = run_single_season(SITES["limpopo"], CROPS["maize"], -0.5, seed=9)
    irrigated, _ = run_single_season(
        SITES["limpopo"], CROPS["maize"], -0.5, seed=9, irrigation_mm_per_week=30.0
    )
    warmed, _ = run_single_season(
        SITES["limpopo"], CROPS["maize"], -0.5, seed=9, temperature_shift=3.0
    )
    check(irrigated.actual_yield > rainfed.actual_yield, "Irrigation did not raise yield")
    check(warmed.season_et_potential > rainfed.season_et_potential,
          "Warming did not raise evaporative demand")
    print(f"  ok    rainfed {rainfed.actual_yield:.2f}, "
          f"irrigated {irrigated.actual_yield:.2f}, warmed {warmed.actual_yield:.2f} t/ha")
except Exception:
    failures.append("Irrigation or warming check raised an exception")
    traceback.print_exc()

section("Observed record and composite, for each driver")
for driver_key, spec in DRIVERS.items():
    try:
        run = run_observed_record("limpopo", "maize", driver=driver_key)
        seasons = run.seasons
        check(len(seasons) > 30, f"{driver_key}: expected more than 30 modelled seasons")
        check(seasons["spi3"].notna().sum() > 20,
              f"{driver_key}: SPI3 is missing for too many seasons")

        spi = run.monthly["spi3"].dropna()
        check(abs(float(spi.mean())) < 0.35,
              f"{driver_key}: SPI3 mean {spi.mean():.2f} is far from zero")
        check(0.6 < float(spi.std()) < 1.5,
              f"{driver_key}: SPI3 standard deviation {spi.std():.2f} is implausible")

        composite = composite_by_phase(seasons)
        positive = composite.loc["positive", "mean_yield"]
        negative = composite.loc["negative", "mean_yield"]
        anomaly = composite.loc["positive", "yield_anomaly_percent"]

        # A composite loss beyond about 60% would mean the teleconnection
        # defaults have drifted back to implausibly strong values.
        check(-60.0 < anomaly < 40.0,
              f"{driver_key}: composite yield anomaly {anomaly:+.0f}% is not credible")

        # The ordering is deliberately not asserted here. With the IOD's weaker
        # teleconnection and only seven events in the record, the composite is
        # not separable from sampling noise and flips sign on some seeds. That
        # is a result, not a bug, so the mechanism is tested without noise below.
        print(f"  ok    {spec.index_name:<18} {len(seasons)} seasons, "
              f"{spec.positive_label} {positive:.2f} vs {spec.negative_label} "
              f"{negative:.2f} t/ha ({anomaly:+.0f}%)")
    except Exception:
        failures.append(f"{driver_key} observed record raised an exception")
        traceback.print_exc()

section("Teleconnection mechanism, with the noise switched off")
for driver_key, spec in DRIVERS.items():
    try:
        silent = TeleconnectionAssumption(
            rainfall_sensitivity=spec.default_sensitivity,
            noise_std=0.0,
            driver_key=driver_key,
        )
        composite = composite_by_phase(
            run_observed_record("limpopo", "maize", driver=driver_key, assumption=silent).seasons
        )
        positive = composite.loc["positive", "mean_yield"]
        negative = composite.loc["negative", "mean_yield"]
        check(positive < negative,
              f"{driver_key}: with no noise, {spec.positive_label} must yield less "
              f"than {spec.negative_label}")
        print(f"  ok    {spec.index_name:<18} {spec.positive_label} {positive:.2f} vs "
              f"{spec.negative_label} {negative:.2f} t/ha")
    except Exception:
        failures.append(f"{driver_key} noise-free composite raised an exception")
        traceback.print_exc()

section("Teleconnection sign responds to the assumption")
try:
    reversed_link = TeleconnectionAssumption(rainfall_sensitivity=0.14, noise_std=0.0)
    default_link = TeleconnectionAssumption(rainfall_sensitivity=-0.14, noise_std=0.0)
    high = run_observed_record("limpopo", "maize", assumption=reversed_link)
    low = run_observed_record("limpopo", "maize", assumption=default_link)
    high_positive = composite_by_phase(high.seasons).loc["positive", "mean_yield"]
    low_positive = composite_by_phase(low.seasons).loc["positive", "mean_yield"]
    check(high_positive > low_positive,
          "Reversing the teleconnection sign did not reverse the yield response")
    print(f"  ok    negative sensitivity {low_positive:.2f} t/ha, "
          f"positive sensitivity {high_positive:.2f} t/ha")
except Exception:
    failures.append("Teleconnection sensitivity check raised an exception")
    traceback.print_exc()

section("Forward scenario on a strong El Nino")
try:
    scenario = run_scenario("limpopo", "maize", index_value=2.4, driver="enso", members=30)
    members = scenario.members["actual_yield"]
    baseline = scenario.baseline["actual_yield"]

    check(scenario.phase == "positive", "Nino 3.4 of +2.4 degC should classify as El Nino")
    check(scenario.index_standardized > 1.5,
          f"+2.4 degC should be more than 1.5 sd, got {scenario.index_standardized:.2f}")
    check(members.mean() < baseline.mean(),
          "The El Nino ensemble should not out-yield the neutral baseline")
    check(len(scenario.analogues) == 5, "Expected five observed analogues")

    # The distributions must overlap. If a strong El Nino guaranteed failure the
    # model would be lying about how much of seasonal rainfall it cannot explain.
    overlap = float((members > baseline.median()).mean())
    check(overlap > 0.02,
          f"Only {overlap:.0%} of El Nino members beat the neutral median; "
          "the teleconnection is behaving deterministically")

    worst_analogues = set(scenario.analogues.index) & {1982, 1997, 2015}
    check(len(worst_analogues) >= 3,
          f"Expected 1982, 1997 and 2015 among the analogues, got {sorted(scenario.analogues.index)}")

    print(f"  ok    {scenario.index_standardized:+.2f} sd, "
          f"mean {members.mean():.2f} vs {baseline.mean():.2f} t/ha "
          f"({scenario.yield_loss_percent:+.0f}%), {overlap:.0%} of members still beat "
          "the neutral median")
    print(f"  ok    analogues {sorted(scenario.analogues.index)}")
except Exception:
    failures.append("Forward scenario raised an exception")
    traceback.print_exc()

section("Ensemble sweep")
try:
    sweep = sensitivity_sweep("limpopo", "maize", np.array([-0.4, 0.0, 0.4]), members=8)
    means = sweep.groupby("rainfall_anomaly")["actual_yield"].mean()
    check(bool(means.is_monotonic_increasing), "Mean yield is not monotonic in rainfall")
    spread = sweep[np.isclose(sweep["rainfall_anomaly"], 0.0)]["actual_yield"]
    check(float(spread.std()) > 0.01, "Ensemble members are identical; timing has no effect")
    print(f"  ok    means {', '.join(f'{v:.2f}' for v in means)} t/ha; "
          f"spread at zero anomaly {spread.std():.2f} t/ha")
except Exception:
    failures.append("Sensitivity sweep raised an exception")
    traceback.print_exc()

section("Driver error: weather model skill feeding the impact model")
try:
    from impact_model.driver_error import (
        DERIVED_DIURNAL_BIAS,
        MVULA_V5_AFRICA_T2M,
        ordered_entries,
    )
    from impact_model.experiment import diurnal_range_sweep, temperature_bias_sweep

    dawn = MVULA_V5_AFRICA_T2M[6]
    afternoon = MVULA_V5_AFRICA_T2M[12]
    night = MVULA_V5_AFRICA_T2M[24]

    check(dawn.valid_hour_utc == 6 and dawn.ic_hour_utc == 0,
          "The first entry should be an IC at 00Z valid at 06Z")
    check(night.valid_hour_utc == 0 and night.ic_hour_utc == 18,
          "The last entry should be an IC at 18Z valid at 00Z")
    check(dawn.beats_persistence, "The dawn step should beat persistence")
    check(not afternoon.beats_persistence, "The afternoon step should not beat persistence")
    check(afternoon.bias < -4.0, "The afternoon cold bias should exceed 4 degC")
    check(night.bias > 0.0, "The night step should be warm biased, not cold")

    # The defining evidence that these are times of day rather than lead times:
    # a decay curve cannot come back down.
    rmse_sequence = [entry.rmse for entry in ordered_entries()]
    check(rmse_sequence != sorted(rmse_sequence),
          "RMSE should be non-monotonic; a monotonic sequence would mean these "
          "really were forecast lead times")
    print("  ok    " + ", ".join(
        f"{s.label} RMSE {s.rmse:.2f} bias {s.bias:+.2f}" for s in ordered_entries()
    ))

    check(DERIVED_DIURNAL_BIAS["diurnal_range_bias"] < -4.0,
          "The implied diurnal range error should be a strong compression")
    print(f"  ok    implied Tmax {DERIVED_DIURNAL_BIAS['t_max_bias']:+.2f}, "
          f"Tmin {DERIVED_DIURNAL_BIAS['t_min_bias']:+.2f}, "
          f"range {DERIVED_DIURNAL_BIAS['diurnal_range_bias']:+.2f} degC")

    biases = np.array([afternoon.bias, dawn.bias, 0.0, 2.0])
    sweep = temperature_bias_sweep(
        "limpopo", "maize", biases, members=8, rainfall_anomaly=-0.2
    )
    means = sweep.groupby("temperature_bias")["actual_yield"].mean()
    demand = sweep.groupby("temperature_bias")["et_potential"].mean()

    check(bool(means.is_monotonic_decreasing),
          "Yield should fall as the temperature bias becomes warmer")
    check(bool(demand.is_monotonic_increasing),
          "Evaporative demand should rise as the temperature bias becomes warmer")

    truth = float(means.loc[0.0])
    at_dawn = float(means.loc[dawn.bias])
    check(abs(at_dawn - truth) < 0.15,
          f"The dawn bias should barely move the yield, moved {at_dawn - truth:+.2f} t/ha")

    # The real error is a compressed daily range, which reaches ET0 through the
    # square-root term and so bites harder than the same number of degrees
    # applied uniformly. If that ordering ever reverses, the tab's argument fails.
    range_bias = DERIVED_DIURNAL_BIAS["diurnal_range_bias"]
    mean_bias = DERIVED_DIURNAL_BIAS["t_mean_bias"]
    diurnal = diurnal_range_sweep(
        "limpopo", "maize", np.array([range_bias, 0.0]),
        members=8, rainfall_anomaly=-0.2, temperature_shift=mean_bias,
    )
    diurnal_means = diurnal.groupby("diurnal_range_bias")["actual_yield"].mean()
    diurnal_demand = diurnal.groupby("diurnal_range_bias")["et_potential"].mean()

    compressed = float(diurnal_means.loc[range_bias])
    uniform_only = float(diurnal_means.loc[0.0])
    check(compressed > uniform_only,
          "Compressing the daily range should inflate yield further than a "
          "uniform offset alone")
    check(float(diurnal_demand.loc[range_bias]) < float(diurnal_demand.loc[0.0]),
          "Compressing the daily range should reduce evaporative demand")
    check(abs(compressed - truth) > abs(uniform_only - truth),
          "The full error should be further from the truth than the naive "
          "uniform-offset assumption; otherwise the tab overstates its case")

    observed_range = diurnal.groupby("diurnal_range_bias")["mean_diurnal_range"].mean()
    check(observed_range.loc[range_bias] < observed_range.loc[0.0] - 3.0,
          "The generated weather did not actually narrow its diurnal range")

    print(f"  ok    perfect {truth:.2f}, uniform offset {uniform_only:.2f} "
          f"({uniform_only - truth:+.2f}), full error {compressed:.2f} "
          f"({compressed - truth:+.2f}) t/ha")
    print(f"  ok    daily range {observed_range.loc[0.0]:.1f} -> "
          f"{observed_range.loc[range_bias]:.1f} degC, demand "
          f"{diurnal_demand.loc[0.0]:.0f} -> {diurnal_demand.loc[range_bias]:.0f} mm")
except Exception:
    failures.append("Driver error check raised an exception")
    traceback.print_exc()

elapsed = time.perf_counter() - started

print("\n" + "=" * 74)
if failures:
    print(f"FAILED: {len(failures)} of {checks} checks did not pass ({elapsed:.1f} s)")
    for failure in failures:
        print(f"  - {failure}")
    sys.exit(1)

print(f"All {checks} checks passed in {elapsed:.1f} s.")
print("The model is ready. Run 'streamlit run app.py' for the dashboard.")
print("=" * 74)

# -*- coding: utf-8 -*-
"""
Command-line demonstration of the drought impact chain.

Run this first in the lecture, before opening the dashboard. It shows the whole
model working in a few seconds of plain text output, which makes the point that
a useful impact model does not have to be a supercomputer job.

    python scripts/run_demo.py --site limpopo --crop maize
    python scripts/run_demo.py --site free_state --anomaly -0.4
    python scripts/run_demo.py --site limpopo --observed
    python scripts/run_demo.py --site limpopo --observed --driver iod
    python scripts/run_demo.py --site limpopo --scenario 2.4
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from impact_model.climate import CPC_ADVISORY, DRIVERS, get_driver, latest_observation
from impact_model.config import CROPS, DEFAULT_CROP, SITES, SOILS, STAGE_LABELS
from impact_model.experiment import (
    composite_by_phase,
    run_observed_record,
    run_scenario,
    run_single_season,
    sensitivity_sweep,
)


def _rule(title: str = "", width: int = 78) -> None:
    if title:
        print(f"\n{title}")
        print("-" * width)
    else:
        print("=" * width)


def show_single_season(site_key: str, crop_key: str, anomaly: float, seed: int) -> None:
    site = SITES[site_key]
    crop = CROPS[crop_key]
    soil = SOILS[site.soil]

    result, _ = run_single_season(
        site, crop, rainfall_anomaly=anomaly, seed=seed
    )

    _rule()
    print(f"SINGLE SEASON: {crop.name} at {site.name}")
    _rule()
    print(f"  Soil                  {soil.name} "
          f"({soil.available_water_capacity:.0f} mm available water per metre)")
    print(f"  Season length         {crop.season_length} days")
    print(f"  Rainfall anomaly      {anomaly:+.0%}")

    _rule("SEASON WATER BALANCE")
    print(f"  Rainfall                    {result.season_rainfall:7.1f} mm")
    print(f"  Runoff                      {result.metadata['season_runoff']:7.1f} mm")
    print(f"  Deep percolation            {result.metadata['season_percolation']:7.1f} mm")
    print(f"  Potential transpiration     {result.season_et_potential:7.1f} mm")
    print(f"  Actual transpiration        {result.season_et_actual:7.1f} mm")
    deficit = result.season_et_potential - result.season_et_actual
    print(f"  Water deficit               {deficit:7.1f} mm "
          f"({100 * deficit / result.season_et_potential:.0f}% of demand unmet)")
    print(f"  Days under water stress     {result.water_stress_days:7d}")

    _rule("WHERE THE YIELD WAS LOST (FAO-33)")
    header = f"  {'Stage':<22}{'Days':>5}{'Rain':>8}{'ETc':>8}{'ETa':>8}{'Deficit':>9}{'Ky':>6}{'Yield x':>9}"
    print(header)
    for _, row in result.stage_summary.iterrows():
        print(
            f"  {STAGE_LABELS[row['stage']]:<22}"
            f"{int(row['days']):>5}"
            f"{row['rainfall']:>8.0f}"
            f"{row['et_potential']:>8.0f}"
            f"{row['et_actual']:>8.0f}"
            f"{row['deficit_ratio']:>8.0%}"
            f"{row['ky']:>6.2f}"
            f"{row['stage_yield_factor']:>9.3f}"
        )

    _rule("IMPACT")
    print(f"  Potential yield             {result.potential_yield:7.2f} t/ha")
    print(f"  Modelled yield              {result.actual_yield:7.2f} t/ha")
    print(f"  Relative yield              {result.relative_yield:7.1%}")
    print(f"  Yield loss                  {result.yield_loss_fraction:7.1%}")
    print()


def show_sensitivity(site_key: str, crop_key: str) -> None:
    anomalies = np.arange(-0.6, 0.45, 0.15)
    sweep = sensitivity_sweep(site_key, crop_key, anomalies, members=15)
    summary = sweep.groupby("rainfall_anomaly").agg(
        rainfall=("season_rainfall", "mean"),
        mean_yield=("actual_yield", "mean"),
        p10=("actual_yield", lambda s: s.quantile(0.10)),
        p90=("actual_yield", lambda s: s.quantile(0.90)),
    )

    _rule("YIELD RESPONSE TO SEASONAL RAINFALL (15-member ensemble each)")
    print(f"  {'Anomaly':>9}{'Rainfall':>11}{'Mean yield':>13}{'10th pct':>11}{'90th pct':>11}")
    for anomaly, row in summary.iterrows():
        print(
            f"  {anomaly:>8.0%}"
            f"{row['rainfall']:>10.0f}mm"
            f"{row['mean_yield']:>11.2f} t/ha"
            f"{row['p10']:>10.2f}  "
            f"{row['p90']:>10.2f}"
        )
    print("\n  The spread at a fixed anomaly is caused only by rainfall timing.")
    print("  Two seasons with identical totals do not give identical yields.")
    print()


def show_observed(site_key: str, crop_key: str, driver_key: str):
    driver = get_driver(driver_key)
    run = run_observed_record(site_key, crop_key, driver=driver)
    record = run.seasons
    composite = composite_by_phase(record)

    _rule(f"OBSERVED {driver.index_name.upper()} RECORD DRIVEN THROUGH THE IMPACT MODEL")
    print(f"  Site       {run.site.name}")
    print(f"  Crop       {run.crop.name}")
    print(f"  Driver     {driver.name} ({driver.index_name}, {driver.season_label} mean)")
    print(f"  Seasons    {record.index.min()}-{record.index.max()}")
    print(f"  Link       {run.assumption.source}")

    _rule(f"COMPOSITE BY {driver.name.upper()} PHASE")
    print(f"  {'Phase':<16}{'Seasons':>9}{'Mean yield':>13}{'Anomaly':>10}{'Rainfall':>11}{'Stress days':>13}")
    for phase, row in composite.iterrows():
        print(
            f"  {driver.phase_label(phase):<16}"
            f"{int(row['seasons']):>9}"
            f"{row['mean_yield']:>11.2f} t/ha"
            f"{row['yield_anomaly_percent']:>9.1f}%"
            f"{row['mean_rainfall']:>10.0f}mm"
            f"{row['mean_stress_days']:>13.1f}"
        )

    worst = record.nsmallest(5, "actual_yield")
    _rule("FIVE WORST MODELLED SEASONS")
    print(f"  {'Season':>7}{driver.index_name:>20}{'Phase':>16}{'Rainfall':>11}{'Yield':>11}{'SPI3':>8}")
    for year, row in worst.iterrows():
        print(
            f"  {year:>7}"
            f"{row['index_value']:>20.2f}"
            f"{driver.phase_label(row['phase']):>16}"
            f"{row['season_rainfall']:>10.0f}mm"
            f"{row['actual_yield']:>9.2f} t/ha"
            f"{row['spi3']:>8.2f}"
        )
    print()
    return run


def show_scenario(site_key: str, crop_key: str, driver_key: str, index_value: float, observed=None) -> None:
    driver = get_driver(driver_key)
    scenario = run_scenario(
        site_key, crop_key, index_value=index_value, driver=driver, observed=observed
    )

    _rule(f"FORWARD SCENARIO: {driver.index_name} = {index_value:+.2f} {driver.units}")
    print(f"  Phase                       {driver.phase_label(scenario.phase)}")
    print(f"  Standardised index          {scenario.index_standardized:+.2f} sd")

    if driver.key == "enso":
        latest = latest_observation()
        print(f"  Latest bundled observation  {latest['value']:+.2f} {driver.units} ({latest['label']})")
        print(f"  NOAA CPC {CPC_ADVISORY['issued']}    {CPC_ADVISORY['status']}, "
              f"Nino 3.4 {CPC_ADVISORY['nino34_anomaly']:+.1f} {driver.units} "
              f"in {CPC_ADVISORY['latest_month']}")

    members = scenario.members["actual_yield"]
    baseline = scenario.baseline["actual_yield"]

    _rule("MODELLED HARVEST, 60-MEMBER ENSEMBLE")
    print(f"  {'':<22}{'Scenario':>12}{'Neutral':>12}")
    for label, quantile in (("10th percentile", 0.10), ("Median", 0.50), ("90th percentile", 0.90)):
        print(f"  {label:<22}{members.quantile(quantile):>10.2f}  {baseline.quantile(quantile):>10.2f}")
    print(f"  {'Mean':<22}{members.mean():>10.2f}  {baseline.mean():>10.2f}")
    print(f"\n  Mean yield change vs neutral: {scenario.yield_loss_percent:+.1f}%")
    print(f"  Seasons below half the neutral median: "
          f"{100.0 * (members < 0.5 * baseline.median()).mean():.0f}% of members")

    _rule("CLOSEST OBSERVED ANALOGUES")
    print(f"  {'Season':>7}{driver.index_name:>20}{'Rainfall':>11}{'Modelled yield':>17}")
    for year, row in scenario.analogues.iterrows():
        print(
            f"  {year:>7}"
            f"{row['index_value']:>20.2f}"
            f"{row['season_rainfall']:>10.0f}mm"
            f"{row['actual_yield']:>12.2f} t/ha"
        )
    print("\n  The analogues are observed seasons, but the yields beside them are")
    print("  modelled, not measured. Check them against what actually happened.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--site", default="limpopo", choices=sorted(SITES), help="Study site")
    parser.add_argument("--crop", default=None, choices=sorted(CROPS), help="Crop (defaults to the site's usual crop)")
    parser.add_argument("--anomaly", type=float, default=-0.30, help="Seasonal rainfall anomaly as a fraction, e.g. -0.3")
    parser.add_argument("--seed", type=int, default=2026, help="Random seed for the weather generator")
    parser.add_argument("--driver", default="enso", choices=sorted(DRIVERS), help="Climate driver: enso (Nino 3.4, DJF) or iod (DMI, SON)")
    parser.add_argument("--observed", action="store_true", help="Also run the full observed index record")
    parser.add_argument("--scenario", type=float, default=None, metavar="VALUE", help="Run a forward scenario at this index value, e.g. 2.4 for a very strong El Nino")
    parser.add_argument("--no-sensitivity", action="store_true", help="Skip the rainfall sensitivity sweep")
    args = parser.parse_args()

    crop_key = args.crop or DEFAULT_CROP.get(args.site, "maize")

    show_single_season(args.site, crop_key, args.anomaly, args.seed)
    if not args.no_sensitivity:
        show_sensitivity(args.site, crop_key)

    observed = None
    if args.observed:
        observed = show_observed(args.site, crop_key, args.driver)
    if args.scenario is not None:
        show_scenario(args.site, crop_key, args.driver, args.scenario, observed=observed)


if __name__ == "__main__":
    main()

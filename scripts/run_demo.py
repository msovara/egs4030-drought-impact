# -*- coding: utf-8 -*-
"""
A quick text view of the model, without the dashboard.

    python scripts/run_demo.py --season 2015          one season in detail
    python scripts/run_demo.py --record               ENSO, rainfall and yield since 1979
    python scripts/run_demo.py --same-total           same rainfall, different timing
    python scripts/run_demo.py --cascade 1.5 2.5      the season ahead for a DJF index range

Add --soil sand|sandy_loam|loam or --planting early|standard|late to change
the setup.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from impact_model.climate import C3S_FORECAST, fit_teleconnection, forecast_djf_range  # noqa: E402
from impact_model.config import (  # noqa: E402
    DEFAULT_PLANTING, DEFAULT_SOIL, PLANTING_DATES, SOILS, STAGE_LABELS, STUDY_AREA,
)
from impact_model.experiment import (  # noqa: E402
    run_cascade, run_historical, run_one_season, same_total_experiment,
)


def rule(title: str = "") -> None:
    print(f"\n{title}\n" + "-" * 76 if title else "=" * 76)


def show_season(season: int, soil: str, planting: str) -> None:
    result, weather = run_one_season(season, soil, planting)
    rule()
    print(f"The {season}/{(season + 1) % 100:02d} season, {STUDY_AREA.name}")
    print(f"Soil: {SOILS[soil].name}; planted {weather.index[0]:%d %B %Y}")
    rule("Season water balance")
    print(f"  Rainfall (planting to harvest)  {result.season_rainfall:6.0f} mm")
    print(f"  Lost as runoff                  {result.metadata['season_runoff']:6.0f} mm")
    print(f"  Drained below the roots         {result.metadata['season_percolation']:6.0f} mm")
    print(f"  Crop water demand               {result.season_et_potential:6.0f} mm")
    print(f"  Water the crop actually used    {result.season_et_actual:6.0f} mm")
    print(f"  Days with water stress          {result.water_stress_days:6d}")
    rule("Where the yield was lost")
    print(f"  {'Stage':<26}{'Rain':>6}{'Demand':>8}{'Used':>6}{'Shortfall':>11}{'Ky':>5}{'Yield x':>9}")
    for _, row in result.stage_summary.iterrows():
        print(f"  {STAGE_LABELS[row['stage']]:<26}{row['rainfall']:>6.0f}{row['et_potential']:>8.0f}"
              f"{row['et_actual']:>6.0f}{row['deficit_ratio']:>11.0%}{row['ky']:>5.1f}"
              f"{row['stage_yield_factor']:>9.2f}")
    print(f"\n  Modelled yield: {result.relative_yield:.0%} of the water-unlimited yield")


def show_record(soil: str, planting: str) -> None:
    fit = fit_teleconnection()
    history = run_historical(soil, planting)
    rule()
    print(f"DJF relative Nino 3.4, Nov-Mar rainfall and modelled maize yield, "
          f"{history.index[0]}-{history.index[-1]}")
    rule("Fitted rainfall response to ENSO")
    print(f"  {fit.summary()}")
    rule("Seasons, sorted by index")
    print(f"  {'Season':<9}{'Index':>7}  {'Phase':<9}{'Rain':>6}{'Dry spell*':>12}{'Yield':>7}")
    for season, row in history.sort_values("relative_index", ascending=False).iterrows():
        print(f"  {season}/{(season + 1) % 100:02d}  {row['relative_index']:>+6.2f}  {row['phase']:<9}"
              f"{row['rainfall']:>6.0f}{row['flowering_dry_spell']:>12.0f}{row['relative_yield']:>7.0%}")
    print("  * longest run of days with less than 1 mm during flowering and grain fill")


def show_same_total(soil: str, planting: str) -> None:
    same = same_total_experiment(soil_key=soil, planting=planting)
    rule()
    print(f"Every season scaled to the same Nov-Mar total of {same.attrs['total_mm']:.0f} mm")
    ordered = same.sort_values("relative_yield")
    for label, rows in (("Lowest yields", ordered.head(5)), ("Highest yields", ordered.tail(5))):
        rule(label)
        for season, row in rows.iterrows():
            print(f"  {season}/{(season + 1) % 100:02d}  yield {row['relative_yield']:4.0%}   "
                  f"flowering rain {row['flowering_rainfall']:4.0f} mm   "
                  f"longest flowering dry spell {row['flowering_dry_spell']:3.0f} days")


def show_cascade(low: float, high: float, soil: str, planting: str) -> None:
    result = run_cascade((low, high), soil_key=soil, planting=planting)
    rule()
    print(f"The season ahead for a DJF relative Nino 3.4 between {low:+.2f} and {high:+.2f} degC")
    print(f"A 'poor' season is a yield below {result.poor_threshold:.0%} of potential, "
          f"the worst third of the historical seasons.")
    rule("Yield, as % of the water-unlimited yield")
    print(f"  {'':<34}{'10th':>6}{'median':>8}{'90th':>6}{'P(poor)':>9}")
    for case, row in result.stage_summary().iterrows():
        print(f"  {case:<34}{row['p10']:>6.0%}{row['median']:>8.0%}{row['p90']:>6.0%}{row['prob_poor']:>9.0%}")
    within = result.historical_in_range()
    rule("Past seasons with an index in this range")
    if within.empty:
        print("  None. The forecast range lies outside the historical record, so the fitted"
              "\n  line is being extended beyond the data.")
    for season, row in within.iterrows():
        print(f"  {season}/{(season + 1) % 100:02d}  index {row['relative_index']:+.2f}  rain "
              f"{row['rainfall']:.0f} mm  modelled yield {row['relative_yield']:.0%}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Text demonstration of the Mopani maize model.")
    parser.add_argument("--season", type=int, help="show one season in detail")
    parser.add_argument("--record", action="store_true", help="the historical record since 1979")
    parser.add_argument("--same-total", action="store_true", help="same rainfall, different timing")
    parser.add_argument("--cascade", nargs=2, type=float, metavar=("LOW", "HIGH"),
                        help="the season ahead for a DJF relative Nino 3.4 range")
    parser.add_argument("--soil", default=DEFAULT_SOIL, choices=sorted(SOILS))
    parser.add_argument("--planting", default=DEFAULT_PLANTING, choices=list(PLANTING_DATES))
    args = parser.parse_args()

    if args.season is not None:
        show_season(args.season, args.soil, args.planting)
    elif args.record:
        show_record(args.soil, args.planting)
    elif args.same_total:
        show_same_total(args.soil, args.planting)
    elif args.cascade:
        show_cascade(*args.cascade, args.soil, args.planting)
    else:
        forecast = forecast_djf_range()
        show_season(2015, args.soil, args.planting)
        if forecast:
            print(f"\nC3S forecast range: {forecast[0]:+.2f} to {forecast[1]:+.2f} degC "
                  f"({C3S_FORECAST['band']}). Try --cascade {forecast[0]:.2f} {forecast[1]:.2f}")
        print("\nSee --help for the other views.")


if __name__ == "__main__":
    main()

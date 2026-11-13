#!/usr/bin/env python3
"""Parameter tuning script for driver pricing model.
Sweeps key parameters on deterministic seeds:
  - wage_cents_per_hour
  - transit_rate_per_km
  - opening_discount (relative to referenceFeeCents)
  - step_slope (escalation rate)
  - urgent_multiplier
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Any, Dict, List

import pricing
from spread.client import Client
from dispatch import play_practice


def run_experiment(
    client: Client,
    level: int,
    seeds: List[str],
    wage_cents: int = 1300,
    transit_rate_km: int = 10,
    opening_discount: float = 0.90,
    step_slope: float = 0.06,
    urgent_start: float = 1.35,
) -> Dict[str, Any]:
    # Patch pricing parameters
    orig_wage = pricing.BASE_WAGE_PER_HOUR_CENTS
    orig_transit_km = pricing.TRANSIT_RATE_PER_KM_CENTS

    pricing.BASE_WAGE_PER_HOUR_CENTS = wage_cents
    pricing.TRANSIT_RATE_PER_KM_CENTS = transit_rate_km
    pricing.PARAM_DISCOUNT = opening_discount
    pricing.PARAM_STEP_SLOPE = step_slope
    pricing.PARAM_URGENT_START = urgent_start

    try:
        results = []
        for seed in seeds:
            world = client.create(level=level, seed=seed)
            try:
                t0 = time.time()
                play_practice(world, level)
                score = world.score()
                results.append({
                    "seed": seed,
                    "marginEur": score["marginCents"] / 100,
                    "revenueEur": score["revenueCents"] / 100,
                    "wonOrders": score["wonOrders"],
                    "onTimeShare": score["onTimeShare"],
                    "ranked": score["ranked"],
                    "duration": round(time.time() - t0, 1),
                })
            finally:
                try:
                    world.delete()
                except Exception:
                    pass

        avg_margin = sum(r["marginEur"] for r in results) / len(results)
        avg_on_time = sum(r["onTimeShare"] for r in results) / len(results)
        ranked_count = sum(1 for r in results if r["ranked"])

        return {
            "params": {
                "wage": wage_cents,
                "transit_km": transit_rate_km,
                "discount": opening_discount,
                "slope": step_slope,
                "urgent_start": urgent_start,
            },
            "avgMargin": round(avg_margin, 2),
            "avgOnTime": round(avg_on_time, 4),
            "rankedCount": f"{ranked_count}/{len(results)}",
            "runs": results,
        }
    finally:
        pricing.BASE_WAGE_PER_HOUR_CENTS = orig_wage
        pricing.TRANSIT_RATE_PER_KM_CENTS = orig_transit_km


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", type=int, default=2)
    parser.add_argument("--seeds", type=str, default="spread-1,spread-2")
    args = parser.parse_args()

    client = Client()
    seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]

    experiments = [
        # 1. Baseline current settings
        {"wage_cents": 1300, "transit_rate_km": 10, "opening_discount": 0.90, "step_slope": 0.06, "urgent_start": 1.35},
        # 2. Lower wage benchmark (€11.50/hr AKT base tier)
        {"wage_cents": 1150, "transit_rate_km": 8, "opening_discount": 0.90, "step_slope": 0.06, "urgent_start": 1.35},
        # 3. Tighter opening discount (0.82) with moderate escalation (0.05)
        {"wage_cents": 1250, "transit_rate_km": 8, "opening_discount": 0.82, "step_slope": 0.05, "urgent_start": 1.35},
        # 4. Moderate opening discount (0.85) with gentle escalation (0.05)
        {"wage_cents": 1300, "transit_rate_km": 10, "opening_discount": 0.85, "step_slope": 0.05, "urgent_start": 1.40},
        # 5. Higher wage (€14.00/hr) with aggressive opening discount (0.78)
        {"wage_cents": 1400, "transit_rate_km": 10, "opening_discount": 0.78, "step_slope": 0.06, "urgent_start": 1.45},
    ]

    print(f"Running {len(experiments)} parameter configurations on Level {args.level} across seeds: {seeds}\n")
    print(f"{'Config':<6} | {'Wage':<6} | {'Rate/km':<7} | {'Disc':<5} | {'Slope':<5} | {'UrgStart':<8} | {'Avg Margin':<12} | {'On-Time':<8} | {'Ranked':<7}")
    print("-" * 85)

    best_config = None
    best_margin = -float("inf")

    for idx, cfg in enumerate(experiments, 1):
        res = run_experiment(client, args.level, seeds, **cfg)
        p = res["params"]
        all_ranked = res["rankedCount"] == f"{len(seeds)}/{len(seeds)}"
        is_best = ""
        if all_ranked and res["avgMargin"] > best_margin:
            best_margin = res["avgMargin"]
            best_config = (idx, cfg, res)
            is_best = " *"

        print(
            f"{idx:<6} | €{p['wage']/100:<5.2f} | €{p['transit_km']/100:<6.2f} | "
            f"{p['discount']:<5.2f} | {p['slope']:<5.2f} | {p['urgent_start']:<8.2f} | "
            f"€{res['avgMargin']:>10,.2f} | {res['avgOnTime']:>6.1%} | {res['rankedCount']:<7}{is_best}"
        )

    if best_config:
        b_idx, b_cfg, b_res = best_config
        print("\n" + "=" * 65)
        print(f"BEST CONFIG: #{b_idx}")
        print(f"Average Margin: €{b_res['avgMargin']:,.2f} ({b_res['avgOnTime']:.1%} on-time, {b_res['rankedCount']} ranked)")
        print(f"Parameters: {b_cfg}")
        print("=" * 65)


if __name__ == "__main__":
    main()

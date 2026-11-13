#!/usr/bin/env python3
"""Benchmark runner for Spread.
Runs one or multiple practice seeds to evaluate and compare dispatch strategies.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from spread.client import Client, SpreadError
from spread.types import Score
from dispatch import Desk, play_practice, report, WAKE_ON


def run_single_seed(client: Client, level: int, seed: str, verbose: bool = False) -> dict[str, Any]:
    """Runs a single practice seed and returns summary score metrics."""
    t0 = time.time()
    world = client.create(level=level, seed=seed)
    try:
        if verbose:
            print(f"\n--- Running Seed: {seed} (Level {level}, World {world.id}) ---")
        play_practice(world, level)
        score: Score = world.score()
        duration = time.time() - t0

        result = {
            "seed": seed,
            "level": level,
            "worldId": world.id,
            "marginEur": score["marginCents"] / 100,
            "revenueEur": score["revenueCents"] / 100,
            "wonOrders": score["wonOrders"],
            "onTimeShare": score["onTimeShare"],
            "undeliveredShare": score["undeliveredShare"],
            "ranked": score["ranked"],
            "durationSec": round(duration, 2),
        }
        return result
    finally:
        try:
            world.delete()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark dispatch strategy across seeds")
    parser.add_argument("--level", type=int, choices=range(1, 9), default=8, help="Level 1-8 (default: 8)")
    parser.add_argument("--seeds", type=str, default="spread-1,spread-2,spread-3", help="Comma-separated seed list")
    parser.add_argument("--verbose", action="store_true", help="Print step reports for each day")
    parser.add_argument("--output", type=str, default=None, help="JSON file path to save benchmark results")
    args = parser.parse_args()

    client = Client()
    seed_list = [s.strip() for s in args.seeds.split(",") if s.strip()]

    print(f"Starting benchmark on {len(seed_list)} seeds at Level {args.level}...")
    results = []

    for seed in seed_list:
        try:
            res = run_single_seed(client, args.level, seed, verbose=args.verbose)
            results.append(res)
            status = "RANKED" if res["ranked"] else "NOT RANKED"
            print(
                f"[{res['seed']}] Margin: €{res['marginEur']:>10,.2f} | "
                f"Revenue: €{res['revenueEur']:>10,.2f} | "
                f"Orders: {res['wonOrders']:>4} | "
                f"On-Time: {res['onTimeShare']:>6.1%} | "
                f"{status} ({res['durationSec']}s)"
            )
        except Exception as e:
            print(f"[{seed}] Failed: {e}", file=sys.stderr)

    if not results:
        print("No successful runs.")
        return

    # Print summary table
    total_margin = sum(r["marginEur"] for r in results)
    avg_margin = total_margin / len(results)
    avg_on_time = sum(r["onTimeShare"] for r in results) / len(results)
    ranked_count = sum(1 for r in results if r["ranked"])

    print("\n" + "=" * 65)
    print(f"BENCHMARK SUMMARY (Level {args.level}, {len(results)} seeds)")
    print("=" * 65)
    print(f"Average Margin:      €{avg_margin:>10,.2f}")
    print(f"Total Margin:        €{total_margin:>10,.2f}")
    print(f"Average On-Time:     {avg_on_time:>10.1%}")
    print(f"Ranked Seeds:        {ranked_count}/{len(results)}")
    print("=" * 65)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w") as f:
            json.dump({"summary": {"avgMargin": avg_margin, "avgOnTime": avg_on_time, "ranked": ranked_count}, "runs": results}, f, indent=2)
        print(f"Saved benchmark results to {args.output}")


if __name__ == "__main__":
    main()

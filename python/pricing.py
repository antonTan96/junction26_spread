"""Driver fee pricing calculation engine based on Finnish labor benchmarks
and road network distances.

Grounds pricing in:
1. Finnish Collective Agreement (AKT transport/logistics) benchmark (~€12.00–€14.00/hr, base €13.00/hr).
2. Public Transit Return/Positioning model (VR train / Matkahuolto bus fare structure: €5.00 base + €0.10/km).
3. Handling surcharges: EV charging stop (+40 min), transfer plates (+30 min).
4. Non-decreasing 1-to-48 step fee schedules in integer game-euro cents.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from spread.types import FeeStep, Order, PostAction, PriceRequest, StopRef

# Economic & operational constants (per python/pricing_design.md)
BASE_WAGE_PER_HOUR_CENTS: int = 1300     # €13.00 / hr (AKT benchmark midpoint)
MIN_GIG_FEE_CENTS: int = 1500            # €15.00 absolute minimum floor per gig
TRANSIT_BASE_FARE_CENTS: int = 500       # €5.00 base public transit booking / connection
TRANSIT_RATE_PER_KM_CENTS: int = 10      # €0.10 / km public transit return rate
EV_CHARGING_MINUTES: int = 40            # Handling time for EV charging stop
TRANSFER_PLATES_MINUTES: int = 30        # Handling time for transfer plates

# Cached map lookup table: (from_place, to_place) -> (km, minutes)
_CACHED_MAP_ROADS: Optional[Dict[Tuple[str, str], Tuple[float, int]]] = None


def find_map_file() -> Optional[Path]:
    """Locates data/map.json across standard workspace layouts."""
    candidates = [
        Path(__file__).resolve().parent.parent / "data" / "map.json",
        Path(__file__).resolve().parent / "data" / "map.json",
        Path("data/map.json").resolve(),
        Path("junction26_spread/data/map.json").resolve(),
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def load_map_roads(path: Optional[Union[str, Path]] = None) -> Dict[Tuple[str, str], Tuple[float, int]]:
    """Loads and caches road distances (km) and driving times (minutes) between places."""
    global _CACHED_MAP_ROADS
    if _CACHED_MAP_ROADS is not None and path is None:
        return _CACHED_MAP_ROADS

    map_path = Path(path) if path else find_map_file()
    roads: Dict[Tuple[str, str], Tuple[float, int]] = {}
    if map_path and map_path.is_file():
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for road in data.get("roads", []):
                roads[(road["from"], road["to"])] = (float(road["km"]), int(road["minutes"]))
        except Exception:
            pass

    if path is None:
        _CACHED_MAP_ROADS = roads
    return roads


def calculate_driver_cost(
    driving_minutes: int,
    distance_km: float,
    with_charging: bool = False,
    with_plates: bool = False,
    is_return_trip: bool = False,
    wage_cents_per_hour: int = BASE_WAGE_PER_HOUR_CENTS,
    charging_count: int = 0,
    plates_count: int = 0,
) -> int:
    """Calculates fair driver baseline cost in integer cents.

    Formulation:
      C_drive = (driving_minutes / 60.0) * wage_cents_per_hour
      C_handling = (handling_minutes / 60.0) * wage_cents_per_hour
      C_return = TRANSIT_BASE_FARE_CENTS (+ distance_km * TRANSIT_RATE_PER_KM_CENTS if not return)
      C_driver = max(round(C_drive + C_handling + C_return), MIN_GIG_FEE_CENTS)
    """
    n_charging = charging_count if charging_count > 0 else (1 if with_charging else 0)
    n_plates = plates_count if plates_count > 0 else (1 if with_plates else 0)

    drive_cost = (driving_minutes / 60.0) * wage_cents_per_hour
    handling_minutes = (EV_CHARGING_MINUTES * n_charging) + (TRANSFER_PLATES_MINUTES * n_plates)
    handling_cost = (handling_minutes / 60.0) * wage_cents_per_hour

    if is_return_trip:
        return_cost = float(TRANSIT_BASE_FARE_CENTS)
    else:
        return_cost = float(TRANSIT_BASE_FARE_CENTS) + round(distance_km * TRANSIT_RATE_PER_KM_CENTS)

    total_cost = round(drive_cost + handling_cost + return_cost)
    return max(int(total_cost), MIN_GIG_FEE_CENTS)


def build_fee_schedule(
    base_fee_cents: int,
    now: int,
    level: int,
    is_urgent: bool = False,
    last_pickup_at: Optional[int] = None,
) -> List[FeeStep]:
    """Generates a valid 1-to-48 step non-decreasing fee schedule in integer cents.

    Constraints:
      1. Length between 1 and 48 steps.
      2. Non-decreasing timestamps (at).
      3. Strictly non-decreasing fees (feeCents).
      4. Level 1 must have exactly 1 step.
    """
    base_fee = max(int(base_fee_cents), MIN_GIG_FEE_CENTS)

    # Level 1 constraint: exactly one step
    if level == 1:
        fee = int(round(base_fee * 1.50)) if is_urgent else base_fee
        return [{"at": int(now), "feeCents": max(1, fee)}]

    # Check if order is entering urgent window (3 hours before lastPickupAt)
    if last_pickup_at is not None and (now >= last_pickup_at - 180):
        is_urgent = True

    if is_urgent:
        # Urgent schedule: 6 steps spaced 25 min apart, starting at 1.35x and stepping up to 2.10x
        steps: List[FeeStep] = []
        prev_fee = 0
        for k in range(6):
            t_k = int(now + k * 25)
            mult = 1.35 + 0.15 * k  # k=0: 1.35, k=1: 1.50, ..., k=5: 2.10
            fee_k = max(prev_fee, max(1, int(round(base_fee * mult))))
            steps.append({"at": t_k, "feeCents": fee_k})
            prev_fee = fee_k
        return steps

    # Normal schedule: gentle step-up (+6% per step) to avoid teaching drivers to wait
    if last_pickup_at is not None and last_pickup_at > now:
        time_to_urgent = max(0, (last_pickup_at - 180) - now)
        if time_to_urgent < 180:
            delta_t = 30
            num_steps = min(8, max(1, time_to_urgent // 30))
        else:
            delta_t = 60
            num_steps = min(8, max(1, time_to_urgent // 60))
    else:
        delta_t = 60
        num_steps = 6

    steps: List[FeeStep] = []
    prev_fee = 0
    for k in range(num_steps):
        t_k = int(now + k * delta_t)
        mult = 1.0 + 0.06 * k
        fee_k = max(prev_fee, max(1, int(round(base_fee * mult))))
        steps.append({"at": t_k, "feeCents": fee_k})
        prev_fee = fee_k

    return steps


def extract_route_metrics(
    order: Order,
    stops: List[StopRef],
    map_roads: Optional[Dict[Tuple[str, str], Tuple[float, int]]] = None,
) -> Tuple[int, float, int, int, bool]:
    """Extracts driving minutes, road distance km, handling stops, and return-trip indicator.

    Returns:
      (driving_minutes, distance_km, charging_count, plates_count, is_return_trip)
    """
    roads = map_roads if map_roads is not None else load_map_roads()

    if not stops:
        # Default fallback to order legs if stops are omitted
        places: List[str] = []
        charging_count = 0
        for leg in order.get("legs", []):
            places.append(leg["pickup"]["placeId"])
            places.append(leg["delivery"]["placeId"])
            car = leg.get("car", {})
            if car.get("electric") and (car.get("chargePercent") is not None) and car["chargePercent"] < 30:
                charging_count += 1
        plates_count = 0
    else:
        places = []
        charging_count = 0
        plates_count = 0
        for s in stops:
            leg_idx = s.get("leg", 0)
            if leg_idx < len(order["legs"]):
                leg = order["legs"][leg_idx]
                place_id = leg["pickup"]["placeId"] if s.get("kind") == "pickup" else leg["delivery"]["placeId"]
                places.append(place_id)
            if s.get("withCharging"):
                charging_count += 1
            if s.get("withPlates"):
                plates_count += 1

    total_minutes = 0
    total_km = 0.0

    if len(places) <= 1:
        total_minutes = 25
        total_km = 12.0
    else:
        for i in range(len(places) - 1):
            pair = (places[i], places[i + 1])
            if pair in roads:
                km, minutes = roads[pair]
                total_km += km
                total_minutes += minutes
            elif pair[0] == pair[1]:
                total_km += 12.0
                total_minutes += 25
            else:
                total_km += 50.0
                total_minutes += 45

    is_return_trip = (len(places) >= 2 and places[0] == places[-1])
    return total_minutes, total_km, charging_count, plates_count, is_return_trip


def calculate_gig_fee_schedule(
    order: Order,
    request: Optional[PriceRequest],
    action_or_stops: Union[PostAction, List[StopRef]],
    now: int,
    level: int,
    is_urgent: bool = False,
    map_roads: Optional[Dict[Tuple[str, str], Tuple[float, int]]] = None,
) -> List[FeeStep]:
    """Calculates fair driver baseline cost and generates a valid non-decreasing fee schedule.

    Used by dispatch.py to replace heuristic fee calculation.
    """
    if isinstance(action_or_stops, dict) and "stops" in action_or_stops:
        stops = action_or_stops["stops"]
    elif isinstance(action_or_stops, list):
        stops = action_or_stops
    else:
        stops = []

    driving_minutes, distance_km, charging_count, plates_count, is_return = extract_route_metrics(
        order, stops, map_roads=map_roads
    )

    driver_cost = calculate_driver_cost(
        driving_minutes=driving_minutes,
        distance_km=distance_km,
        is_return_trip=is_return,
        charging_count=charging_count,
        plates_count=plates_count,
    )

    # Reconcile with request referenceFeeCents if present
    if request is not None and "referenceFeeCents" in request:
        ref_fee = request["referenceFeeCents"]
        num_pickups = sum(1 for s in stops if s.get("kind") == "pickup") or 1
        total_legs = max(1, len(order.get("legs", [])))
        scaled_ref_fee = round(ref_fee * (num_pickups / total_legs))
        # Protect against lowballing while respecting driver labor/transit baseline
        discount = 1.0 if level == 1 else 0.90
        base_fee = max(driver_cost, int(round(discount * scaled_ref_fee)))
    else:
        base_fee = driver_cost

    base_fee = max(base_fee, MIN_GIG_FEE_CENTS)

    last_pickup = order.get("lastPickupAt")
    return build_fee_schedule(
        base_fee_cents=base_fee,
        now=now,
        level=level,
        is_urgent=is_urgent,
        last_pickup_at=last_pickup,
    )


# Driver Fee Pricing Specification & Algorithmic Design

**Target Audience:** `@coder`, `@verifier`, `@coordinator`  
**Location:** `python/pricing_design.md`  
**Status:** Approved for Implementation  

---

## 1. Executive Summary & Objective

In Spread, our dispatch system posts freelance driver gigs across Finland. Freelance drivers decide autonomously whether to accept gigs based on their opportunity cost: driving time, positioning/return transit fares, and handling tasks (such as EV charging or transfer plates).

Under-pricing leads to unbooked gigs, driver drops, missed delivery deadlines (jeopardizing the required **>= 90% on-time minimum**), and severe penalties (up to 200% of price plus forfeiture). Over-pricing erodes gross margin. Crucially, as documented in `docs/HANDBOOK.md` ("Drivers learn your fees"), posting an artificially low opening fee that always ramps up steeply teaches drivers to wait, delaying bookings until right before deadlines.

This document specifies a principled, deterministic driver fee calculation engine grounded in:
1. **Finnish Collective Agreement Benchmarks** for logistics/transport drivers (~€12.00–€14.00/hour).
2. **Public Transit Positioning & Return Cost Model** (VR trains / Matkahuolto bus fare structure by road km).
3. **Extra Handling Time Allowances** for EV charging (+40 min) and transfer plates (+30 min).
4. **Structured Fee Schedule Generator** conforming to the API rules (1–48 non-decreasing steps in integer cents), balancing prompt acceptance with margin optimization.

---

## 2. Finnish Labor Benchmark & Core Economic Parameters

In Finland, transport and logistics sector collective agreements (*Kuorma-autoalan työehtosopimus* / AKT) establish base wages for drivers between **€12.00 and €14.00 per hour**. 

### Configurable Constants:
- **`BASE_WAGE_PER_HOUR_CENTS`**: `1300` (i.e. **€13.00 / hour**, default benchmark midpoint).
- **`MIN_GIG_FEE_CENTS`**: `1500` (i.e. **€15.00**, absolute floor for any gig, covering dispatch overhead and driver minimum engagement).
- **`TRANSIT_BASE_FARE_CENTS`**: `500` (i.e. **€5.00**, fixed booking/station connection allowance for regional/local transit).
- **`TRANSIT_RATE_PER_KM_CENTS`**: `10` (i.e. **€0.10 / km**, mirroring Finnish rail and intercity bus fares, e.g. VR / Matkahuolto standard advance pricing).
- **`EV_CHARGING_MINUTES`**: `40` (Handling stop per Rule 3).
- **`TRANSFER_PLATES_MINUTES`**: `30` (Handling stop for cars without valid registration plates).

---

## 3. Mathematical Cost Formulation

For a given gig (which may contain one or multiple legs), the total baseline cost to a driver $C_{\text{driver}}$ is composed of three components:
1. **Base Driving Labor Cost** ($C_{\text{drive}}$)
2. **Handling Time Labor Cost** ($C_{\text{handling}}$)
3. **Return / Positioning Travel Allowance** ($C_{\text{return}}$)

### 3.1. Routing & Distance Derivation
From `data/map.json` (or `client.map()`), look up the road graph for all consecutive stops in the gig:
- Let the stops sequence be $S_0, S_1, \dots, S_n$.
- For each transition $S_i \to S_{i+1}$:
  - $\text{km}_i = \text{roads}[S_i.\text{placeId} \to S_{i+1}.\text{placeId}].\text{km}$
  - $\text{minutes}_i = \text{roads}[S_i.\text{placeId} \to S_{i+1}.\text{placeId}].\text{minutes}$
- **Total Driving Minutes:**
  $$M_{\text{drive}} = \sum_{i=0}^{n-1} \text{minutes}_i$$
- **Total Driving Distance (km):**
  $$D_{\text{total}} = \sum_{i=0}^{n-1} \text{km}_i$$

*(Note: For a single leg $A \to B$, $M_{\text{drive}} = \text{minutes}(A \to B)$ and $D_{\text{total}} = \text{km}(A \to B)$).*

### 3.2. Base Driving Labor Cost ($C_{\text{drive}}$)
$$C_{\text{drive}} = \frac{M_{\text{drive}}}{60.0} \times W_{\text{hourly}}$$
where $W_{\text{hourly}} = \text{BASE\_WAGE\_PER\_HOUR\_CENTS}$ ($1300$).

### 3.3. Extra Handling Time Labor Cost ($C_{\text{handling}}$)
Per `docs/RULES.md`:
- `withCharging`: Adds 40 minutes to the gig.
- `withPlates`: Adds 30 minutes to the gig.

Let:
$$M_{\text{handling}} = (40 \times N_{\text{charging}}) + (30 \times N_{\text{plates}})$$
where $N_{\text{charging}}$ is the number of pickups with EV charging required, and $N_{\text{plates}}$ is the number of pickups requiring transfer plates.

$$C_{\text{handling}} = \frac{M_{\text{handling}}}{60.0} \times W_{\text{hourly}}$$

### 3.4. Return / Positioning Transit Allowance ($C_{\text{return}}$)
Drivers must position themselves to the pickup and return home/to their origin after dropping off the vehicle.
- If the gig is a **trade-in** where the final delivery is back at the initial pickup location ($S_n.\text{placeId} == S_0.\text{placeId}$), return transit is negligible/local:
  $$C_{\text{return}} = \text{TRANSIT\_BASE\_FARE\_CENTS}$$
- For one-way deliveries, the return distance is approximately the one-way transit distance $D_{\text{return}} \approx D_{\text{total}}$:
  $$C_{\text{return}} = F_{\text{base}} + (R_{\text{km}} \times D_{\text{return}})$$
  where $F_{\text{base}} = 500$ cents (€5.00) and $R_{\text{km}} = 10$ cents/km (€0.10/km).

*Sanity Check vs Real-World Finnish Transit:*
- 172 km (Helsinki $\to$ Tampere): $500 + 172 \times 10 = 2220$ cents (€22.20) — directly matches a VR InterCity train ticket!
- 600 km (Helsinki $\to$ Oulu): $500 + 600 \times 10 = 6500$ cents (€65.00) — matches standard VR long-distance fare.

### 3.5. Total Baseline Driver Cost ($C_{\text{driver}}$)
$$C_{\text{driver}} = \text{round}\left( C_{\text{drive}} + C_{\text{handling}} + C_{\text{return}} \right)$$

Enforce minimum gig floor:
$$C_{\text{driver}} = \max\left( C_{\text{driver}}, \text{MIN\_GIG\_FEE\_CENTS} \right)$$

### 3.6. Reconciliation with Request `referenceFeeCents`
The API provides `referenceFeeCents` in each `PriceRequest`. As explained in `HANDBOOK.md`, `referenceFeeCents` is a market estimate calibrated to a driver from the pickup town, but with noise.
To create a robust base fee $F_{\text{base}}$:
$$F_{\text{base}} = \max\left( C_{\text{driver}}, \text{round}(0.90 \times \text{referenceFeeCents}) \right)$$
*(If the gig carries a fraction of cars from an order, scale `referenceFeeCents` by $\frac{\text{cars}}{\text{total\_legs}}$).*

---

## 4. Fee Schedule Generation Algorithm

The Spread API enforces strict rules on fee schedules:
1. **Length:** Between 1 and 48 steps.
2. **Ordering:** Timestamps `at` must be non-decreasing.
3. **Monotonicity:** Fees `feeCents` must be strictly non-decreasing ($F_0 \le F_1 \le \dots \le F_m$).
4. **Data Types:** `at` must be integer world minutes; `feeCents` must be integer game-euro cents.
5. **Level 1 Exception:** At Level 1, the schedule must contain **exactly 1 step**.

### 4.1. Step Horizon & Key World Timestamps
Let:
- $t_{\text{now}}$: current world minute.
- $t_{\text{last\_pickup}}$: `order["lastPickupAt"]` if available, or estimated as `order["deadline"] - M_{\text{drive}} - M_{\text{handling}}`.
- $t_{\text{urgent}}$: `deadline_close` is exactly $t_{\text{last\_pickup}} - 180$ (3 hours prior to last pickup).
- $t_{\text{window\_end}}$: the earliest pickup window end.

### 4.2. Normal Schedule Generation (Not Urgent)
When the order is posted in normal operating conditions:
- **Opening Fee:**
  $$F_{\text{open}} = F_{\text{base}}$$
- **Step Interval:**
  We space steps every $60$ minutes (or $30$ minutes if time remaining $< 180$ minutes).
  Number of steps $K = \min(8, \max(1, \lfloor \frac{t_{\text{urgent}} - t_{\text{now}}}{60} \rfloor))$.
- **Fee Step Multipliers:**
  Instead of aggressive raises (which teach drivers to wait), use a steady, modest step-up:
  - Step $k = 0$: $t = t_{\text{now}}$, $\text{fee} = F_{\text{open}}$
  - Step $k \in [1, K-1]$:
    $$t_k = t_{\text{now}} + k \times \Delta t$$
    $$\text{fee}_k = \text{round}\left( F_{\text{open}} \times (1.0 + 0.06 \times k) \right)$$
  - This caps normal raises at $\approx +30\%$ to $+40\%$ before urgent escalation.

### 4.3. Urgent Schedule Generation (`deadline_close` or Repost after Drop)
When an order reaches `deadline_close` ($t \ge t_{\text{urgent}}$) or is urgent:
- Time is critical; missing the pickup results in late delivery refunds (10% to 50%) or undelivered penalties (200%).
- Escalation steps are spaced every $20$ to $30$ minutes:
  - Step $k = 0$: $t = t_{\text{now}}$, $\text{fee}_0 = \text{round}(F_{\text{base}} \times 1.35)$
  - Step $k \in [1, 5]$:
    $$t_k = t_{\text{now}} + k \times 25$$
    $$\text{fee}_k = \text{round}\left( F_{\text{base}} \times (1.35 + 0.15 \times k) \right)$$
  - Max urgent fee is bounded at $2.10 \times F_{\text{base}}$ to preserve positive gross margin while guaranteeing driver pickup.

### 4.4. Level 1 Adaptation
If `level == 1`:
- Returns a single step: `[{"at": now, "feeCents": max(1, F_base)}]`.

---

## 5. Specification for Implementation (`python/pricing.py`)

The coder should implement `python/pricing.py` exposing the following core interface:

```python
"""
Driver fee pricing calculation engine based on Finnish labor benchmarks
and road network distances.
"""
from typing import List, Optional
from spread.types import FeeStep, Order, PostAction, PriceRequest

# Constants
BASE_WAGE_PER_HOUR_CENTS: int = 1300     # €13.00 / hr
MIN_GIG_FEE_CENTS: int = 1500            # €15.00 min gig fee
TRANSIT_BASE_FARE_CENTS: int = 500       # €5.00 base public transit
TRANSIT_RATE_PER_KM_CENTS: int = 10      # €0.10 / km public transit return
EV_CHARGING_MINUTES: int = 40            # Handling time
TRANSFER_PLATES_MINUTES: int = 30        # Handling time

def calculate_driver_cost(
    driving_minutes: int,
    distance_km: float,
    with_charging: bool = False,
    with_plates: bool = False,
    is_return_trip: bool = False,
    wage_cents_per_hour: int = BASE_WAGE_PER_HOUR_CENTS,
) -> int:
    """Calculates fair driver baseline cost in integer cents."""
    ...

def build_fee_schedule(
    base_fee_cents: int,
    now: int,
    level: int,
    is_urgent: bool = False,
    last_pickup_at: Optional[int] = None,
) -> List[FeeStep]:
    """Generates non-decreasing 1-to-48 step fee schedule."""
    ...

def calculate_gig_fee_schedule(
    order: Order,
    request: PriceRequest,
    action: PostAction,
    now: int,
    level: int,
    is_urgent: bool,
    map_roads: dict,  # (from_id, to_id) -> (km, minutes)
) -> List[FeeStep]:
    """High-level entry point used by dispatch.py to replace fees_for()."""
    ...
```

---

## 6. Integration Checklist for `@coder`

1. **Road Map Loading:**
   Load `data/map.json` once into an in-memory lookup table:
   `MAP_ROADS[(from_id, to_id)] = (km, minutes)`.
2. **Stop Attribute Inspection:**
   When iterating through `action["stops"]`:
   - Identify `withCharging = True` on pickups.
   - Identify `withPlates = True` on pickups.
   - Sum road minutes and distances between consecutive stops.
3. **Connect to `dispatch.py`:**
   In `Desk.fees_for(order, cars)` or where `outbox.append({"type": "post", ...})` / `reprice` is invoked:
   - Call `calculate_gig_fee_schedule(...)`.
   - Ensure `schedule` is valid non-decreasing integer cents and meets Level 1–8 constraints.
4. **Validation:**
   Run `python3 -m py_compile python/pricing.py python/dispatch.py` to ensure no syntax errors.

---
*Authored by @designer on 2026-11-13.*

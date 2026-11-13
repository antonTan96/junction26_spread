# Spread — Autonomous Car Transport Dispatcher

Autonomous dispatch system for the **Bahn Express "Spread" Challenge** (Junction 2026).

The system acts as a car transport dispatcher across Finland for one simulated week (Monday 00:00 to Wednesday 22:00). It quotes car dealers, assigns freelance drivers across 30 Finnish towns, manages deadlines, notes, and route constraints, aiming to maximize gross margin while maintaining the **≥90% on-time delivery minimum** required for ranking.

---

## Repository Layout

```
.
├── .env.example              # Template for API credentials
├── README.md                 # Project documentation & strategy overview
├── data/
│   └── map.json              # Cached Finland road network (30 towns, 900 road pairs)
├── docs/                     # Official challenge references
│   ├── HOW.md                # Human-friendly challenge guide
│   ├── HANDBOOK.md           # Full handbook: architecture, mechanics & practice tools
│   ├── RULES.md              # Definitive rulebook (account lines, fines, levels)
│   ├── API.md                # Route reference, event payloads, rate limits
│   └── openapi.json          # Machine-readable OpenAPI 3.1 contract
├── python/                   # Python implementation & optimization workspace
│   ├── spread/               # Spread API client, websocket stream, and typed models
│   ├── dispatch.py           # Active dispatch agent
│   ├── benchmark.py          # Multi-seed benchmark runner & evaluator
│   ├── pyproject.toml        # Python project configuration
│   └── requirements.txt      # Optional analysis & solver dependencies
├── typescript/               # TypeScript implementation (runs on Node 22+ or Bun)
│   ├── spread.ts             # API client & WebSocket connector
│   ├── types.ts              # Full TypeScript type definitions
│   ├── starter.ts            # TypeScript starter desk
│   ├── reveal-csv.ts         # Export reveal data to CSV
│   ├── package.json
│   └── tsconfig.json
└── scripts/
    ├── run_practice.sh       # Run a practice world (Python or TypeScript)
    ├── run_final.sh          # Connect to live test finals and Sunday's final
    └── run_benchmark.sh      # Benchmark dispatch performance across multiple seeds
```

---

## Quick Start

### 1. Configure Credentials

Credentials are automatically read from `.env` (or environment variables `SPREAD_URL` and `SPREAD_KEY`).

```sh
cp .env.example .env
# Edit .env with your team key from https://spread.bahnexpress.com/join
```

### 2. Run Practice

#### In Python (Default):
```sh
# Run practice world at level 1 with seed "spread-1"
./scripts/run_practice.sh python 1 spread-1

# Or run directly inside python/
cd python
python3 dispatch.py --level 8 --seed spread-1
```

#### In TypeScript (Bun or Node 22+):
```sh
# Run practice world in TypeScript
./scripts/run_practice.sh ts 1 spread-1

# Or directly inside typescript/
cd typescript
node starter.ts --level 8 --seed spread-1
```

### 3. Run Multi-Seed Benchmarks

Compare strategies across deterministic seeds:
```sh
./scripts/run_benchmark.sh 8 "spread-1,spread-2,spread-3,spread-4,spread-5"
```
Or with custom flags:
```sh
cd python
python3 benchmark.py --level 8 --seeds spread-1,spread-2,spread-3 --output ../runs/experiment1.json
```

### 4. Ranking Runs & Live Final

- **Practice Ranking Rounds (`--board`)**: Plays secret seeded worlds that compare all teams on the public leaderboard.
  ```sh
  cd python && python3 dispatch.py --level 8 --board
  ```
- **Live Final / Test Final (`--final`)**: Connects to the live WebSocket stream. Set your agent running before 08:00 Helsinki time on Sunday (and for Saturday test finals at 14:00 and 20:00).
  ```sh
  ./scripts/run_final.sh python
  ```

---

## Key Challenge Mechanics

### 1. Delivery Minimum (Ranking Condition)
- **≥90% of won orders must be delivered on-time.**
- An unranked team cannot make the top 10 finalists, regardless of raw profit.
- A car not delivered when the simulation ends on Wednesday at 22:00 incurs a penalty of **2× the quoted price**.

### 2. Levels
- **Level 1–3**: Free wins (dealer accepts list price), basic posting, schedules, multi-car gigs.
- **Level 4**: Competitor enters. Dealer compares options and competitors. Late orders degrade dealer reputation.
- **Level 5**: Dealer notes (delays, payment gates, closed hours), weather, failed visit fees.
- **Level 6**: Random unannounced regional competitor outages, flu epidemic, bulk dealer orders.
- **Level 7**: Severe driver shortage (~30% of normal driver pool), dearer competitor.
- **Level 8 (Final Level)**: Non-uniform shortage per town, unannounced price war day, dealer trust mechanics (delivering on time raises accepted prices up to +25%).

### 3. Driver & Fleet Dynamics
- Drivers reside in 30 Finnish towns.
- High notification density within 30 km of driver home base.
- Drivers learn fee escalation patterns and wait for increases if gigs consistently rise.
- Late fees or emergency escalation can be handled via direct offers (`POST /v1/worlds/{id}/actions` with `type: "offer"`).

---

## Inspection & Replay Tools

- **Run Viewer**: Inspect any played week on an interactive map at `https://spread.bahnexpress.com/viewer/`
- **Team Dashboard**: View practice round scores, final status, and submission hash at `https://spread.bahnexpress.com/team`
- **Leaderboard**: Live ranking at `https://spread.bahnexpress.com/leaderboard`

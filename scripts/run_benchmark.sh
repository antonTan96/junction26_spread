#!/usr/bin/env bash
# Run benchmark across multiple seeds
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

LEVEL="${1:-8}"
SEEDS="${2:-spread-1,spread-2,spread-3}"

cd python
python3 benchmark.py --level "$LEVEL" --seeds "$SEEDS" --verbose --output "../runs/benchmark_level_${LEVEL}.json"

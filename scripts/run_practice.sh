#!/usr/bin/env bash
# Run practice world in Python or TypeScript
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

# Source .env if exists
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

LANG="${1:-python}"
LEVEL="${2:-1}"
SEED="${3:-spread-1}"

echo "=================================================="
echo "Running Spread Practice ($LANG, Level $LEVEL, Seed: $SEED)"
echo "Target URL: $SPREAD_URL"
echo "=================================================="

if [ "$LANG" = "ts" ] || [ "$LANG" = "typescript" ]; then
  cd typescript
  node starter.ts --level "$LEVEL" --seed "$SEED"
else
  cd python
  python3 dispatch.py --level "$LEVEL" --seed "$SEED"
fi


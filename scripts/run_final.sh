#!/usr/bin/env bash
# Connect to the live final / test final stream
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

LANG="${1:-python}"

echo "=================================================="
echo "Connecting to Live Final / Test Final ($LANG)"
echo "Target URL: $SPREAD_URL"
echo "=================================================="

if [ "$LANG" = "ts" ] || [ "$LANG" = "typescript" ]; then
  cd typescript
  node starter.ts --final
else
  cd python
  python3 dispatch.py --final
fi

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "$#" -gt 0 ]; then
  exec python3 render.py "$@"
fi
exec python3 render.py --config examples/type-impact.json --out out/type-impact.mp4

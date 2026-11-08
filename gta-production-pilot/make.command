#!/usr/bin/env bash
set -euo pipefail
template_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON:-python3}"
if ! "$python_bin" -c 'import PIL, numpy, jsonschema' >/dev/null 2>&1; then
  echo "Install the local Python dependencies first:" >&2
  echo "  $python_bin -m pip install -r $template_dir/requirements.txt" >&2
  exit 1
fi
exec "$python_bin" "$template_dir/render.py" --spec "$template_dir/examples/pilot.json" --out "$template_dir/out/pilot" "$@"

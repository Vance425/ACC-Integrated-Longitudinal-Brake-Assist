#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENPILOT_DIR="${SIENNA_TSS25_PLUS_OPENPILOT_DIR:-/data/openpilot}"
PID_FILE="$BASE_DIR/intersection_distance_sidecar.pid"
LOG_FILE="$BASE_DIR/intersection_distance_sidecar.log"
ROUTE_FILE="${SIENNA_TSS25_PLUS_ROUTE_FILE:-/data/sienna_route/current_route.json}"
STATE_FILE="${SIENNA_TSS25_PLUS_OSM_STATE_FILE:-/data/sienna_route/osm_context.json}"
OSM_GEOJSON="${SIENNA_TSS25_PLUS_OSM_GEOJSON:-/data/sienna_route/osm_events.geojson}"
PERIOD="${SIENNA_TSS25_PLUS_INTERSECTION_DISTANCE_PERIOD:-1.5}"
PYTHON_BIN="${SIENNA_TSS25_PLUS_PYTHON_BIN:-/usr/local/venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
  kill "$old_pid"
  sleep 1
fi

mkdir -p "$(dirname "$STATE_FILE")"
cd "$OPENPILOT_DIR"
PYTHONPATH="$OPENPILOT_DIR:${PYTHONPATH:-}" nohup "$PYTHON_BIN" tools/sienna_tss25_plus/sienna_intersection_distance_sidecar.py \
  --route-file "$ROUTE_FILE" \
  --state-file "$STATE_FILE" \
  --osm-geojson "$OSM_GEOJSON" \
  --period "$PERIOD" \
  > "$LOG_FILE" 2>&1 &
echo "$!" > "$PID_FILE"
echo "SiennaTSS25Plus intersection distance sidecar started pid=$(cat "$PID_FILE") period=$PERIOD osm_geojson=$OSM_GEOJSON"

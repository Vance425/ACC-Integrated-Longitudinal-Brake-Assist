#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENPILOT_DIR="${SIENNA_TSS25_PLUS_OPENPILOT_DIR:-/data/openpilot}"
PID_FILE="$BASE_DIR/route_receiver.pid"
LOG_FILE="$BASE_DIR/route_receiver.log"
PORT="${SIENNA_TSS25_PLUS_ROUTE_PORT:-8790}"
ROUTE_DIR="${SIENNA_TSS25_PLUS_ROUTE_DIR:-/data/sienna_route}"

old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
  kill "$old_pid"
  sleep 1
fi

mkdir -p "$ROUTE_DIR"
cd "$OPENPILOT_DIR"
nohup python3 tools/sienna_tss25_plus/sienna_route_receiver.py \
  --port "$PORT" \
  --route-dir "$ROUTE_DIR" \
  > "$LOG_FILE" 2>&1 &
echo "$!" > "$PID_FILE"
echo "SiennaTSS25Plus route receiver started on :$PORT pid=$(cat "$PID_FILE") route_dir=$ROUTE_DIR"

SIDECAR_START="$BASE_DIR/start_osm_route_sidecar.sh"
if [[ "${SIENNA_TSS25_PLUS_START_OSM_SIDECAR:-0}" == "1" && -x "$SIDECAR_START" ]]; then
  "$SIDECAR_START"
else
  echo "SiennaTSS25Plus OSM sidecar autostart disabled; set SIENNA_TSS25_PLUS_START_OSM_SIDECAR=1 to enable"
fi

INTERSECTION_SIDECAR_START="$BASE_DIR/start_intersection_distance_sidecar.sh"
if [[ "${SIENNA_TSS25_PLUS_START_INTERSECTION_DISTANCE_SIDECAR:-1}" == "1" && -x "$INTERSECTION_SIDECAR_START" ]]; then
  "$INTERSECTION_SIDECAR_START"
else
  echo "SiennaTSS25Plus intersection distance sidecar autostart disabled"
fi

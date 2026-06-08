#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote_plus, urlparse


DEFAULT_ROUTE_DIR = Path(os.environ.get("SIENNA_TSS25_PLUS_ROUTE_DIR", "sienna_route"))
DEFAULT_OSM_STATE_FILE = Path(os.environ.get("SIENNA_TSS25_PLUS_OSM_STATE_FILE", "/data/sienna_route/osm_context.json"))
DEFAULT_HOST = os.environ.get("SIENNA_TSS25_PLUS_ROUTE_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.environ.get("SIENNA_TSS25_PLUS_ROUTE_PORT", "8790"))
UI_VERSION = "2026-05-25.1"


def utc_ms() -> int:
  return int(time.time() * 1000)


def utc_now() -> str:
  return datetime.now(timezone.utc).isoformat()


def empty_route(source: str = "empty") -> dict[str, object]:
  return {
    "schema": "sienna_route_v1",
    "route_id": "",
    "route_version": 0,
    "route_updated_at": "",
    "source": source,
    "received_at": utc_now(),
    "destination_name": "",
    "destination": None,
    "route_polyline": None,
    "encoded_polyline": "",
    "turn_instructions": [],
    "source_context": {},
    "routing_mode": "",
    "raw": "",
    "status": "empty",
    "notes": [],
  }


def parse_lat_lon_pair(text: str) -> tuple[float, float] | None:
  patterns = [
    r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
    r"q=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
    r"ll=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
    r"destination=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
    r"daddr=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
    r"(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)",
  ]
  for pattern in patterns:
    match = re.search(pattern, text)
    if match:
      lat = float(match.group(1))
      lon = float(match.group(2))
      if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
        return lat, lon
  return None


def parse_geo_uri(text: str) -> tuple[float, float] | None:
  if not text.startswith("geo:"):
    return None
  body = text[4:].split("?", 1)[0]
  parts = body.split(",")
  if len(parts) >= 2:
    try:
      return float(parts[0]), float(parts[1])
    except ValueError:
      return None
  return None


def parse_destination_name(text: str) -> str:
  parsed = urlparse(text)
  qs = parse_qs(parsed.query)
  for key in ("q", "query", "destination", "daddr"):
    values = qs.get(key)
    if values:
      value = unquote_plus(values[0])
      if not re.fullmatch(r"-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?", value.strip()):
        return value.strip()
  if text.startswith("geo:"):
    qs = parse_qs(urlparse(text).query)
    values = qs.get("q")
    if values:
      return unquote_plus(values[0]).strip()
  return ""


def normalize_turn(turn: dict[str, object]) -> dict[str, object]:
  distance = turn.get("distance_along_route_m", turn.get("s", turn.get("s_m", 0.0)))
  try:
    distance_f = float(distance)
  except (TypeError, ValueError):
    distance_f = 0.0
  target = turn.get("target_speed_mps", "")
  try:
    target_f: float | str = float(target) if target != "" else ""
  except (TypeError, ValueError):
    target_f = ""
  return {
    "type": str(turn.get("type", turn.get("kind", "turn"))),
    "distance_along_route_m": distance_f,
    "street_name": str(turn.get("street_name", "")),
    "target_speed_mps": target_f,
    "confidence": float(turn.get("confidence", 1.0) or 1.0),
  }


def canonical_route_payload(route: dict[str, object]) -> str:
  relevant = {
    "destination_name": route.get("destination_name", ""),
    "destination": route.get("destination"),
    "route_polyline": route.get("route_polyline"),
    "encoded_polyline": route.get("encoded_polyline", ""),
    "turn_instructions": route.get("turn_instructions", []),
  }
  return json.dumps(relevant, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def route_id(route: dict[str, object]) -> str:
  return hashlib.sha1(canonical_route_payload(route).encode("utf-8")).hexdigest()[:16]


def route_from_payload(payload: dict[str, object], raw: str = "") -> dict[str, object]:
  route = empty_route(str(payload.get("source", "json")))
  route["raw"] = raw
  route["destination_name"] = str(payload.get("destination_name", payload.get("name", "")))
  route["route_polyline"] = payload.get("route_polyline")
  route["encoded_polyline"] = str(payload.get("encoded_polyline", payload.get("polyline", "")))
  route["turn_instructions"] = [normalize_turn(t) for t in payload.get("turn_instructions", []) if isinstance(t, dict)]
  route["source_context"] = {
    "coordinate_source": payload.get("coordinate_source", ""),
    "coordinate_export": payload.get("coordinate_export", ""),
    "route_length_m": payload.get("route_length_m", ""),
    "route_time_s": payload.get("route_time_s", ""),
    "traffic_light_count": payload.get("traffic_light_count", ""),
    "amap_context": payload.get("amap_context", {}),
  }
  route["routing_mode"] = str(payload.get("routing_mode", ""))
  route["destination"] = payload.get("destination")
  route["route_updated_at"] = str(payload.get("route_updated_at", payload.get("updated_at", "")))
  route["route_id"] = str(payload.get("route_id", "")) or route_id(route)
  route["status"] = "route_ready" if (route["route_polyline"] or route["encoded_polyline"]) else "destination_only"
  route["notes"] = [] if route["status"] == "route_ready" else ["No route polyline yet; use destination for UI only until a route source provides turn-by-turn data."]
  return route


def route_from_share_text(text: str) -> dict[str, object]:
  text = text.strip()
  route = empty_route("share_text")
  route["raw"] = text

  try:
    payload = json.loads(text)
    if isinstance(payload, dict):
      return route_from_payload(payload, raw=text)
  except json.JSONDecodeError:
    pass

  if text.startswith("geo:"):
    pair = parse_geo_uri(text)
  else:
    pair = parse_lat_lon_pair(text)

  route["destination_name"] = parse_destination_name(text)
  if pair is not None:
    lat, lon = pair
    route["destination"] = {"lat": lat, "lon": lon}
    route["status"] = "destination_only"
    route["notes"] = ["Destination received from phone/car share. Route polyline still needed for turn advisory."]
  elif text:
    route["destination_name"] = route["destination_name"] or text[:120]
    route["status"] = "destination_text_only"
    route["notes"] = ["Text destination received. A route provider must resolve it before OSM assist can predict turns."]
  return route


def load_osm_context() -> dict[str, object] | None:
  try:
    if not DEFAULT_OSM_STATE_FILE.exists():
      return None
    payload = json.loads(DEFAULT_OSM_STATE_FILE.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None
  except Exception:
    return None


def parse_float_field(payload: dict[str, object], *keys: str) -> float | None:
  for key in keys:
    value = payload.get(key)
    if value is None or value == "":
      continue
    try:
      parsed = float(value)
    except (TypeError, ValueError):
      continue
    if math.isfinite(parsed):
      return parsed
  return None


def clamp_float(value: float, minimum: float, maximum: float) -> float:
  return max(minimum, min(maximum, value))


def speed_limit_context_from_payload(payload: dict[str, object], current_route: dict[str, object]) -> dict[str, object]:
  limit_mps = parse_float_field(payload, "speed_limit_mps", "speedLimitMps", "current_mps", "currentMps")
  limit_kph = parse_float_field(payload, "speed_limit_kph", "speedLimitKph", "current_speed_limit_kph", "currentSpeedLimitKph")
  if limit_mps is None and limit_kph is not None:
    limit_mps = limit_kph / 3.6
  if limit_mps is None:
    raise ValueError("missing speed limit; use speed_limit_kph/current_speed_limit_kph or speed_limit_mps/current_mps")
  limit_mps = clamp_float(limit_mps, 1.0, 55.0)
  confidence = clamp_float(parse_float_field(payload, "confidence", "match_confidence", "matchConfidence") or 0.90, 0.0, 1.0)
  source = str(payload.get("source", payload.get("provider", "speed_limit_bridge")))
  route_id = str(current_route.get("route_id", "")) or "speed_limit_bridge"
  route_version = int(current_route.get("route_version", 0) or 0)
  return {
    "schema": "sienna_osm_context_v1",
    "status": "speed_limit_only",
    "updated_at_ms": utc_ms(),
    "route_id": route_id,
    "route_version": route_version,
    "route_status": current_route.get("status", ""),
    "route_safety": {
      "active": False,
      "reason": "speed_limit_only",
    },
    "match": {
      "confidence": round(confidence, 3),
      "mode": "speed_limit_bridge",
      "source": source,
    },
    "speed_limit": {
      "current_mps": round(limit_mps, 3),
      "current_kph": round(limit_mps * 3.6, 1),
      "source": source,
    },
    "target_speed_mps": None,
    "target_reasons": [],
    "shadow_only": True,
  }


def write_speed_limit_context(payload: dict[str, object]) -> None:
  DEFAULT_OSM_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
  body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
  tmp = DEFAULT_OSM_STATE_FILE.with_suffix(DEFAULT_OSM_STATE_FILE.suffix + ".tmp")
  tmp.write_text(body, encoding="utf-8")
  tmp.replace(DEFAULT_OSM_STATE_FILE)


def _payload_float(payload: dict[str, object], *keys: str, default: float | None = None) -> float | None:
  for key in keys:
    value = payload.get(key)
    if value is None or value == "":
      continue
    try:
      return float(value)
    except (TypeError, ValueError):
      continue
  return default


def intersection_distance_context_from_payload(payload: dict[str, object], current_route: dict[str, object]) -> dict[str, object]:
  distance_m = _payload_float(
    payload,
    "distance_m",
    "intersection_distance_m",
    "traffic_light_distance_m",
    "gps_intersection_distance_m",
    "next_distance_m",
  )
  if distance_m is None or not 0.0 <= distance_m <= 300.0:
    raise ValueError("distance_m must be within 0..300 meters")

  event_type = str(payload.get("type", payload.get("event_type", "traffic_signals")) or "traffic_signals")
  if event_type not in ("traffic_signals", "intersection", "stop", "give_way", "crossing"):
    event_type = "intersection"
  confidence = _payload_float(payload, "confidence", "match_confidence", default=0.80)
  confidence = max(0.0, min(1.0, confidence if confidence is not None else 0.80))
  source = str(payload.get("source", "intersection_distance_bridge"))[:60]

  previous = load_osm_context() or {}
  speed_limit = previous.get("speed_limit") if isinstance(previous.get("speed_limit"), dict) else None
  position = payload.get("position") if isinstance(payload.get("position"), dict) else previous.get("position")
  context = {
    "schema": "sienna_osm_context_v1",
    "status": "active",
    "updated_at_ms": utc_ms(),
    "route_id": str(payload.get("route_id", current_route.get("route_id", ""))),
    "route_version": int(payload.get("route_version", current_route.get("route_version", 0)) or 0),
    "route_status": str(current_route.get("status", "")),
    "destination_name": str(current_route.get("destination_name", "")),
    "route_safety": {
      "active": True,
      "reason": "intersection_distance_bridge",
      "source": source,
    },
    "position": position or {},
    "match": {
      "confidence": round(confidence, 3),
      "mode": "intersection_distance_bridge",
      "source": source,
    },
    "next_osm_event": {
      "distance_m": round(float(distance_m), 1),
      "type": event_type,
      "distance_from_route_m": 0.0,
      "source": source,
      "confidence": round(confidence, 3),
    },
    "target_speed_mps": None,
    "target_reasons": [event_type],
    "shadow_only": True,
  }
  if speed_limit is not None:
    context["speed_limit"] = speed_limit
  return context


class RouteStore:
  def __init__(self, route_dir: Path):
    self.route_dir = route_dir
    self.current_path = route_dir / "current_route.json"
    self.history_dir = route_dir / "history"

  def load(self) -> dict[str, object]:
    if not self.current_path.exists():
      return empty_route()
    try:
      return json.loads(self.current_path.read_text(encoding="utf-8"))
    except Exception as exc:
      route = empty_route("load_error")
      route["status"] = "error"
      route["notes"] = [str(exc)]
      return route

  def save(self, route: dict[str, object]) -> dict[str, object]:
    self.route_dir.mkdir(parents=True, exist_ok=True)
    self.history_dir.mkdir(parents=True, exist_ok=True)
    previous = self.load()
    previous_id = str(previous.get("route_id", ""))
    previous_version = int(previous.get("route_version", 0) or 0)
    if not route.get("route_id"):
      route["route_id"] = route_id(route)
    route["route_version"] = previous_version if route["route_id"] == previous_id else previous_version + 1
    if not route.get("route_updated_at"):
      route["route_updated_at"] = utc_now()
    route["received_at"] = utc_now()
    body = json.dumps(route, ensure_ascii=False, indent=2, sort_keys=True)
    self.current_path.write_text(body + "\n", encoding="utf-8")
    stamp = route["received_at"].replace(":", "").replace("-", "").split(".")[0]
    (self.history_dir / f"{stamp}.json").write_text(body + "\n", encoding="utf-8")
    return route

  def clear(self) -> dict[str, object]:
    route = empty_route("clear")
    return self.save(route)


def make_handler(store: RouteStore):
  class Handler(BaseHTTPRequestHandler):
    server_version = "SiennaRouteReceiver/1.0"

    def log_message(self, fmt: str, *args) -> None:
      print(f"{utc_now()} {self.address_string()} - {fmt % args}", flush=True)

    def send_json(self, status: int, payload: dict[str, object]) -> None:
      body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
      self.send_response(status)
      self.send_header("Content-Type", "application/json; charset=utf-8")
      self.send_header("Cache-Control", "no-store, max-age=0")
      self.send_header("Content-Length", str(len(body)))
      self.end_headers()
      self.wfile.write(body)

    def send_html(self, status: int, html: str) -> None:
      body = html.encode("utf-8")
      self.send_response(status)
      self.send_header("Content-Type", "text/html; charset=utf-8")
      self.send_header("Cache-Control", "no-store, max-age=0")
      self.send_header("Content-Length", str(len(body)))
      self.end_headers()
      self.wfile.write(body)

    def read_body(self) -> bytes:
      length = int(self.headers.get("Content-Length", "0"))
      return self.rfile.read(length) if length > 0 else b""

    def do_GET(self) -> None:
      path = urlparse(self.path).path
      if path in ("/", "/ui"):
        self.send_html(200, self.ui_html())
        return
      if path == "/health":
        self.send_json(200, {"ok": True, "service": "SiennaRouteReceiver", "ui_version": UI_VERSION})
        return
      if path in ("/route", "/status"):
        self.send_json(200, {
          "ok": True,
          "route": store.load(),
          "osm_context": load_osm_context(),
          "path": str(store.current_path),
        })
        return
      if path in ("/speed_limit", "/intersection_distance"):
        self.send_json(200, {
          "ok": True,
          "osm_context": load_osm_context(),
          "path": str(DEFAULT_OSM_STATE_FILE),
        })
        return
      self.send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
      path = urlparse(self.path).path
      body = self.read_body()
      try:
        if path == "/route":
          payload = json.loads(body.decode("utf-8"))
          if not isinstance(payload, dict):
            raise ValueError("JSON route payload must be an object")
          route = store.save(route_from_payload(payload, raw=body.decode("utf-8", "replace")))
          self.send_json(200, {"ok": True, "route": route, "path": str(store.current_path)})
          return
        if path == "/share":
          content_type = self.headers.get("Content-Type", "")
          if "application/json" in content_type:
            payload = json.loads(body.decode("utf-8"))
            text = str(payload.get("text", payload.get("url", payload))) if isinstance(payload, dict) else str(payload)
          else:
            text = body.decode("utf-8", "replace")
          route = store.save(route_from_share_text(text))
          self.send_json(200, {"ok": True, "route": route, "path": str(store.current_path)})
          return
        if path == "/clear":
          self.send_json(200, {"ok": True, "route": store.clear(), "path": str(store.current_path)})
          return
        if path == "/speed_limit":
          payload = json.loads(body.decode("utf-8"))
          if not isinstance(payload, dict):
            raise ValueError("JSON speed-limit payload must be an object")
          context = speed_limit_context_from_payload(payload, store.load())
          write_speed_limit_context(context)
          self.send_json(200, {"ok": True, "osm_context": context, "path": str(DEFAULT_OSM_STATE_FILE)})
          return
        if path == "/intersection_distance":
          payload = json.loads(body.decode("utf-8"))
          if not isinstance(payload, dict):
            raise ValueError("JSON intersection-distance payload must be an object")
          context = intersection_distance_context_from_payload(payload, store.load())
          write_speed_limit_context(context)
          self.send_json(200, {"ok": True, "osm_context": context, "path": str(DEFAULT_OSM_STATE_FILE)})
          return
        if path == "/intersection_distance/clear":
          previous = load_osm_context() or {}
          context = {
            "schema": "sienna_osm_context_v1",
            "status": "intersection_distance_cleared",
            "updated_at_ms": utc_ms(),
            "route_safety": {"active": False, "reason": "intersection_distance_cleared"},
            "speed_limit": previous.get("speed_limit") if isinstance(previous.get("speed_limit"), dict) else {},
            "target_speed_mps": None,
            "target_reasons": [],
            "shadow_only": True,
          }
          write_speed_limit_context(context)
          self.send_json(200, {"ok": True, "osm_context": context, "path": str(DEFAULT_OSM_STATE_FILE)})
          return
        if path == "/speed_limit/clear":
          context = {
            "schema": "sienna_osm_context_v1",
            "status": "speed_limit_cleared",
            "updated_at_ms": utc_ms(),
            "route_safety": {"active": False, "reason": "speed_limit_cleared"},
            "target_speed_mps": None,
            "target_reasons": [],
            "shadow_only": True,
          }
          write_speed_limit_context(context)
          self.send_json(200, {"ok": True, "osm_context": context, "path": str(DEFAULT_OSM_STATE_FILE)})
          return
      except Exception as exc:
        self.send_json(400, {"ok": False, "error": str(exc)})
        return
      self.send_json(404, {"ok": False, "error": "not_found"})

    def ui_html(self) -> str:
      route = json.dumps(store.load(), ensure_ascii=False, indent=2)
      return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sienna Route Receiver</title>
  <style>
    body {{ margin: 0; font-family: system-ui, -apple-system, Segoe UI, sans-serif; background: #f7f7f4; color: #202124; }}
    main {{ max-width: 920px; margin: 0 auto; padding: 18px; }}
    h1 {{ font-size: 24px; margin: 8px 0 16px; }}
    section {{ margin: 14px 0; padding: 14px; border: 1px solid #d8d8d0; background: #fff; border-radius: 8px; }}
    label {{ display: block; font-weight: 650; margin-bottom: 8px; }}
    textarea, input {{ box-sizing: border-box; width: 100%; font: 14px ui-monospace, SFMono-Regular, Consolas, monospace; padding: 10px; border: 1px solid #b9b9b0; border-radius: 6px; }}
    textarea {{ min-height: 120px; }}
    button {{ border: 0; border-radius: 6px; background: #1769aa; color: white; padding: 10px 14px; font-weight: 650; margin: 8px 8px 0 0; }}
    button.secondary {{ background: #5f6368; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #1f2933; color: #eef2f7; padding: 12px; border-radius: 6px; overflow: auto; }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    @media (max-width: 720px) {{ .row {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<main>
  <h1>SiennaTSS25Plus Route Receiver</h1>
  <section>
    <label for="shareText">手機/車載分享文字或網址</label>
    <textarea id="shareText" placeholder="貼上 Google Maps / Apple Maps / 高德 / geo: URL，或目的地文字"></textarea>
    <button onclick="sendShare()">送出分享資料</button>
  </section>
  <section>
    <label for="routeJson">Route JSON / 車載導航 POST 格式</label>
    <textarea id="routeJson" placeholder='{{"destination_name":"Home","encoded_polyline":"...","turn_instructions":[...]}}'></textarea>
    <button onclick="sendRoute()">送出路線</button>
    <button class="secondary" onclick="clearRoute()">清除目前路線</button>
  </section>
  <section>
    <label>目前路線狀態</label>
    <pre id="status">{route}</pre>
  </section>
</main>
<script>
async function refresh() {{
  const res = await fetch('/route');
  const data = await res.json();
  document.getElementById('status').textContent = JSON.stringify(data.route, null, 2);
}}
async function sendShare() {{
  const text = document.getElementById('shareText').value;
  const res = await fetch('/share', {{ method: 'POST', headers: {{ 'Content-Type': 'text/plain; charset=utf-8' }}, body: text }});
  document.getElementById('status').textContent = JSON.stringify(await res.json(), null, 2);
}}
async function sendRoute() {{
  const text = document.getElementById('routeJson').value;
  const res = await fetch('/route', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: text }});
  document.getElementById('status').textContent = JSON.stringify(await res.json(), null, 2);
}}
async function clearRoute() {{
  const res = await fetch('/clear', {{ method: 'POST' }});
  document.getElementById('status').textContent = JSON.stringify(await res.json(), null, 2);
}}
refresh();
</script>
</body>
</html>"""

  return Handler


def main() -> int:
  parser = argparse.ArgumentParser(description="Phone/in-car route receiver for SiennaTSS25Plus OSM assist.")
  parser.add_argument("--host", default=DEFAULT_HOST)
  parser.add_argument("--port", type=int, default=DEFAULT_PORT)
  parser.add_argument("--route-dir", type=Path, default=DEFAULT_ROUTE_DIR)
  args = parser.parse_args()

  store = RouteStore(args.route_dir)
  store.route_dir.mkdir(parents=True, exist_ok=True)
  server = ThreadingHTTPServer((args.host, args.port), make_handler(store))
  print(f"Sienna route receiver listening on http://{args.host}:{args.port} route_dir={store.route_dir}", flush=True)
  server.serve_forever()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

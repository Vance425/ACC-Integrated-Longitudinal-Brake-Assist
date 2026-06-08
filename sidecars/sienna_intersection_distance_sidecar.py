#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cereal import messaging

from tools.sienna_tss25_plus.osm_route_context import (
  GpsSample,
  PointLL,
  build_route,
  haversine_m,
  load_route,
  local_projector,
  project_to_route,
)


DEFAULT_ROUTE_FILE = Path(os.environ.get("SIENNA_TSS25_PLUS_ROUTE_FILE", "/data/sienna_route/current_route.json"))
DEFAULT_STATE_FILE = Path(os.environ.get("SIENNA_TSS25_PLUS_OSM_STATE_FILE", "/data/sienna_route/osm_context.json"))
DEFAULT_OSM_GEOJSON = Path(os.environ.get("SIENNA_TSS25_PLUS_OSM_GEOJSON", "/data/sienna_route/osm_events.geojson"))
DEFAULT_LOG_FILE = Path(os.environ.get("SIENNA_TSS25_PLUS_INTERSECTION_DISTANCE_LOG", "/data/sienna_route/intersection_distance.jsonl"))
DEFAULT_STATUS_FILE = Path(os.environ.get("SIENNA_TSS25_PLUS_INTERSECTION_DISTANCE_STATUS", "/data/params/d/SiennaIntersectionDistanceState"))
DEFAULT_PARAMS_DIR = Path(os.environ.get("SIENNA_TSS25_PLUS_PARAMS_DIR", "/data/params/d"))
OSM_GEOJSON_FALLBACKS = (
  Path("/data/sienna_route/osm.geojson"),
  Path("/data/sienna_route/osm_map.geojson"),
  Path("/data/sienna_route/osm_context.geojson"),
)
OSM_GRID_DEG = 0.002

EVENT_TYPES = {"traffic_signals", "intersection", "stop", "give_way", "crossing"}
EVENT_KEYWORDS = (
  "traffic_signal",
  "traffic_signals",
  "traffic_light",
  "traffic_lights",
  "signal",
  "intersection",
  "junction",
  "stop",
  "give_way",
  "give way",
  "yield",
  "crossing",
  "crosswalk",
  "red_light",
)


@dataclass(frozen=True)
class RouteEvent:
  s: float
  kind: str
  source: str
  confidence: float


@dataclass(frozen=True)
class MapEvent:
  ll: PointLL
  kind: str
  source: str
  confidence: float


@dataclass
class MapEventIndex:
  path: str = ""
  mtime: float = 0.0
  events: list[MapEvent] | None = None
  grid: dict[tuple[int, int], list[int]] | None = None
  error: str = ""


@dataclass(frozen=True)
class IntersectionMatch:
  kind: str
  source: str
  distance_m: float
  confidence: float
  event_confidence: float
  route_s_m: float
  cross_track_m: float
  event_distance_from_route_m: float
  mode: str


def now_ms() -> int:
  return int(time.time() * 1000)


def read_text(path: Path) -> str:
  try:
    return path.read_text(encoding="utf-8").strip()
  except Exception:
    return ""


def read_bool_param(name: str) -> bool:
  return read_text(DEFAULT_PARAMS_DIR / name) == "1"


def read_float_param(name: str, default: float, lo: float, hi: float) -> float:
  try:
    value = float(read_text(DEFAULT_PARAMS_DIR / name))
  except Exception:
    value = default
  return max(lo, min(hi, value))


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  tmp = path.with_suffix(path.suffix + ".tmp")
  tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
  tmp.replace(path)


def append_jsonl(path: Path, payload: dict[str, Any], max_bytes: int = 2_000_000) -> None:
  try:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > max_bytes:
      backup = path.with_suffix(path.suffix + ".1")
      try:
        backup.unlink()
      except FileNotFoundError:
        pass
      path.replace(backup)
    with path.open("a", encoding="utf-8") as f:
      f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
  except Exception:
    pass


def load_json(path: Path) -> dict[str, Any]:
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}
  except Exception:
    return {}


def as_float(value: Any) -> float | None:
  if value is None or value == "":
    return None
  try:
    out = float(value)
  except (TypeError, ValueError):
    return None
  if not math.isfinite(out):
    return None
  return out


def angle_delta_deg(a: float, b: float) -> float:
  return (b - a + 180.0) % 360.0 - 180.0


def normalize_kind(text: str, path_hint: str = "") -> str:
  raw = f"{text} {path_hint}".lower().replace("-", "_")
  if "give_way" in raw or "give way" in raw or "yield" in raw:
    return "give_way"
  if "cross" in raw or "crosswalk" in raw:
    return "crossing"
  if "stop" in raw:
    return "stop"
  if "traffic" in raw or "signal" in raw or "light" in raw or "red_light" in raw:
    return "traffic_signals"
  return "intersection"


def has_event_hint(text: str) -> bool:
  lower = text.lower()
  return any(keyword in lower for keyword in EVENT_KEYWORDS)


def route_event_from_dict(item: dict[str, Any], path_hint: str) -> RouteEvent | None:
  distance = None
  for key in ("distance_along_route_m", "s", "s_m", "route_s_m", "distance_m", "next_distance_m"):
    distance = as_float(item.get(key))
    if distance is not None:
      break
  if distance is None or distance < 0.0:
    return None

  kind_text = str(item.get("type", item.get("kind", item.get("event_type", item.get("name", "")))))
  if not has_event_hint(kind_text) and not has_event_hint(path_hint):
    return None
  confidence = as_float(item.get("confidence"))
  if confidence is None:
    confidence = 0.75
  return RouteEvent(
    s=distance,
    kind=normalize_kind(kind_text, path_hint),
    source=path_hint[:80] or "route_json",
    confidence=max(0.0, min(1.0, confidence)),
  )


def extract_route_events(route_meta: dict[str, Any]) -> list[RouteEvent]:
  events: list[RouteEvent] = []

  def add_event(event: RouteEvent | None) -> None:
    if event is not None and event.kind in EVENT_TYPES:
      events.append(event)

  for turn in route_meta.get("turn_instructions", []):
    if isinstance(turn, dict):
      add_event(route_event_from_dict(turn, "turn_instructions"))

  def walk(obj: Any, path: str) -> None:
    if isinstance(obj, dict):
      add_event(route_event_from_dict(obj, path))
      for key, value in obj.items():
        child_path = f"{path}.{key}" if path else str(key)
        if isinstance(value, (dict, list)):
          walk(value, child_path)
        elif has_event_hint(child_path):
          distance = as_float(value)
          if distance is not None and distance >= 0.0:
            add_event(RouteEvent(distance, normalize_kind("", child_path), child_path[:80], 0.70))
    elif isinstance(obj, list):
      for idx, value in enumerate(obj):
        child_path = f"{path}[{idx}]"
        if isinstance(value, (dict, list)):
          walk(value, child_path)
        elif has_event_hint(path):
          distance = as_float(value)
          if distance is not None and distance >= 0.0:
            add_event(RouteEvent(distance, normalize_kind("", path), path[:80], 0.70))

  walk(route_meta.get("source_context", {}), "source_context")
  walk(route_meta.get("amap_context", {}), "amap_context")
  walk(route_meta.get("events", []), "events")

  dedup: dict[tuple[int, str], RouteEvent] = {}
  for event in events:
    key = (int(round(event.s)), event.kind)
    if key not in dedup or event.confidence > dedup[key].confidence:
      dedup[key] = event
  return sorted(dedup.values(), key=lambda event: event.s)


def sample_from_gps_service(sm: messaging.SubMaster, service: str) -> GpsSample | None:
  if sm.recv_frame.get(service, 0) <= 0 or not sm.alive.get(service, False):
    return None
  gps = sm[service]
  if not getattr(gps, "hasFix", False):
    return None
  try:
    lat = float(gps.latitude)
    lon = float(gps.longitude)
    speed = float(getattr(gps, "speed", 0.0))
    heading = float(getattr(gps, "bearingDeg", 0.0))
  except (TypeError, ValueError):
    return None
  if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
    return None
  return GpsSample(row={}, t=str(now_ms()), ll=PointLL(lat, lon), speed_mps=max(0.0, speed), heading_deg=heading)


def sample_from_live_location(sm: messaging.SubMaster) -> GpsSample | None:
  if sm.recv_frame.get("liveLocationKalman", 0) <= 0 or not sm.alive.get("liveLocationKalman", False):
    return None
  loc = sm["liveLocationKalman"]
  try:
    pos = loc.positionGeodetic
    vel = loc.velocityCalibrated
    lat = float(pos.value[0])
    lon = float(pos.value[1])
    speed = math.hypot(float(vel.value[0]), float(vel.value[1]))
    heading = math.degrees(math.atan2(float(vel.value[0]), float(vel.value[1])))
  except Exception:
    return None
  if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
    return None
  return GpsSample(row={}, t=str(now_ms()), ll=PointLL(lat, lon), speed_mps=max(0.0, speed), heading_deg=heading)


def current_gps_sample(sm: messaging.SubMaster) -> GpsSample | None:
  for service in ("gpsLocationExternal", "gpsLocation"):
    sample = sample_from_gps_service(sm, service)
    if sample is not None:
      return sample
  return sample_from_live_location(sm)


def car_speed_mps(sm: messaging.SubMaster) -> float:
  try:
    return max(0.0, float(sm["carState"].vEgo))
  except Exception:
    return 0.0


def route_active(route_meta: dict[str, Any]) -> bool:
  return str(route_meta.get("status", "")) == "route_ready"


def merge_speed_limit(previous: dict[str, Any], payload: dict[str, Any]) -> None:
  speed_limit = previous.get("speed_limit")
  if isinstance(speed_limit, dict):
    payload["speed_limit"] = speed_limit


def flatten_properties(properties: Any) -> dict[str, Any]:
  if not isinstance(properties, dict):
    return {}
  out = dict(properties)
  nested_tags = properties.get("tags")
  if isinstance(nested_tags, dict):
    out.update(nested_tags)
  return out


def event_kind_from_tags(tags: dict[str, Any]) -> str | None:
  highway = str(tags.get("highway", "")).lower().replace("-", "_")
  crossing = str(tags.get("crossing", "")).lower().replace("-", "_")
  traffic_signals = str(tags.get("traffic_signals", "")).lower()
  junction = str(tags.get("junction", "")).lower()
  if highway == "traffic_signals" or traffic_signals not in ("", "none", "no") or crossing == "traffic_signals":
    return "traffic_signals"
  if highway == "stop":
    return "stop"
  if highway == "give_way":
    return "give_way"
  if highway == "crossing" or crossing in ("marked", "uncontrolled", "zebra"):
    return "crossing"
  if junction in ("yes", "intersection"):
    return "intersection"
  joined = " ".join(str(value).lower() for value in tags.values() if isinstance(value, (str, int, float)))
  if has_event_hint(joined):
    return normalize_kind(joined)
  return None


def event_confidence(kind: str, geometry_type: str) -> float:
  base = {
    "traffic_signals": 0.95,
    "stop": 0.90,
    "give_way": 0.80,
    "crossing": 0.75,
    "intersection": 0.55,
  }.get(kind, 0.50)
  if geometry_type != "Point":
    base -= 0.10
  return max(0.20, min(1.0, base))


def source_from_tags(tags: dict[str, Any], fallback: str) -> str:
  for key in ("source", "id", "osm_id", "@id", "name"):
    value = tags.get(key)
    if value not in (None, ""):
      return f"osm_geojson:{key}={str(value)[:48]}"
  return fallback


def collect_lon_lat_pairs(coords: Any, out: list[tuple[float, float]]) -> None:
  if not isinstance(coords, list) or not coords:
    return
  if len(coords) >= 2 and isinstance(coords[0], (int, float)) and isinstance(coords[1], (int, float)):
    lon = float(coords[0])
    lat = float(coords[1])
    if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
      out.append((lon, lat))
    return
  for item in coords:
    collect_lon_lat_pairs(item, out)


def geometry_event_points(geometry: dict[str, Any]) -> list[PointLL]:
  typ = str(geometry.get("type", ""))
  coords = geometry.get("coordinates")
  pairs: list[tuple[float, float]] = []
  collect_lon_lat_pairs(coords, pairs)
  if not pairs:
    return []
  if typ in ("Point", "MultiPoint"):
    return [PointLL(lat, lon) for lon, lat in pairs]
  lon = sum(pair[0] for pair in pairs) / len(pairs)
  lat = sum(pair[1] for pair in pairs) / len(pairs)
  return [PointLL(lat, lon)]


def grid_key(point: PointLL) -> tuple[int, int]:
  return (math.floor(point.lat / OSM_GRID_DEG), math.floor(point.lon / OSM_GRID_DEG))


def build_map_grid(events: list[MapEvent]) -> dict[tuple[int, int], list[int]]:
  grid: dict[tuple[int, int], list[int]] = {}
  for idx, event in enumerate(events):
    grid.setdefault(grid_key(event.ll), []).append(idx)
  return grid


def resolve_osm_geojson(path: Path) -> Path | None:
  if path.exists():
    return path
  for candidate in OSM_GEOJSON_FALLBACKS:
    if candidate.exists():
      return candidate
  return None


def load_osm_event_index(path: Path) -> MapEventIndex:
  resolved = resolve_osm_geojson(path)
  if resolved is None:
    return MapEventIndex(path=str(path), mtime=0.0, events=[], grid={}, error="osm_geojson_missing")
  try:
    mtime = resolved.stat().st_mtime
    data = json.loads(resolved.read_text(encoding="utf-8"))
    features = data.get("features", []) if isinstance(data, dict) and data.get("type") == "FeatureCollection" else [data]
    events: list[MapEvent] = []
    seen: set[tuple[int, int, str]] = set()
    for idx, feature in enumerate(features):
      if not isinstance(feature, dict):
        continue
      geometry = feature.get("geometry")
      if not isinstance(geometry, dict):
        continue
      tags = flatten_properties(feature.get("properties"))
      kind = event_kind_from_tags(tags)
      if kind not in EVENT_TYPES:
        continue
      points = geometry_event_points(geometry)
      for point in points:
        key = (int(round(point.lat * 1e6)), int(round(point.lon * 1e6)), kind)
        if key in seen:
          continue
        seen.add(key)
        events.append(MapEvent(
          ll=point,
          kind=kind,
          source=source_from_tags(tags, f"osm_geojson:feature[{idx}]"),
          confidence=event_confidence(kind, str(geometry.get("type", ""))),
        ))
    return MapEventIndex(path=str(resolved), mtime=mtime, events=events, grid=build_map_grid(events), error="")
  except Exception as exc:
    return MapEventIndex(path=str(resolved), mtime=0.0, events=[], grid={}, error=str(exc)[:160])


def maybe_reload_map_index(path: Path, current: MapEventIndex) -> MapEventIndex:
  resolved = resolve_osm_geojson(path)
  if resolved is None:
    if current.error == "osm_geojson_missing" and not current.events:
      return current
    return MapEventIndex(path=str(path), mtime=0.0, events=[], grid={}, error="osm_geojson_missing")
  try:
    mtime = resolved.stat().st_mtime
  except Exception:
    return MapEventIndex(path=str(resolved), mtime=0.0, events=[], grid={}, error="osm_geojson_stat_error")
  if current.path == str(resolved) and current.mtime == mtime:
    return current
  return load_osm_event_index(resolved)


def query_map_events(index: MapEventIndex, origin: PointLL, radius_m: float) -> list[MapEvent]:
  events = index.events or []
  grid = index.grid or {}
  if not events or not grid:
    return []
  center = grid_key(origin)
  cell_radius = max(1, int(math.ceil((radius_m / 111000.0) / OSM_GRID_DEG)) + 1)
  out: list[MapEvent] = []
  for dy in range(-cell_radius, cell_radius + 1):
    for dx in range(-cell_radius, cell_radius + 1):
      for idx in grid.get((center[0] + dy, center[1] + dx), []):
        event = events[idx]
        if haversine_m(origin, event.ll) <= radius_m:
          out.append(event)
  return out


def inactive_payload(state_file: Path, reason: str, route_meta: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
  payload: dict[str, Any] = {
    "schema": "sienna_osm_context_v1",
    "status": reason,
    "updated_at_ms": now_ms(),
    "route_id": route_meta.get("route_id", ""),
    "route_version": route_meta.get("route_version", 0),
    "route_status": route_meta.get("status", ""),
    "destination_name": route_meta.get("destination_name", ""),
    "route_safety": {"active": False, "reason": reason},
    "target_speed_mps": None,
    "target_reasons": [],
    "shadow_only": True,
  }
  if extra:
    payload.update(extra)
  merge_speed_limit(load_json(state_file), payload)
  return payload


def active_payload(state_file: Path, route_meta: dict[str, Any], sample: GpsSample, match: IntersectionMatch) -> dict[str, Any]:
  payload: dict[str, Any] = {
    "schema": "sienna_osm_context_v1",
    "status": "active",
    "updated_at_ms": now_ms(),
    "route_id": route_meta.get("route_id", ""),
    "route_version": route_meta.get("route_version", 0),
    "route_status": route_meta.get("status", ""),
    "destination_name": route_meta.get("destination_name", ""),
    "route_safety": {
      "active": True,
      "reason": "intersection_distance_sidecar",
      "source": match.source,
    },
    "position": {
      "lat": sample.ll.lat,
      "lon": sample.ll.lon,
      "speed_mps": sample.speed_mps,
      "heading_deg": sample.heading_deg,
    },
    "match": {
      "route_s_m": round(float(match.route_s_m), 1),
      "cross_track_m": round(float(match.cross_track_m), 1),
      "confidence": round(float(match.confidence), 3),
      "mode": match.mode,
    },
    "next_osm_event": {
      "distance_m": round(float(match.distance_m), 1),
      "type": match.kind,
      "distance_from_route_m": round(float(match.event_distance_from_route_m), 1),
      "source": match.source,
      "confidence": round(float(match.event_confidence), 3),
    },
    "target_speed_mps": None,
    "target_reasons": [match.kind],
    "shadow_only": True,
  }
  merge_speed_limit(load_json(state_file), payload)
  return payload


def status_payload(status: str, **values: Any) -> dict[str, Any]:
  return {"schema": "sienna_intersection_distance_state_v1", "updated_at_ms": now_ms(), "status": status, **values}


def route_metadata_match(projection_s: float, route_cross_track_m: float, route_events: list[RouteEvent], max_cross_track: float) -> IntersectionMatch | None:
  upcoming = [event for event in route_events if event.s >= projection_s - 5.0]
  event = upcoming[0] if upcoming else None
  if event is None:
    return None
  distance_m = max(0.0, event.s - projection_s)
  route_confidence = max(0.0, min(1.0, 1.0 - route_cross_track_m / max_cross_track))
  confidence = min(route_confidence, event.confidence)
  return IntersectionMatch(
    kind=event.kind,
    source=event.source,
    distance_m=distance_m,
    confidence=confidence,
    event_confidence=event.confidence,
    route_s_m=projection_s,
    cross_track_m=route_cross_track_m,
    event_distance_from_route_m=0.0,
    mode="route_intersection_distance",
  )


def route_projected_map_match(sample: GpsSample, route: list[Any], projection_s: float, route_cross_track_m: float, index: MapEventIndex, max_cross_track: float) -> IntersectionMatch | None:
  map_radius = read_float_param("SiennaIntersectionDistanceMapRadiusM", 350.0, 80.0, 800.0)
  lookahead = read_float_param("SiennaIntersectionDistanceLookaheadM", 300.0, 50.0, 800.0)
  event_cross_track = read_float_param("SiennaIntersectionDistanceEventCrossTrackM", 45.0, 10.0, 120.0)
  candidates = query_map_events(index, sample.ll, map_radius)
  best: IntersectionMatch | None = None
  route_confidence = max(0.0, min(1.0, 1.0 - route_cross_track_m / max_cross_track))
  for event in candidates:
    try:
      event_projection = project_to_route(event.ll, route)
    except Exception:
      continue
    distance_m = event_projection.s - projection_s
    if distance_m < -5.0 or distance_m > lookahead:
      continue
    if event_projection.cross_track_m > event_cross_track:
      continue
    event_track_confidence = max(0.0, min(1.0, 1.0 - event_projection.cross_track_m / event_cross_track))
    confidence = min(route_confidence, event.confidence, event_track_confidence)
    match = IntersectionMatch(
      kind=event.kind,
      source=f"{event.source}:route_projected"[:96],
      distance_m=max(0.0, distance_m),
      confidence=confidence,
      event_confidence=event.confidence,
      route_s_m=projection_s,
      cross_track_m=route_cross_track_m,
      event_distance_from_route_m=event_projection.cross_track_m,
      mode="osm_geojson_route_projected",
    )
    if best is None or match.distance_m < best.distance_m:
      best = match
  return best


def heading_map_match(sample: GpsSample, index: MapEventIndex) -> IntersectionMatch | None:
  if sample.heading_deg is None:
    return None
  lookahead = read_float_param("SiennaIntersectionDistanceLookaheadM", 300.0, 50.0, 800.0)
  map_radius = read_float_param("SiennaIntersectionDistanceMapRadiusM", 350.0, 80.0, 800.0)
  cone_deg = read_float_param("SiennaIntersectionDistanceHeadingConeDeg", 35.0, 10.0, 80.0)
  max_lateral = read_float_param("SiennaIntersectionDistanceMaxLateralM", 55.0, 8.0, 160.0)
  candidates = query_map_events(index, sample.ll, max(map_radius, lookahead + 25.0))
  if not candidates:
    return None
  project = local_projector(sample.ll)
  heading_rad = math.radians(float(sample.heading_deg) % 360.0)
  best: IntersectionMatch | None = None
  for event in candidates:
    xy = project(event.ll)
    forward_m = xy.x * math.sin(heading_rad) + xy.y * math.cos(heading_rad)
    lateral_m = xy.x * math.cos(heading_rad) - xy.y * math.sin(heading_rad)
    if forward_m < 0.0 or forward_m > lookahead:
      continue
    if abs(lateral_m) > max_lateral:
      continue
    bearing = (math.degrees(math.atan2(xy.x, xy.y)) + 360.0) % 360.0
    delta = abs(angle_delta_deg(float(sample.heading_deg), bearing))
    if delta > cone_deg:
      continue
    cone_confidence = max(0.0, 1.0 - delta / cone_deg)
    lateral_confidence = max(0.0, 1.0 - abs(lateral_m) / max_lateral)
    confidence = min(event.confidence, 0.80 * cone_confidence + 0.20 * lateral_confidence)
    match = IntersectionMatch(
      kind=event.kind,
      source=f"{event.source}:heading"[:96],
      distance_m=forward_m,
      confidence=confidence,
      event_confidence=event.confidence,
      route_s_m=0.0,
      cross_track_m=abs(lateral_m),
      event_distance_from_route_m=abs(lateral_m),
      mode="osm_geojson_heading",
    )
    if best is None or match.distance_m < best.distance_m:
      best = match
  return best


def run(args: argparse.Namespace) -> int:
  sm = messaging.SubMaster(["gpsLocation", "gpsLocationExternal", "liveLocationKalman", "carState"])
  route_mtime = 0.0
  route_meta: dict[str, Any] = {}
  route = []
  route_events: list[RouteEvent] = []
  map_index = MapEventIndex(events=[], grid={})
  last_status = ""
  last_write_t = 0.0

  while True:
    compute_start_t = time.monotonic()
    period_s = read_float_param("SiennaIntersectionDistancePeriodS", args.period, 0.5, 5.0)
    enabled = read_bool_param("SiennaIntersectionDistanceAssist")
    onroad = read_bool_param("IsOnroad")
    sm.update(0)

    try:
      mtime = args.route_file.stat().st_mtime
    except FileNotFoundError:
      mtime = 0.0
    if mtime != route_mtime:
      route_mtime = mtime
      route_meta = load_json(args.route_file)
      route = []
      route_events = []
      if route_active(route_meta):
        try:
          route = build_route(load_route(args.route_file, None))
          route_events = extract_route_events(route_meta)
        except Exception as exc:
          atomic_write_json(args.status_file, status_payload("route_load_error", error=str(exc)[:160]))

    map_index = maybe_reload_map_index(args.osm_geojson, map_index)
    map_event_count = len(map_index.events or [])

    if not enabled:
      payload = inactive_payload(args.state_file, "intersection_distance_disabled", route_meta)
      status = "disabled"
    elif not onroad:
      payload = inactive_payload(args.state_file, "intersection_distance_offroad", route_meta)
      status = "offroad"
    else:
      speed = car_speed_mps(sm)
      min_speed = read_float_param("SiennaIntersectionDistanceMinSpeedKph", 3.0, 0.0, 30.0) / 3.6
      if speed < min_speed:
        payload = inactive_payload(args.state_file, "intersection_distance_waiting_for_moving_vehicle", route_meta, {"position": {"speed_mps": round(float(speed), 2)}})
        status = "waiting_for_moving_vehicle"
      else:
        sample = current_gps_sample(sm)
        if sample is None:
          payload = inactive_payload(args.state_file, "intersection_distance_waiting_for_gps", route_meta)
          status = "waiting_for_gps"
        else:
          match: IntersectionMatch | None = None
          projection_status: dict[str, Any] = {}
          max_cross_track = read_float_param("SiennaIntersectionDistanceMaxCrossTrackM", 70.0, 20.0, 180.0)
          if route_active(route_meta) and route:
            try:
              projection = project_to_route(sample.ll, route)
              route_confidence = max(0.0, min(1.0, 1.0 - projection.cross_track_m / max_cross_track))
              projection_status = {
                "route_s_m": round(float(projection.s), 1),
                "cross_track_m": round(float(projection.cross_track_m), 1),
                "confidence": round(float(route_confidence), 3),
              }
              if projection.cross_track_m <= max_cross_track:
                match = route_metadata_match(projection.s, projection.cross_track_m, route_events, max_cross_track)
                if match is None and map_event_count > 0:
                  match = route_projected_map_match(sample, route, projection.s, projection.cross_track_m, map_index, max_cross_track)
            except Exception as exc:
              projection_status = {"error": str(exc)[:160]}

          if match is None and map_event_count > 0:
            match = heading_map_match(sample, map_index)

          if match is not None and match.confidence > 0.05:
            payload = active_payload(args.state_file, route_meta, sample, match)
            status = "active"
          else:
            if map_index.error:
              reason = f"intersection_distance_{map_index.error}"
            elif map_event_count <= 0 and not route_events:
              reason = "intersection_distance_waiting_for_events"
            else:
              reason = "intersection_distance_no_upcoming_event"
            payload = inactive_payload(args.state_file, reason, route_meta, {"match": projection_status, "osm_map": {"path": map_index.path, "event_count": map_event_count, "error": map_index.error}})
            status = reason

    compute_ms = round((time.monotonic() - compute_start_t) * 1000.0, 3)
    payload["distance_compute_ms"] = compute_ms
    payload["distance_compute_source"] = "sienna_intersection_distance_sidecar"

    now = time.monotonic()
    if status != last_status or status == "active" or now - last_write_t >= max(5.0, period_s):
      previous_context = load_json(args.state_file)
      previous_reason = ""
      if isinstance(previous_context.get("route_safety"), dict):
        previous_reason = str(previous_context["route_safety"].get("reason", ""))
      should_write_context = status == "active" or previous_reason == "intersection_distance_sidecar"
      if should_write_context:
        atomic_write_json(args.state_file, payload)
      atomic_write_json(args.status_file, status_payload(
        status,
        event=payload.get("next_osm_event"),
        route_status=route_meta.get("status", ""),
        route_event_count=len(route_events),
        map_event_count=map_event_count,
        osm_map={"path": map_index.path, "error": map_index.error},
        distance_compute_ms=compute_ms,
      ))
      append_jsonl(args.log_file, payload)
      last_status = status
      last_write_t = now

    time.sleep(period_s)


def main() -> int:
  parser = argparse.ArgumentParser(description="Low-load GPS/OSM intersection distance producer for SiennaTSS25Plus.")
  parser.add_argument("--route-file", type=Path, default=DEFAULT_ROUTE_FILE)
  parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
  parser.add_argument("--osm-geojson", type=Path, default=DEFAULT_OSM_GEOJSON)
  parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG_FILE)
  parser.add_argument("--status-file", type=Path, default=DEFAULT_STATUS_FILE)
  parser.add_argument("--period", type=float, default=1.5)
  return run(parser.parse_args())


if __name__ == "__main__":
  raise SystemExit(main())

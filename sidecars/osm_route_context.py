#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


EARTH_RADIUS_M = 6371000.0
KPH_TO_MS = 1000.0 / 3600.0
MPH_TO_MS = 1609.344 / 3600.0


@dataclass(frozen=True)
class PointLL:
  lat: float
  lon: float


@dataclass(frozen=True)
class PointXY:
  x: float
  y: float


@dataclass
class RoutePoint:
  ll: PointLL
  xy: PointXY
  s: float


@dataclass
class GpsSample:
  row: dict[str, str]
  t: str
  ll: PointLL
  speed_mps: float | None
  heading_deg: float | None


@dataclass
class Projection:
  s: float
  cross_track_m: float
  heading_deg: float
  segment_idx: int


@dataclass
class TurnInstruction:
  s: float
  kind: str
  angle_deg: float
  target_speed_mps: float
  source: str
  street_name: str = ""
  confidence: float = 1.0


@dataclass
class OsmEvent:
  s: float
  kind: str
  distance_from_route_m: float
  tags: dict[str, object]


@dataclass
class OsmSpeedSegment:
  s0: float
  s1: float
  speed_mps: float
  tags: dict[str, object]


def haversine_m(a: PointLL, b: PointLL) -> float:
  lat1 = math.radians(a.lat)
  lat2 = math.radians(b.lat)
  dlat = lat2 - lat1
  dlon = math.radians(b.lon - a.lon)
  h = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
  return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def bearing_deg(a: PointXY, b: PointXY) -> float:
  # 0 deg is north, 90 deg is east.
  return (math.degrees(math.atan2(b.x - a.x, b.y - a.y)) + 360.0) % 360.0


def angle_delta_deg(a: float, b: float) -> float:
  return (b - a + 180.0) % 360.0 - 180.0


def local_projector(origin: PointLL):
  lat0 = math.radians(origin.lat)
  lon0 = math.radians(origin.lon)
  cos_lat = max(0.05, math.cos(lat0))

  def project(p: PointLL) -> PointXY:
    return PointXY(
      x=(math.radians(p.lon) - lon0) * EARTH_RADIUS_M * cos_lat,
      y=(math.radians(p.lat) - lat0) * EARTH_RADIUS_M,
    )

  return project


def decode_polyline(text: str) -> list[PointLL]:
  coords: list[PointLL] = []
  index = 0
  lat = 0
  lon = 0
  text = text.strip()
  while index < len(text):
    values = []
    for _ in range(2):
      shift = 0
      result = 0
      while True:
        b = ord(text[index]) - 63
        index += 1
        result |= (b & 0x1f) << shift
        shift += 5
        if b < 0x20:
          break
      values.append(~(result >> 1) if result & 1 else result >> 1)
    lat += values[0]
    lon += values[1]
    coords.append(PointLL(lat / 1e5, lon / 1e5))
  return coords


def load_geojson_points(path: Path) -> list[list[PointLL]]:
  data = json.loads(path.read_text(encoding="utf-8"))
  if data.get("schema") == "sienna_route_v1":
    points = route_json_points(data)
    return [points] if points else []
  lines: list[list[PointLL]] = []

  def add_geometry(geometry: dict[str, object]) -> None:
    typ = geometry.get("type")
    coords = geometry.get("coordinates")
    if typ == "LineString" and isinstance(coords, list):
      lines.append([PointLL(float(lat), float(lon)) for lon, lat, *_ in coords])
    elif typ == "MultiLineString" and isinstance(coords, list):
      for line in coords:
        lines.append([PointLL(float(lat), float(lon)) for lon, lat, *_ in line])

  if data.get("type") == "FeatureCollection":
    for feature in data.get("features", []):
      geometry = feature.get("geometry") if isinstance(feature, dict) else None
      if isinstance(geometry, dict):
        add_geometry(geometry)
  elif data.get("type") == "Feature":
    geometry = data.get("geometry")
    if isinstance(geometry, dict):
      add_geometry(geometry)
  elif "type" in data:
    add_geometry(data)

  return [line for line in lines if len(line) >= 2]


def route_json_points(data: dict[str, object]) -> list[PointLL]:
  route_polyline = data.get("route_polyline")
  if isinstance(route_polyline, list):
    points: list[PointLL] = []
    for item in route_polyline:
      if isinstance(item, dict):
        lat = item.get("lat", item.get("latitude"))
        lon = item.get("lon", item.get("lng", item.get("longitude")))
        if lat is not None and lon is not None:
          points.append(PointLL(float(lat), float(lon)))
      elif isinstance(item, (list, tuple)) and len(item) >= 2:
        # Prefer [lat, lon] for our route JSON, but accept GeoJSON-like [lon, lat]
        first = float(item[0])
        second = float(item[1])
        if abs(first) <= 90.0 and abs(second) <= 180.0:
          points.append(PointLL(first, second))
        else:
          points.append(PointLL(second, first))
    if len(points) >= 2:
      return points

  encoded = data.get("encoded_polyline")
  if isinstance(encoded, str) and encoded.strip():
    return decode_polyline(encoded)
  return []


def load_gpx_points(path: Path) -> list[PointLL]:
  root = ET.parse(path).getroot()
  points: list[PointLL] = []
  for elem in root.iter():
    name = elem.tag.rsplit("}", 1)[-1]
    if name in ("trkpt", "rtept"):
      lat = elem.attrib.get("lat")
      lon = elem.attrib.get("lon")
      if lat is not None and lon is not None:
        points.append(PointLL(float(lat), float(lon)))
  return points


def load_csv_points(path: Path) -> list[PointLL]:
  with path.open(newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    rows = list(reader)
  if not rows:
    return []
  lat_col = find_column(rows[0], ("lat", "latitude", "gps_lat", "gpsLatitude"))
  lon_col = find_column(rows[0], ("lon", "lng", "longitude", "gps_lon", "gpsLongitude"))
  if lat_col is None or lon_col is None:
    raise ValueError(f"Cannot find lat/lon columns in {path}")
  return [PointLL(float(row[lat_col]), float(row[lon_col])) for row in rows if row.get(lat_col) and row.get(lon_col)]


def load_route(path: Path, encoded_polyline: str | None) -> list[PointLL]:
  if encoded_polyline:
    return decode_polyline(encoded_polyline)
  suffix = path.suffix.lower()
  if suffix in (".geojson", ".json"):
    lines = load_geojson_points(path)
    if not lines:
      raise ValueError(f"No LineString route found in {path}")
    return max(lines, key=len)
  if suffix == ".gpx":
    points = load_gpx_points(path)
    if len(points) < 2:
      raise ValueError(f"No GPX route/track points found in {path}")
    return points
  if suffix == ".csv":
    points = load_csv_points(path)
    if len(points) < 2:
      raise ValueError(f"No CSV route points found in {path}")
    return points
  text = path.read_text(encoding="utf-8").strip()
  return decode_polyline(text)


def build_route(points: list[PointLL]) -> list[RoutePoint]:
  if len(points) < 2:
    raise ValueError("Route needs at least two points")
  project = local_projector(points[0])
  route: list[RoutePoint] = []
  total = 0.0
  prev_xy: PointXY | None = None
  for point in points:
    xy = project(point)
    if prev_xy is not None:
      total += math.hypot(xy.x - prev_xy.x, xy.y - prev_xy.y)
    route.append(RoutePoint(point, xy, total))
    prev_xy = xy
  return route


def find_column(row: dict[str, str], candidates: Iterable[str]) -> str | None:
  lowered = {key.lower(): key for key in row.keys()}
  for candidate in candidates:
    key = lowered.get(candidate.lower())
    if key is not None:
      return key
  return None


def parse_float(value: str | None) -> float | None:
  if value is None or value == "":
    return None
  try:
    return float(value)
  except ValueError:
    return None


def load_gps_csv(path: Path) -> list[GpsSample]:
  with path.open(newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    rows = list(reader)
  if not rows:
    return []
  first = rows[0]
  lat_col = find_column(first, ("lat", "latitude", "gps_lat", "gpsLatitude"))
  lon_col = find_column(first, ("lon", "lng", "longitude", "gps_lon", "gpsLongitude"))
  if lat_col is None or lon_col is None:
    raise ValueError(f"Cannot find lat/lon columns in {path}")
  time_col = find_column(first, ("t", "time", "timestamp", "log_time", "sec", "seconds"))
  speed_col = find_column(first, ("speed_mps", "v_ego", "vEgo", "speed", "speed_ms"))
  speed_kph_col = find_column(first, ("speed_kph", "speedKph", "v_kph"))
  heading_col = find_column(first, ("heading", "bearing", "heading_deg", "bearing_deg"))
  samples: list[GpsSample] = []
  for idx, row in enumerate(rows):
    lat = parse_float(row.get(lat_col))
    lon = parse_float(row.get(lon_col))
    if lat is None or lon is None:
      continue
    speed_mps = parse_float(row.get(speed_col)) if speed_col else None
    if speed_mps is None and speed_kph_col:
      speed_kph = parse_float(row.get(speed_kph_col))
      speed_mps = speed_kph * KPH_TO_MS if speed_kph is not None else None
    samples.append(GpsSample(
      row=row,
      t=row.get(time_col, str(idx)) if time_col else str(idx),
      ll=PointLL(lat, lon),
      speed_mps=speed_mps,
      heading_deg=parse_float(row.get(heading_col)) if heading_col else None,
    ))
  return samples


def project_to_route(point: PointLL, route: list[RoutePoint]) -> Projection:
  project = local_projector(route[0].ll)
  p = project(point)
  best: Projection | None = None
  for idx in range(len(route) - 1):
    a = route[idx]
    b = route[idx + 1]
    vx = b.xy.x - a.xy.x
    vy = b.xy.y - a.xy.y
    seg_len2 = vx * vx + vy * vy
    if seg_len2 <= 1e-6:
      continue
    u = max(0.0, min(1.0, ((p.x - a.xy.x) * vx + (p.y - a.xy.y) * vy) / seg_len2))
    px = a.xy.x + u * vx
    py = a.xy.y + u * vy
    dist = math.hypot(p.x - px, p.y - py)
    s = a.s + math.sqrt(seg_len2) * u
    projection = Projection(s=s, cross_track_m=dist, heading_deg=bearing_deg(a.xy, b.xy), segment_idx=idx)
    if best is None or projection.cross_track_m < best.cross_track_m:
      best = projection
  if best is None:
    raise ValueError("Route contains no usable segments")
  return best


def route_point_at(route: list[RoutePoint], s: float) -> RoutePoint:
  if s <= 0.0:
    return route[0]
  if s >= route[-1].s:
    return route[-1]
  for idx in range(len(route) - 1):
    a = route[idx]
    b = route[idx + 1]
    if a.s <= s <= b.s:
      span = max(1e-6, b.s - a.s)
      u = (s - a.s) / span
      return RoutePoint(
        ll=PointLL(a.ll.lat + (b.ll.lat - a.ll.lat) * u, a.ll.lon + (b.ll.lon - a.ll.lon) * u),
        xy=PointXY(a.xy.x + (b.xy.x - a.xy.x) * u, a.xy.y + (b.xy.y - a.xy.y) * u),
        s=s,
      )
  return route[-1]


def circumradius_m(a: PointXY, b: PointXY, c: PointXY) -> float | None:
  ab = math.hypot(a.x - b.x, a.y - b.y)
  bc = math.hypot(b.x - c.x, b.y - c.y)
  ca = math.hypot(c.x - a.x, c.y - a.y)
  area2 = abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x))
  if area2 < 1e-3 or min(ab, bc, ca) < 3.0:
    return None
  return (ab * bc * ca) / (2.0 * area2)


def classify_turn(angle: float) -> str:
  side = "left" if angle > 0.0 else "right"
  mag = abs(angle)
  if mag >= 135.0:
    return f"sharp_{side}"
  if mag >= 55.0:
    return side
  return f"slight_{side}"


def infer_turns(route: list[RoutePoint], min_angle_deg: float, lateral_accel: float) -> list[TurnInstruction]:
  turns: list[TurnInstruction] = []
  for idx in range(1, len(route) - 1):
    prev = route[idx - 1]
    cur = route[idx]
    nxt = route[idx + 1]
    incoming = bearing_deg(prev.xy, cur.xy)
    outgoing = bearing_deg(cur.xy, nxt.xy)
    angle = angle_delta_deg(incoming, outgoing)
    if abs(angle) < min_angle_deg:
      continue
    radius = circumradius_m(prev.xy, cur.xy, nxt.xy)
    if radius is None:
      target = 7.0 if abs(angle) > 55.0 else 10.0
    else:
      target = math.sqrt(max(4.0, lateral_accel * radius))
    turns.append(TurnInstruction(
      s=cur.s,
      kind=classify_turn(angle),
      angle_deg=angle,
      target_speed_mps=min(target, 16.0),
      source="route_geometry",
    ))
  return turns


def load_turns_csv(path: Path) -> list[TurnInstruction]:
  with path.open(newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    rows = list(reader)
  turns: list[TurnInstruction] = []
  for row in rows:
    s = parse_float(row.get("distance_along_route_m") or row.get("s") or row.get("s_m"))
    if s is None:
      continue
    speed = parse_float(row.get("target_speed_mps"))
    speed_kph = parse_float(row.get("target_speed_kph"))
    if speed is None and speed_kph is not None:
      speed = speed_kph * KPH_TO_MS
    turns.append(TurnInstruction(
      s=s,
      kind=row.get("type") or row.get("kind") or "turn",
      angle_deg=parse_float(row.get("angle_deg")) or 0.0,
      target_speed_mps=speed if speed is not None else 8.0,
      source="turns_csv",
      street_name=row.get("street_name", ""),
      confidence=parse_float(row.get("confidence")) or 1.0,
    ))
  return sorted(turns, key=lambda turn: turn.s)


def load_turns_route_json(path: Path) -> list[TurnInstruction]:
  data = json.loads(path.read_text(encoding="utf-8"))
  if data.get("schema") != "sienna_route_v1":
    return []
  turns = []
  for turn in data.get("turn_instructions", []):
    if not isinstance(turn, dict):
      continue
    turns.append(TurnInstruction(
      s=float(turn.get("distance_along_route_m", 0.0) or 0.0),
      kind=str(turn.get("type", "turn")),
      angle_deg=float(turn.get("angle_deg", 0.0) or 0.0),
      target_speed_mps=float(turn.get("target_speed_mps", 8.0) or 8.0),
      source="route_json",
      street_name=str(turn.get("street_name", "")),
      confidence=float(turn.get("confidence", 1.0) or 1.0),
    ))
  return sorted(turns, key=lambda turn: turn.s)


def parse_speed_mps(value: object) -> float | None:
  if value is None:
    return None
  text = str(value).strip().lower()
  if not text or text in ("none", "signals", "walk", "variable"):
    return None
  first = text.split(";", 1)[0].strip()
  parts = first.replace(",", ".").split()
  try:
    number = float(parts[0])
  except (ValueError, IndexError):
    return None
  if "mph" in first:
    return number * MPH_TO_MS
  return number * KPH_TO_MS


def geometry_points(geometry: dict[str, object]) -> list[PointLL]:
  typ = geometry.get("type")
  coords = geometry.get("coordinates")
  if typ == "Point" and isinstance(coords, list):
    lon, lat, *_ = coords
    return [PointLL(float(lat), float(lon))]
  if typ == "LineString" and isinstance(coords, list):
    return [PointLL(float(lat), float(lon)) for lon, lat, *_ in coords]
  return []


def load_osm_geojson(path: Path, route: list[RoutePoint], route_tolerance_m: float) -> tuple[list[OsmEvent], list[OsmSpeedSegment]]:
  data = json.loads(path.read_text(encoding="utf-8"))
  features = data.get("features", []) if data.get("type") == "FeatureCollection" else [data]
  events: list[OsmEvent] = []
  speed_segments: list[OsmSpeedSegment] = []
  event_tags = {"traffic_signals", "stop", "give_way", "crossing"}

  for feature in features:
    if not isinstance(feature, dict):
      continue
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
      continue
    tags = feature.get("properties") or {}
    if not isinstance(tags, dict):
      tags = {}
    points = geometry_points(geometry)
    if not points:
      continue
    highway = str(tags.get("highway", ""))
    traffic_signals = "traffic_signals" in tags
    is_event = highway in event_tags or traffic_signals
    speed = parse_speed_mps(tags.get("maxspeed") or tags.get("maxspeed:forward") or tags.get("maxspeed:advisory"))

    if is_event:
      proj = min((project_to_route(point, route) for point in points), key=lambda p: p.cross_track_m)
      if proj.cross_track_m <= route_tolerance_m:
        events.append(OsmEvent(s=proj.s, kind=highway or "traffic_signals", distance_from_route_m=proj.cross_track_m, tags=tags))

    if speed is not None and len(points) >= 2:
      projections = [project_to_route(point, route) for point in points]
      close = [proj for proj in projections if proj.cross_track_m <= route_tolerance_m]
      if len(close) >= 2:
        s0 = min(proj.s for proj in close)
        s1 = max(proj.s for proj in close)
        if s1 > s0:
          speed_segments.append(OsmSpeedSegment(s0=s0, s1=s1, speed_mps=speed, tags=tags))

  return sorted(events, key=lambda e: e.s), sorted(speed_segments, key=lambda seg: seg.s0)


def current_speed_limit(s: float, segments: list[OsmSpeedSegment]) -> float | None:
  for seg in segments:
    if seg.s0 - 5.0 <= s <= seg.s1 + 5.0:
      return seg.speed_mps
  return None


def next_speed_limit_change(s: float, current: float | None, segments: list[OsmSpeedSegment]) -> tuple[float | None, float | None]:
  best: tuple[float | None, float | None] = (None, None)
  for seg in segments:
    if seg.s0 <= s:
      continue
    if current is None or abs(seg.speed_mps - current) > 0.2:
      if best[0] is None or seg.s0 < best[0]:
        best = (seg.s0, seg.speed_mps)
  if best[0] is None:
    return None, None
  return best[0] - s, best[1]


def next_item(s: float, items):
  ahead = [item for item in items if item.s >= s]
  return min(ahead, key=lambda item: (item.s, getattr(item, "target_speed_mps", 99.0))) if ahead else None


def approach_speed(current_s: float, target_s: float, target_speed: float, decel: float) -> float:
  distance = max(0.0, target_s - current_s)
  return math.sqrt(max(0.0, target_speed * target_speed + 2.0 * decel * distance))


def context_rows(
  samples: list[GpsSample],
  route: list[RoutePoint],
  turns: list[TurnInstruction],
  events: list[OsmEvent],
  speed_segments: list[OsmSpeedSegment],
  max_cross_track_m: float,
  decel_mps2: float,
) -> list[dict[str, object]]:
  rows: list[dict[str, object]] = []
  for sample in samples:
    proj = project_to_route(sample.ll, route)
    heading_error = ""
    confidence = max(0.0, min(1.0, 1.0 - proj.cross_track_m / max_cross_track_m))
    if sample.heading_deg is not None:
      heading_error_float = abs(angle_delta_deg(sample.heading_deg, proj.heading_deg))
      heading_error = f"{heading_error_float:.1f}"
      confidence *= max(0.0, 1.0 - heading_error_float / 90.0)

    turn = next_item(proj.s, turns)
    event = next_item(proj.s, events)
    speed_limit = current_speed_limit(proj.s, speed_segments)
    next_limit_dist, next_limit = next_speed_limit_change(proj.s, speed_limit, speed_segments)

    target_candidates: list[float] = []
    if speed_limit is not None:
      target_candidates.append(speed_limit)
    if next_limit_dist is not None and next_limit is not None and next_limit < (speed_limit or 100.0):
      target_candidates.append(approach_speed(proj.s, proj.s + next_limit_dist, next_limit, decel_mps2))
    if turn is not None:
      target_candidates.append(approach_speed(proj.s, turn.s, turn.target_speed_mps, decel_mps2))
    if event is not None and event.kind in ("traffic_signals", "stop", "give_way"):
      event_target = 5.0 if event.kind == "traffic_signals" else 3.0
      target_candidates.append(approach_speed(proj.s, event.s, event_target, decel_mps2))

    osm_target = min(target_candidates) if target_candidates else None
    route_point = route_point_at(route, proj.s)
    rows.append({
      "t": sample.t,
      "lat": f"{sample.ll.lat:.7f}",
      "lon": f"{sample.ll.lon:.7f}",
      "route_s_m": f"{proj.s:.1f}",
      "route_remaining_m": f"{max(0.0, route[-1].s - proj.s):.1f}",
      "matched_lat": f"{route_point.ll.lat:.7f}",
      "matched_lon": f"{route_point.ll.lon:.7f}",
      "cross_track_m": f"{proj.cross_track_m:.1f}",
      "route_heading_deg": f"{proj.heading_deg:.1f}",
      "heading_error_deg": heading_error,
      "confidence": f"{confidence:.3f}",
      "speed_mps": "" if sample.speed_mps is None else f"{sample.speed_mps:.2f}",
      "osm_speed_limit_mps": "" if speed_limit is None else f"{speed_limit:.2f}",
      "next_speed_limit_distance_m": "" if next_limit_dist is None else f"{next_limit_dist:.1f}",
      "next_speed_limit_mps": "" if next_limit is None else f"{next_limit:.2f}",
      "next_route_turn_distance_m": "" if turn is None else f"{turn.s - proj.s:.1f}",
      "next_route_turn_type": "" if turn is None else turn.kind,
      "next_route_turn_target_speed_mps": "" if turn is None else f"{turn.target_speed_mps:.2f}",
      "next_osm_event_distance_m": "" if event is None else f"{event.s - proj.s:.1f}",
      "next_osm_event_type": "" if event is None else event.kind,
      "osm_target_speed_mps": "" if osm_target is None else f"{osm_target:.2f}",
    })
  return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  fieldnames = list(rows[0].keys()) if rows else ["t"]
  with path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)


def main() -> int:
  parser = argparse.ArgumentParser(description="Offline route/OSM context prototype for SiennaTSS25Plus.")
  parser.add_argument("--gps-csv", type=Path, required=True, help="CSV with lat/lon and optional speed/heading columns.")
  parser.add_argument("--route", type=Path, required=True, help="Route GPX, GeoJSON, CSV, or file containing encoded polyline.")
  parser.add_argument("--encoded-polyline", help="Encoded route polyline string. Overrides --route contents.")
  parser.add_argument("--turns-csv", type=Path, help="Optional turn list with distance_along_route_m,type,target_speed_mps.")
  parser.add_argument("--osm-geojson", type=Path, help="Optional OSM-derived GeoJSON features for speed/event context.")
  parser.add_argument("-o", "--output", type=Path, default=Path("osm_route_context.csv"))
  parser.add_argument("--route-tolerance-m", type=float, default=35.0)
  parser.add_argument("--max-cross-track-m", type=float, default=35.0)
  parser.add_argument("--min-turn-angle-deg", type=float, default=28.0)
  parser.add_argument("--curve-lateral-accel", type=float, default=1.4)
  parser.add_argument("--approach-decel", type=float, default=0.9)
  args = parser.parse_args()

  route_points = load_route(args.route, args.encoded_polyline)
  route = build_route(route_points)
  samples = load_gps_csv(args.gps_csv)
  if not samples:
    raise ValueError(f"No GPS samples found in {args.gps_csv}")

  turns = infer_turns(route, args.min_turn_angle_deg, args.curve_lateral_accel)
  if args.route.suffix.lower() == ".json":
    turns.extend(load_turns_route_json(args.route))
  if args.turns_csv:
    turns.extend(load_turns_csv(args.turns_csv))
    turns.sort(key=lambda turn: turn.s)

  events: list[OsmEvent] = []
  speed_segments: list[OsmSpeedSegment] = []
  if args.osm_geojson:
    events, speed_segments = load_osm_geojson(args.osm_geojson, route, args.route_tolerance_m)

  rows = context_rows(
    samples=samples,
    route=route,
    turns=turns,
    events=events,
    speed_segments=speed_segments,
    max_cross_track_m=args.max_cross_track_m,
    decel_mps2=args.approach_decel,
  )
  write_csv(args.output, rows)
  print(args.output)
  print(f"route_length_m={route[-1].s:.1f} samples={len(samples)} turns={len(turns)} osm_events={len(events)} speed_segments={len(speed_segments)}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

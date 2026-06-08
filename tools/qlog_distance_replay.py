#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import re
import sys
import time
import types
from bisect import bisect_left
from pathlib import Path
from typing import Any


def segment_num(path: Path) -> int:
  match = re.search(r"--(\d+)--qlog", path.name)
  return int(match.group(1)) if match else 999999


def add_import_roots(openpilot_root: Path | None, schema_root: Path | None) -> None:
  for root in (openpilot_root, schema_root):
    if root and root.exists():
      sys.path.insert(0, str(root))


def load_log_reader():
  errors: list[str] = []
  for module_name in (
    "openpilot.tools.lib.logreader",
    "tools.lib.logreader",
    "opendbc_car.logreader",
  ):
    try:
      module = __import__(module_name, fromlist=["LogReader"])
      return module.LogReader
    except Exception as exc:
      errors.append(f"{module_name}: {type(exc).__name__}: {exc}")
  schema_root = next((Path(path) for path in sys.path if (Path(path) / "cereal" / "log.capnp").exists()), None)
  if schema_root is not None:
    try:
      import capnp
      import zstandard as zstd

      capnp_log = capnp.load(str(schema_root / "cereal" / "log.capnp"), imports=[str(schema_root / "cereal")])

      class SchemaLogReader:
        def __init__(self, fn: str, sort_by_time: bool = False, **_kwargs: Any):
          data = Path(fn).read_bytes()
          if fn.endswith(".zst") or data.startswith(b"\x28\xB5\x2F\xFD"):
            with zstd.ZstdDecompressor().stream_reader(data) as reader:
              data = reader.read()
          ents = []
          try:
            for ent in capnp_log.Event.read_multiple_bytes(data):
              ents.append(ent)
          except Exception:
            pass
          self._data = data
          if sort_by_time:
            ents.sort(key=lambda msg: msg.logMonoTime)
          self._ents = ents

        def __iter__(self):
          return iter(self._ents)

      return SchemaLogReader
    except Exception as exc:
      errors.append(f"schema_logreader: {type(exc).__name__}: {exc}")
  raise RuntimeError("Cannot import LogReader. Tried: " + " | ".join(errors))


def load_local_modules(sidecar_dir: Path):
  cereal_mod = types.ModuleType("cereal")
  messaging_mod = types.ModuleType("cereal.messaging")

  class SubMaster:  # pylint: disable=too-few-public-methods
    pass

  messaging_mod.SubMaster = SubMaster
  cereal_mod.messaging = messaging_mod
  sys.modules["cereal"] = cereal_mod
  sys.modules["cereal.messaging"] = messaging_mod

  if "tools" not in sys.modules:
    sys.modules["tools"] = types.ModuleType("tools")
  if "tools.sienna_tss25_plus" not in sys.modules:
    sys.modules["tools.sienna_tss25_plus"] = types.ModuleType("tools.sienna_tss25_plus")

  context_name = "tools.sienna_tss25_plus.osm_route_context"
  context_spec = importlib.util.spec_from_file_location(context_name, sidecar_dir / "osm_route_context.py")
  if context_spec is None or context_spec.loader is None:
    raise RuntimeError("Cannot load osm_route_context.py")
  context = importlib.util.module_from_spec(context_spec)
  sys.modules[context_name] = context
  context_spec.loader.exec_module(context)

  sidecar_spec = importlib.util.spec_from_file_location("sienna_intersection_distance_sidecar_replay", sidecar_dir / "sienna_intersection_distance_sidecar.py")
  if sidecar_spec is None or sidecar_spec.loader is None:
    raise RuntimeError("Cannot load sienna_intersection_distance_sidecar.py")
  sidecar = importlib.util.module_from_spec(sidecar_spec)
  sys.modules[sidecar_spec.name] = sidecar
  sidecar_spec.loader.exec_module(sidecar)
  return context, sidecar


def which(msg: Any) -> str:
  try:
    return str(msg.which())
  except Exception:
    return "INVALID"


def msg_rel_s(msg: Any, base_mono: int | None) -> float:
  mono = int(getattr(msg, "logMonoTime", 0))
  if base_mono is None:
    return 0.0
  return (mono - base_mono) / 1.0e9


def nearest(rows: list[dict[str, Any]], rel_s: float, max_dt_s: float = 0.75) -> dict[str, Any] | None:
  if not rows:
    return None
  times = [row["rel_s"] for row in rows]
  idx = bisect_left(times, rel_s)
  best = None
  best_dt = None
  for cand in (idx - 1, idx):
    if 0 <= cand < len(rows):
      dt = abs(rows[cand]["rel_s"] - rel_s)
      if best_dt is None or dt < best_dt:
        best = rows[cand]
        best_dt = dt
  if best is None or best_dt is None or best_dt > max_dt_s:
    return None
  return best


def sample_from_gps_msg(msg: Any, rel_s: float, ctx: Any) -> dict[str, Any] | None:
  gps = getattr(msg, which(msg))
  if not getattr(gps, "hasFix", False):
    return None
  try:
    lat = float(gps.latitude)
    lon = float(gps.longitude)
    speed = max(0.0, float(getattr(gps, "speed", 0.0)))
    heading = float(getattr(gps, "bearingDeg", 0.0))
  except Exception:
    return None
  if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
    return None
  return {
    "rel_s": rel_s,
    "sample": ctx.GpsSample(row={}, t=f"{rel_s:.3f}", ll=ctx.PointLL(lat, lon), speed_mps=speed, heading_deg=heading),
    "gps_source": which(msg),
  }


def sample_from_live_location_msg(msg: Any, rel_s: float, ctx: Any) -> dict[str, Any] | None:
  loc = msg.liveLocationKalman
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
  return {
    "rel_s": rel_s,
    "sample": ctx.GpsSample(row={}, t=f"{rel_s:.3f}", ll=ctx.PointLL(lat, lon), speed_mps=max(0.0, speed), heading_deg=heading),
    "gps_source": "liveLocationKalman",
  }


def parse_marker_text(text: str) -> tuple[str, dict[str, Any] | None]:
  for marker in (
    "SIENNA_TRAFFIC_LIGHT_DEBUG",
    "SIENNA_TRAFFIC_DEBUG",
    "SIENNA_TSS3_DEBUG",
    "SIENNA_OSM_DEBUG",
    "SIENNA_TURN_DEBUG",
    "SIENNA_TAIWAN_STOP_DEBUG",
  ):
    idx = text.find(marker)
    if idx < 0:
      continue
    tail = text[idx + len(marker):].strip()
    if tail.startswith("{"):
      try:
        return marker, json.loads(tail)
      except Exception:
        return marker, None
    return marker, None
  return "", None


def distance_phase(distance_m: float | None, v_kph: float | None) -> tuple[str, float | None, float]:
  if distance_m is None:
    return "no_distance", None, 0.0
  if distance_m > 160.0:
    return "watch", 50.0, 0.0
  if distance_m > 120.0:
    return "far_coast", 50.0, 0.15
  if distance_m > 80.0:
    return "prepare_slow", 40.0, 0.45
  if distance_m > 40.0:
    return "mid_light_brake", 30.0, 0.90
  if distance_m > 20.0:
    return "near_firm_brake", 22.0, 1.30
  return "stop_zone", 0.0, 1.50


def read_qlog_inputs(qlog_dir: Path, LogReader: Any, ctx: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
  gps_rows: list[dict[str, Any]] = []
  car_rows: list[dict[str, Any]] = []
  plan_rows: list[dict[str, Any]] = []
  marker_rows: list[dict[str, Any]] = []
  base_mono: int | None = None
  for path in sorted(qlog_dir.glob("*qlog.zst"), key=segment_num):
    for msg in LogReader(str(path), sort_by_time=False):
      if base_mono is None:
        base_mono = int(getattr(msg, "logMonoTime", 0))
      rel_s = msg_rel_s(msg, base_mono)
      typ = which(msg)
      if typ in ("gpsLocationExternal", "gpsLocation"):
        row = sample_from_gps_msg(msg, rel_s, ctx)
        if row is not None:
          row["segment"] = segment_num(path)
          gps_rows.append(row)
      elif typ == "liveLocationKalman":
        row = sample_from_live_location_msg(msg, rel_s, ctx)
        if row is not None:
          row["segment"] = segment_num(path)
          gps_rows.append(row)
      elif typ == "carState":
        cs = msg.carState
        try:
          car_rows.append({
            "rel_s": rel_s,
            "v_kph": float(cs.vEgo) * 3.6,
            "a_ego": float(getattr(cs, "aEgo", 0.0)),
            "brake_pressed": bool(getattr(cs, "brakePressed", False)),
            "gas_pressed": bool(getattr(cs, "gasPressed", False)),
            "standstill": bool(getattr(cs, "standstill", False)),
          })
        except Exception:
          pass
      elif typ == "longitudinalPlan":
        lp = msg.longitudinalPlan
        try:
          plan_rows.append({
            "rel_s": rel_s,
            "a_target": float(getattr(lp, "aTarget", 0.0)),
            "should_stop": bool(getattr(lp, "shouldStop", False)),
            "has_lead": bool(getattr(lp, "hasLead", False)),
            "source": str(getattr(lp, "longitudinalPlanSource", "")),
          })
        except Exception:
          pass
      elif typ in ("logMessage", "androidLog"):
        text = ""
        try:
          text = str(msg.logMessage)
        except Exception:
          try:
            text = str(msg.androidLog.message)
          except Exception:
            text = ""
        marker, payload = parse_marker_text(text)
        if marker:
          marker_rows.append({"rel_s": rel_s, "marker": marker, "payload": payload or {}})
  gps_rows.sort(key=lambda row: row["rel_s"])
  car_rows.sort(key=lambda row: row["rel_s"])
  plan_rows.sort(key=lambda row: row["rel_s"])
  marker_rows.sort(key=lambda row: row["rel_s"])
  return gps_rows, car_rows, plan_rows, marker_rows


def replay_dir(qlog_dir: Path, args: argparse.Namespace, ctx: Any, sidecar: Any, LogReader: Any) -> list[dict[str, Any]]:
  gps_rows, car_rows, plan_rows, marker_rows = read_qlog_inputs(qlog_dir, LogReader, ctx)
  map_index = sidecar.load_osm_event_index(args.osm_geojson)
  route_meta: dict[str, Any] = {}
  route = []
  if args.route_file and args.route_file.exists():
    route_meta = sidecar.load_json(args.route_file)
    try:
      route = ctx.build_route(ctx.load_route(args.route_file, None))
    except Exception:
      route = []

  rows: list[dict[str, Any]] = []
  last_replay_s = -1.0e9
  for gps in gps_rows:
    rel_s = float(gps["rel_s"])
    if rel_s - last_replay_s < args.period:
      continue
    car = nearest(car_rows, rel_s)
    speed_mps = (float(car["v_kph"]) / 3.6) if car else float(gps["sample"].speed_mps or 0.0)
    if speed_mps < args.min_speed_kph / 3.6:
      continue
    sample = gps["sample"]
    sample = ctx.GpsSample(row={}, t=sample.t, ll=sample.ll, speed_mps=speed_mps, heading_deg=sample.heading_deg)
    plan = nearest(plan_rows, rel_s)
    marker = nearest(marker_rows, rel_s, max_dt_s=2.0)

    t0 = time.perf_counter()
    match = None
    status = "no_match"
    if route:
      try:
        projection = ctx.project_to_route(sample.ll, route)
        if projection.cross_track_m <= args.max_cross_track_m:
          match = sidecar.route_projected_map_match(sample, route, projection.s, projection.cross_track_m, map_index, args.max_cross_track_m)
          status = "route_projected" if match is not None else "route_no_event"
        else:
          status = "route_cross_track_high"
      except Exception as exc:
        status = f"route_error:{type(exc).__name__}"
    if match is None:
      match = sidecar.heading_map_match(sample, map_index)
      if match is not None:
        status = "heading"
    compute_ms = (time.perf_counter() - t0) * 1000.0

    distance_m = None if match is None else float(match.distance_m)
    phase, target_kph, req_decel = distance_phase(distance_m, float(car["v_kph"]) if car else None)
    red_payload = marker["payload"] if marker else {}
    rows.append({
      "qlog_dir": str(qlog_dir),
      "segment": gps.get("segment", ""),
      "rel_s": round(rel_s, 3),
      "gps_source": gps.get("gps_source", ""),
      "lat": round(float(sample.ll.lat), 7),
      "lon": round(float(sample.ll.lon), 7),
      "heading_deg": "" if sample.heading_deg is None else round(float(sample.heading_deg), 2),
      "v_kph": "" if car is None else round(float(car["v_kph"]), 2),
      "a_ego": "" if car is None else round(float(car["a_ego"]), 3),
      "brake_pressed": "" if car is None else car["brake_pressed"],
      "gas_pressed": "" if car is None else car["gas_pressed"],
      "plan_a_target": "" if plan is None else round(float(plan["a_target"]), 3),
      "plan_should_stop": "" if plan is None else plan["should_stop"],
      "plan_has_lead": "" if plan is None else plan["has_lead"],
      "distance_status": status,
      "distance_m": "" if distance_m is None else round(distance_m, 2),
      "distance_mode": "" if match is None else match.mode,
      "event_kind": "" if match is None else match.kind,
      "event_source": "" if match is None else match.source,
      "distance_confidence": "" if match is None else round(float(match.confidence), 3),
      "distance_phase": phase,
      "target_kph": "" if target_kph is None else target_kph,
      "requested_decel_mps2": round(req_decel, 3),
      "distance_compute_ms": round(compute_ms, 3),
      "map_event_count": len(map_index.events or []),
      "map_error": map_index.error,
      "nearest_marker": "" if marker is None else marker["marker"],
      "red_present": red_payload.get("red_present", red_payload.get("target_red_present", "")) if isinstance(red_payload, dict) else "",
      "signal_range": red_payload.get("target_signal_range", red_payload.get("signal_range", "")) if isinstance(red_payload, dict) else "",
    })
    last_replay_s = rel_s
  return rows


def main() -> int:
  parser = argparse.ArgumentParser(description="Replay SiennaTSS25Plus GPS+OSM intersection distance calculation from qlog.")
  parser.add_argument("qlog_dirs", nargs="+", type=Path)
  parser.add_argument("--osm-geojson", type=Path, default=Path("/data/sienna_route/osm_events.geojson"))
  parser.add_argument("--route-file", type=Path)
  parser.add_argument("--output", type=Path, default=Path("qlog_distance_replay.csv"))
  parser.add_argument("--sidecar-dir", type=Path, default=Path(__file__).resolve().parent)
  parser.add_argument("--openpilot-root", type=Path, default=Path("/data/openpilot"))
  parser.add_argument("--schema-root", type=Path, default=Path(r"D:\Codex\.qlog_schema"))
  parser.add_argument("--period", type=float, default=1.5)
  parser.add_argument("--min-speed-kph", type=float, default=3.0)
  parser.add_argument("--max-cross-track-m", type=float, default=70.0)
  args = parser.parse_args()

  add_import_roots(args.openpilot_root, args.schema_root)
  LogReader = load_log_reader()
  ctx, sidecar = load_local_modules(args.sidecar_dir)

  all_rows: list[dict[str, Any]] = []
  for qlog_dir in args.qlog_dirs:
    all_rows.extend(replay_dir(qlog_dir, args, ctx, sidecar, LogReader))

  args.output.parent.mkdir(parents=True, exist_ok=True)
  fieldnames = list(all_rows[0].keys()) if all_rows else [
    "qlog_dir", "segment", "rel_s", "distance_status", "distance_m", "distance_compute_ms", "map_event_count", "map_error",
  ]
  with args.output.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_rows)
  summary = {
    "output": str(args.output),
    "rows": len(all_rows),
    "osm_geojson": str(args.osm_geojson),
    "qlog_dirs": [str(path) for path in args.qlog_dirs],
  }
  print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

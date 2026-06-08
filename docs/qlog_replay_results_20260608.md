# qlog Replay Results 2026-06-08

## Purpose

Replay qlog GPS/carState/longitudinalPlan samples through the local GPS+OSM distance logic and record the cost of each distance-generation step.

The output table includes `distance_compute_ms` for every replayed row.

## Local Dependency Setup

Windows qlog parsing needed local dependencies installed outside OneDrive:

```powershell
python -m pip install --target D:\Temp\qlog_pydeps_20260608 zstandard pycapnp
```

The replay tool uses `D:\Codex\.qlog_schema\cereal\log.capnp` when a full openpilot checkout is not available.

## Baseline Without OSM Event Map

Input qlog directories:

- `D:\Codex\commaai\20260608.2`
- `D:\Codex\commaai\20260608.1`
- `D:\Codex\commaai\20260607.2`

Output was written locally to:

- `D:\Temp\c3x_osm_distance_20260608\qlog_distance_replay_baseline_no_map.csv`

This CSV is not committed because it contains GPS coordinates.

Rows:

- `20260608.2`: 682
- `20260608.1`: 768
- `20260607.2`: 344
- Total: 1794

Compute cost without an OSM map:

| qlog | avg ms | p95 ms | p99 ms | max ms |
|---|---:|---:|---:|---:|
| 20260608.2 | 0.5601 | 1.106 | 1.412 | 1.944 |
| 20260608.1 | 0.6877 | 1.255 | 1.651 | 2.453 |
| 20260607.2 | 0.7303 | 1.382 | 1.907 | 2.121 |

All baseline rows showed `osm_geojson_missing`, so this validates replay mechanics and low idle cost, not real intersection distance.

## Synthetic OSM Event Test

A synthetic traffic-signal point was placed about 120 m ahead of the first qlog GPS sample in `20260608.2`.

Result:

- Rows: 682
- Rows with a heading distance match: 8
- Average compute cost: 0.4359 ms
- P95: 0.841 ms
- P99: 1.418 ms
- Max: 1.602 ms

First matched row:

- distance: 120.0 m
- mode: `osm_geojson_heading`
- phase: `prepare_slow`
- requested decel: `0.45 m/s^2`
- compute time: `0.59 ms`

This verifies the replay table and distance timing path. It does not validate real-world OSM event accuracy.


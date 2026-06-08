# SiennaTSS25Plus RedLight Assist

Private development workspace for the Toyota Sienna TSS2.5+/TSS3-lite red-light prepare, stop-line distance, and low-load qlog replay work.

This repository intentionally keeps code, design notes, and summarized test results separate from raw qlogs, qcamera video, GPS traces, and car identifiers.

## Current Status

- Red-light prepare and braking logic exists on the C3X stack, but road tests showed late/weak braking and occasional overshoot.
- The next distance layer has been implemented locally: GPS + local OSM event map, with route projection when a route exists and heading-cone fallback when no route exists.
- The `/intersection_distance` bridge remains a fallback/debug input, not the intended primary distance source.
- qlog replay tooling now produces a per-sample table including `distance_compute_ms`.
- This local repo has not been synced to C3X after the latest local GPS+OSM distance and qlog replay changes.

## Repository Layout

- `sidecars/`: C3X-side low-load services and route/OSM helpers.
- `tools/`: offline qlog replay and analysis tools.
- `scripts/`: service start scripts used on C3X.
- `restore/`: reboot/restore persistence script.
- `docs/`: progress, architecture, safety notes, and replay results.

## Privacy Rules

Do not commit:

- qlog/rlog/qcamera/raw video
- CSV replay tables containing GPS coordinates
- VIN, dongle ID, route traces, screenshots with plates, or raw CAN dumps
- generated archives or install bundles

Keep this repo private while active road-test data and vehicle-specific behavior are still being developed.

## Verified Local Checks

On 2026-06-08, these checks passed locally:

- Python AST parse for `sidecars/sienna_intersection_distance_sidecar.py`
- Python AST parse for `tools/qlog_distance_replay.py`
- `bash -n` for `scripts/start_intersection_distance_sidecar.sh`
- `bash -n` for `restore/restore_tss25_on_boot.sh`
- qlog replay baseline for `20260608.2`, `20260608.1`, and `20260607.2`
- synthetic OSM event replay that produced heading-based distances and compute-time measurements


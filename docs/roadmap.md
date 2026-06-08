# Roadmap

## Stage 1: Shadow Distance Validation

- Sync local GPS+OSM distance sidecar to C3X when online.
- Provide or generate `/data/sienna_route/osm_events.geojson`.
- Confirm `SiennaIntersectionDistanceState` shows active distances on real roads.
- Compare qlog replay distance with on-road UI/driver observation.

## Stage 2: Prepare Timing

- Use distance bands to start red-light prepare earlier.
- Keep first action as release/coast.
- Apply light braking while distance is still comfortable.
- Escalate braking only when distance/speed says stopping is still required.

## Stage 3: Stop-Line Refinement

- Add stop-line/white-line shadow only after red intent and prepare slowdown already exist.
- Prefer nearest ego-lane stop line when visible.
- Treat motorcycle box / multiple white lines as "stop earlier" risk.

## Stage 4: Robustness

- Add stale-state UI warning when traffic-light sidecar or distance sidecar is not producing fresh state.
- Keep sidecar restart watchdog lightweight.
- Add qlog replay reports after every road test.

## Stage 5: Packaging

- Convert install/remove actions into Patch API entries.
- Keep each feature independently installable and reversible.
- Preserve restore behavior across reboot without forcing openpilot restart.


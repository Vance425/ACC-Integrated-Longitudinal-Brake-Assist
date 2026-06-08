# Safety Notes

This project is experimental and vehicle-specific.

## Non-Negotiables

- Do not let OSM map distance create a stop decision by itself.
- Camera/sidecar red-light intent must already exist before distance-assisted red-light prepare/braking is used.
- Driver override must always win.
- Avoid automatic openpilot restart during road use.
- Sidecar watchdog may restart sidecars, but must not restart openpilot automatically.
- Keep CPU/disk load low on C3X.

## Known Risks

- Mixed traffic-light heads can be misclassified by camera-only logic.
- FAR/MID/NEAR visual range is not a physical distance measurement.
- OSM event points can be offset from the actual stop line.
- Heading-only no-route matching can select a nearby parallel road or future intersection if the cone is too wide.
- qlog replay validates decision logic, not final Toyota actuation.
- UI status can lag if sidecar/debug state goes stale.

## Privacy Risks

qlogs and replay CSVs often contain GPS coordinates and should not be committed.

Before making anything public, scrub:

- qlog/qcamera
- CSV/JSONL containing lat/lon
- VIN/dongle identifiers
- license plates and faces in images/video
- raw CAN dumps


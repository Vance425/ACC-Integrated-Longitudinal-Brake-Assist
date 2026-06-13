# C3X 同步狀態總表

最後更新：2026-06-09

這份文件是 `Comma ai` 工作區內 C3X 已同步/未同步狀態的中央管理檔。後續所有對話都應先讀這份文件，再決定是否需要同步、驗證或補文件；不要在單一對話裡各自維護一份狀態。

## 管理規則

- `已同步到 C3X` 只放已實際 scp/ssh 安裝、遠端語法檢查通過，且有基本 marker/param 驗證的項目。
- `本機準備待同步` 放已在本機檔案完成並通過本機語法檢查，但尚未部署到 C3X 的項目。
- `已關閉/回滾` 放曾部署過但目前不應視為 active 的功能。
- `舊本機實驗/未安裝` 放以前準備過、但目前不是最新同步包的一部分，也沒有裝到 C3X 的 patch 或工具。
- 每次同步、回滾或手動修改車機後，都要更新本檔。
- 若 C3X 不在線，只能更新 `本機準備待同步`，不能把項目移到 `已同步到 C3X`。
- C3X 相關狀態以本檔為準；`PROJECT_MEMORY.md` 只保留索引與重要背景。

## C3X 連線資訊

- 室內 Wi-Fi：`comma@192.168.31.162`
- 手機熱點：`comma@172.20.10.7`
- 目前狀態：2026-06-09 已同步最新待同步功能到室內 Wi-Fi `192.168.31.162`；同步時 `IsOnroad=0`、`IsEngaged=0`。

## 中央同步包

- 同步腳本：`D:\Temp\tss3_fix_20260609\sync_tss3_fix_to_c3x.ps1`
- 主要 restore repo：`D:\Codex\SiennaTSS25Plus-RedLight-Assist`
- 車機 restore 入口：`/data/sienna_custom/restore_tss25_on_boot.sh`
- 本機 restore 腳本：`D:\Codex\SiennaTSS25Plus-RedLight-Assist\restore\restore_tss25_on_boot.sh`

最新同步腳本目前會上傳並覆蓋：

- `/data/openpilot/selfdrive/controls/lib/longitudinal_planner.py`
- `/data/sienna_custom/longitudinal_planner_tss3_lite_restore.py`
- `/data/openpilot/tools/sienna_tss25_plus/traffic_light_sidecar.py`
- `/data/sienna_custom/traffic_light_sidecar_restore.py`
- `/data/openpilot/selfdrive/controls/lib/desire_helper.py`
- `/data/sienna_custom/desire_helper_sienna_restore.py`
- `/data/sienna_custom/restore_tss25_on_boot.sh`

## 已同步到 C3X

### 基礎車型與 OP-long

- Toyota Sienna TSS2.5+ / TSS25+ 車型辨識 baseline。
- `CarParams.carFingerprint=TOYOTA_SIENNA_TSS25_PLUS` 已驗證。
- OP-long 測試 baseline：
  - `ToyotaEnforceStockLongitudinal=0`
  - `ExperimentalMode=1`
  - `ExperimentalModeConfirmed=1`
  - `DynamicExperimentalControl=1`
  - `CarParams.openpilotLongitudinalControl=True`
- `params_keys.h` / `selfdrived.py` 早期 patch 曾讓 experimental mode 對 Toyota OP-long 測試可用。

### 通訊與 validity workaround

- `radard.py` workaround：維持 `radarState` valid，避免 `radarState` / `longitudinalPlan` validity cascade。
- `selfdrived.py` workaround：對 alive/frequency OK 但 validity false 的服務放寬 `ignore_valid`，包含 `liveCalibration`、`driverMonitoringState`、`livePose`、`liveDelay`、`liveParameters`、`liveTorqueParameters`、`driverAssistance`。
- `locationdTemporaryError` gate 放寬：只有 `livePose.inputsOK=False` 且 sensor/posenet 也失敗時才觸發。
- `selfdrivedLagging` 加約 3 秒 grace，降低短暫高負載造成的 soft disable。
- 注意：這些是已知 2026-06-02 validity cascade 的 rescue workaround，不應拿來掩蓋新的 panda/CAN/真實硬體故障。

### TSS3-lite 縱向控制

- `SiennaTss3LiteAssist=1` / `Shadow=1`。
- 紅燈/e2e stop-intent 輔助：
  - `SiennaTss3LiteE2eStopAssist=1`
  - min/max distance `2/50 m`
  - max decel `0.8 m/s^2`
- TSS3-lite stop hold：
  - low-speed stop hold
  - entry speed/distance、memory、max hold、standstill decel 參數已納入 restore。
- TSS3-lite OSM/sunnypilot speed-limit cap：
  - `SiennaTss3LiteOsmSpeedLimitCap=1`
  - 優先讀 sunnypilot speed-limit resolver / `liveMapDataSP` / `carStateSP`
  - fallback 才讀 `/data/sienna_route/osm_context.json`
  - `SiennaTss3LiteOsmSpeedLimitCapMaxDecel=0.25` 在最新 restore 中保守設定。

### 紅燈 prepare 與 traffic light sidecar

- `SiennaTrafficLightPrepareAssist=1` / `Shadow=1`。
- planner 只讀 `/data/params/d/SiennaTrafficLightState`，不在 planner 內做影像分析。
- sidecar 使用 wide road camera、低頻 numpy threshold；停車或 camera 不可用時降載。
- traffic-light state 支援：
  - red/mixed/green/yellow counts
  - target signal color / range
  - ego-lane signal classification
  - small ego-lane red candidate
  - white-line stop-line shadow
  - intersection marking shadow
- range control:
  - FAR/MID/NEAR target speed 與 decel 分段
  - first-red coast/no-accel
  - green release
  - uncertain / gas override timeout
- GPS/intersection-distance-assisted red-light prepare：
  - `SiennaTrafficLightGpsDistanceAssist=1`
  - GPS/OSM distance 不會自己創造紅燈意圖，只在紅燈候選已確認時提供距離分段。
- no-GPS high-speed guard / degrade：
  - `SiennaTrafficLightNoGpsHighSpeedGuardKph=60.0`
  - no-GPS 近距離分段 decel 參數已納入最新 restore。

### Traffic light watchdog

- `traffic_light_watchdog.py` 已同步。
- 低頻監看 sidecar PID/state。
- 車輛移動時 state stale、sidecar missing 或 processing error 連續超限會重啟 sidecar。
- 寫入 `/data/params/d/SiennaTrafficLightWatchdogState`。

### Traffic slowdown / 前車車流輔助

- `SiennaTrafficSlowdownAssist=1` / `Shadow=1`。
- Stage 4 已同步：
  - Stage 1/2/3：lead/traffic 早期 coast 與 comfort decel。
  - Stage 4：低速 close-lead stop/hold。
- stop gates：
  - `dRel <= 8 m`
  - `vEgo <= 2.0 m/s`
  - `vLead <= 0.5 m/s`
- 高速 close-range AEB 不由這層處理，仍交給原本 MPC/AEB。

### 轉彎與曲率縱向輔助

- `SiennaRampCurveAssist=1` / `Shadow=1`。
  - 高速匝道/彎道估計 lateral accel，必要時用減速降低橫向壓力。
  - 預設：min speed `35 kph`、start lat accel `1.15 m/s^2`、target `1.0 m/s^2`、max decel `0.5 m/s^2`。
- `SiennaLowSpeedTurnAssist=1` / `Shadow=1`。
  - 針對低速大彎轉向不足。
  - 只在 OP-long、selfdrive enabled、無油門/煞車覆蓋、低速高曲率、且有曲率 shortfall 或 lateral output 近飽和時減速。
  - 預設：`3-25 kph`、start curvature `0.035`、target lateral accel `0.42 m/s^2`、max decel `0.55 m/s^2`。
- `SiennaTurnSignalLaneChangeGate=1`。
  - 2026-06-09 已同步到 live/golden `desire_helper.py`。
  - 避免一般過彎/匝道打方向燈時誤觸發 `laneChangeLeft/Right`，把車往線邊拉。
  - 預設：低於 `60 kph` 或方向盤角度已達 `3 deg` 時，方向燈不進 lane-change desire。
- `SiennaCurveLaneBias=1`。
  - 2026-06-09 已同步到 live/golden `desire_helper.py`。
  - 高架/匝道小彎時避免貼內側護欄/車道線，降低乘客壓迫感。
  - 預設：`45-95 kph`、方向盤角度至少 `3 deg`、每 `1.0 s` pulse 一次。
  - 行為：右彎輕微 `keepLeft`，左彎輕微 `keepRight`；不使用強 `turnLeft/turnRight`。

### Route / OSM / intersection distance

- route receiver 已同步，port `8790`。
- OSM route safety sidecar 曾同步：
  - route rolling window metadata
  - partial-window / off-route expiry
  - route-end safety
- full OSM sidecar autostart 目前關閉，避免 CPU/lag。
- intersection distance sidecar 已同步：
  - `SiennaIntersectionDistanceAssist=1`
  - route/GPS/OSM event distance layer
  - `/intersection_distance` bridge fallback
  - real GPS+OSM map event distance 需要 `/data/sienna_route/osm_events.geojson`
- 最新 C3X 狀態曾驗證：`osm_geojson_missing` 時不會產生 real OSM event distance。

### UI 與顯示

- Brake bar UI：
  - 顯示目前縱向煞車請求來源與大小。
  - 來源包含 TSS3、traffic-light prepare、traffic slowdown、Taiwan stop debug。
  - 已修正為四段色彩與左側固定 layout。
- Intersection/traffic status UI：
  - 左側狀態 rail
  - STOP LINE card / brake bar overlap 已修正。
- Disable updates UI/persistence：
  - restore script 會維持 `DisableUpdates`，並停止 updater。

### qlog / debug

- planner debug markers 已改為較可靠的 qlog marker。
- 包含：
  - `SIENNA_TSS3_DEBUG`
  - `SIENNA_TRAFFIC_DEBUG`
  - `SIENNA_TRAFFIC_LIGHT_DEBUG`
  - `SIENNA_RAMP_CURVE_DEBUG`
  - `SIENNA_LOW_SPEED_TURN_DEBUG`
- restore 會 seed 多個 debug JSON，避免空檔案造成 reader error。

### Persistence / restore

- `/data/sienna_custom/restore_tss25_on_boot.sh` 是主要 restore 入口。
- restore 會修復/覆蓋：
  - planner live/golden
  - traffic-light sidecar live/golden
  - brake bar UI live/golden
  - watchdog live/golden
  - route/intersection sidecar scripts
  - runtime params
- `/data/continue.sh` 相關流程曾更新過，確保重開機/啟動後 restore params 不被清掉。

## 本機準備待同步

目前無待同步功能。

最新一次同步：

- 時間：2026-06-09
- IP：`192.168.31.162`
- 同步項目：`SiennaTurnSignalLaneChangeGate`、`SiennaCurveLaneBias`
- 遠端驗證：
  - `bash -n /data/sienna_custom/restore_tss25_on_boot.sh` OK
  - live/golden planner、traffic-light sidecar、desire helper `py_compile` OK
  - `/data/sienna_custom/restore_tss25_on_boot.sh` 執行 OK
  - `SiennaTurnSignalLaneChangeGate=1`
  - `SiennaCurveLaneBias=1`
  - `IsOnroad=0`
  - `IsEngaged=0`
  - `controlsd`、`plannerd`、`selfdrived`、`modeld` 未運行；下一次 onroad 啟動會載入新 `desire_helper.py`。

## 已關閉 / 回滾 / 不應視為 active

- `LaneTurnDesire=0`
  - 強 `turnLeft/turnRight` 不使用。
  - 原因：正常 marked-lane turn 會貼線，乘客體感不好。
- `SiennaOsmSpeedAssist=0`
  - 舊 OSM assist 關閉。
  - 目前保留 TSS3-lite speed-limit cap 作為主要速限輔助。
- `SiennaUrbanPostTurnAccelHold=0`
  - 路口轉完後加速 hold 目前關閉。
- full OSM sidecar autostart 關閉。
  - Route receiver 保留。
  - 需要時才啟動 OSM sidecar，避免 CPU/lag。
- `SiennaCurveComfortAssist` / `SiennaCurveComfortShadow`
  - 2026-05-30 曾部署，因 ACC engagement 後觸發 communication issue 已回滾。
  - 不要未經離線/車上 process 測試就重新部署。
- 早期 `TaiwanStopApproachControl` 類 active stopline patch 不作為目前主控制路徑。
  - 現在紅燈主線以 TSS3-lite / traffic-light prepare stack 為準。

## 舊本機實驗 / 未安裝

以下項目在 Comma ai 工作區曾準備過，但不是目前最新同步包的一部分，也沒有裝到 C3X。除非重新 review，否則不要直接同步。

- `sienna_tss25_plus_red_light_shadow_ui_20260601.patch`
  - shadow UI patch 曾安裝到 C3X/Patch API。
  - 後續另有 `2026-06-02.1` shadow validation optimization 本機版，增加 `raw_stop_distance`、`distance_jump`、`stable_frames`、`confidence_state`。
  - 本機版當時 `git apply --check` passed，但未同步到 C3X。
- `sienna_tss25_plus_red_light_op_long_active_20260601.patch`
  - OP-long-only active braking patch。
  - 本機 `git apply --check` passed。
  - 未安裝，且目前已被 TSS3-lite stack 取代。
- 舊 `SiennaTrafficSlowdownAssist` 早期 shadow/params_keys/control_api patch。
  - 已被後續 planner Stage 4 實作取代。
- 舊 `SiennaOsmSpeedAssist` route-derived target-speed cap。
  - 已被 TSS3-lite speed-limit cap / route safety / intersection distance layers取代。
- 本機 qlog replay / analysis 工具。
  - 例如 `D:\Temp\analyze_lateral_qlog_20260609_1.py`、`D:\Temp\c3x_osm_distance_20260608\qlog_distance_replay.py`。
  - 只作分析，不屬於車機同步項目。

## 下一次同步檢查清單

1. 確認 C3X offroad/not engaged。
2. 執行同步腳本到可連線 IP。
3. 遠端確認 `py_compile` 通過。
4. 遠端確認 markers：
   - `SiennaLowSpeedTurnAssist` in planner
   - `SiennaTurnSignalLaneChangeGate` in desire helper
   - `SiennaCurveLaneBias` in desire helper
   - `SiennaTrafficLightNoGpsHighSpeedGuardKph` in restore script
5. 執行 `/data/sienna_custom/restore_tss25_on_boot.sh`。
6. 若 openpilot/plannerd/controlsd 已在跑，且車輛 offroad/not engaged，再決定是否重啟相關 process。
7. 更新本檔，把成功部署的功能從 `本機準備待同步` 移到 `已同步到 C3X`。

## Pending Sync - 2026-06-11 TSS3 Traffic-Light Distance Guard

- Local package: `D:\Temp\tss3_fix_20260611_2`
- C3X sync status: pending; both known IPs timed out during this session (`192.168.31.162`, `172.20.10.7`).
- Files prepared:
  - `longitudinal_planner.py`
  - `longitudinal_planner_tss3_lite_restore.py`
  - `restore_tss25_on_boot.sh`
  - `sync_tss3_fix_to_c3x.ps1`
- Fix intent:
  - GPS/OSM stop-line distance control now requires fresh current red-stop evidence; memory alone cannot trigger GPS distance braking.
  - Above `SiennaTrafficLightGpsUrbanMaxKph=65.0`, no-current-red highway/expressway cases clear prepare memory and block GPS stop-line control.
  - `late_hard`/`hard` GPS phases may bypass stale gas override hold only when the gas pedal is not currently pressed and a fresh red-stop signal exists within `SiennaTrafficLightGasHoldLateBypassM=35.0`.
  - GPS `brake`/`hard`/`late_hard` braking now includes distance-based required decel instead of relying only on target-speed error.
- Local verification:
  - Python compile-without-pyc passed for both planner files.
  - PowerShell sync script parser check passed.
  - Local Git Bash/WSL `bash -n` was blocked by Windows access-denied; run `bash -n` on C3X during sync.

## Pending Sync - 2026-06-11 OSM Route Event Gate

- Local source: `D:\Temp\c3x_osm_distance_20260608`
- C3X sync status: synced later on 2026-06-11 to `comma@192.168.31.162`; earlier both known IPs timed out during the preparation session.
- Files changed:
  - `osm_route_sidecar.py`
  - `test_route_window_safety.py`
- Fix intent:
  - When a partial route is waiting for the next window, route window expired, or off-route expired, suppress forward route-event outputs so stale route turns/events cannot drive route-based decel.
  - Preserve `speed_limit.current_mps` during inactive route-event states so the TSS3-lite current-road speed-limit cap can still work without a valid forward route.
  - New context marker: `route_safety.route_event_active`.
  - Inactive states now report `target_speed_mps=null`, `target_reasons=[]`, `next_turn=null`, `next_osm_event=null`, and no next speed-limit event, while keeping current speed limit if map matching has one.
- Local verification:
  - Bundled Python `py_compile` passed for `osm_route_sidecar.py` and `sienna_route_receiver.py`.
  - `test_route_window_safety.py` passed (`route_window_safety_ok`).

## Synced - 2026-06-11 OSM Route Event Gate

- Synced to C3X: `comma@192.168.31.162`
- C3X state during sync: `IsOnroad=0`, `IsEngaged=0`
- Remote backup: `/data/sienna_tss25_plus/backups/20260611_115149-osm-route-event-gate`
- Installed files:
  - `/data/openpilot/tools/sienna_tss25_plus/osm_route_sidecar.py`
  - `/data/tools/SiennaTSS25Plus_route_receiver/osm_route_sidecar.py`
  - `/data/sienna_custom/sienna_api_bundle.tar.gz`
- Verified markers in live files and bundle:
  - `route_event_active`
  - `effective_next_turn`
  - `effective_next_event`
  - `target_reasons if route_event_active else []`
- Verification:
  - C3X `py_compile` passed for both installed sidecar paths.
  - Route receiver health returned OK on `127.0.0.1:8790`.
  - OSM sidecar started from `/data/tools/SiennaTSS25Plus_route_receiver/start_osm_route_sidecar.sh`; steady CPU after startup was about `2.0%`.
  - Current context is `status=waiting_for_route`, `route_safety.active=false`, because route is currently cleared.

## Synced - 2026-06-11 TSS3 Traffic-Light Distance Guard

- Synced to C3X: `comma@192.168.31.162`
- C3X state during sync: `IsOnroad=0`, `IsEngaged=0`, no `controlsd`/`plannerd`/`selfdrived`/`modeld` processes after install check.
- Remote backup: `/data/sienna_tss25_plus/backups/20260611_113520-tss3-traffic-light-distance-guard`
- Installed files:
  - `/data/openpilot/selfdrive/controls/lib/longitudinal_planner.py`
  - `/data/sienna_custom/longitudinal_planner_tss3_lite_restore.py`
  - `/data/sienna_custom/restore_tss25_on_boot.sh`
- Verified markers in live/golden planner:
  - `SiennaTrafficLightGpsUrbanMaxKph`
  - `gas_hold_late_bypass`
  - `current_stop_red_evidence`
  - `gps_distance_high_speed_blocked`
- Verified params:
  - `SiennaTrafficLightGpsUrbanMaxKph=65.0`
  - `SiennaTrafficLightGasHoldLateBypassM=35.0`
- Local sync package remains at: `D:\Temp\tss3_fix_20260611_2`

## Synced - 2026-06-11 Route Receiver GPS API

- Synced to C3X: `comma@192.168.31.162`
- Remote backups:
  - `/data/sienna_tss25_plus/backups/20260611_123542-route-receiver-gps-api-direct-path`
  - `/data/sienna_tss25_plus/backups/20260611_123829-route-receiver-venv-python`
- Installed files:
  - `/data/openpilot/tools/sienna_tss25_plus/sienna_route_receiver.py`
  - `/data/tools/SiennaTSS25Plus_route_receiver/sienna_route_receiver.py`
  - `/data/tools/SiennaTSS25Plus_route_receiver/start_route_receiver.sh`
  - `/data/sienna_custom/sienna_api_bundle.tar.gz`
- New endpoint: `GET /gps` on route receiver port `8790`.
- Response intent:
  - Prefer current `/data/sienna_route/osm_context.json` position when available.
  - Fallback to direct C3X cereal topics: `gpsLocationExternal`, `gpsLocation`, `liveLocationKalman`.
  - Include diagnostics under `direct_gps.gps_debug` and OSM state freshness under `age_s` / `fresh`.
- Start script now prefers `/usr/local/venv/bin/python` so `cereal` and `capnp` imports work in the receiver service; it falls back to `python3` only if the venv binary is absent.
- Verification:
  - Local `py_compile` and payload smoke tests passed.
  - C3X `py_compile` passed for both receiver paths.
  - `/health` returned OK after restart.
  - `/gps` returned valid JSON with `direct_gps.gps_debug` for all three GPS services. Parked/offroad state had no live GPS topic, so `ok=false` / `gps position unavailable` is expected until GPS messages publish.

## Synced - 2026-06-11 Android Provider GPS For Route Receiver

- Android app version: `0.1.37` / `versionCode 38`.
- APK output: `D:\Temp\sienna_amap_companion_20260611\sienna-amap-companion-0.1.37-debug.apk`.
- App behavior:
  - Each C3X route-window payload now includes `provider_gps` when the Android AMap location is fresh (`<=15 s`).
  - `provider_gps` is WGS84 export with original GCJ-02 coordinates, speed, bearing, altitude, accuracy, location type, and timestamp.
  - Route fingerprint/window identity intentionally ignores GPS so GPS drift does not force route reloads.
  - C3X window detail view shows provider GPS availability, age, and accuracy.
- C3X sync target: `comma@192.168.31.162`.
- Remote backup: `/data/sienna_tss25_plus/backups/20260611_130709-route-provider-gps`.
- Installed files:
  - `/data/openpilot/tools/sienna_tss25_plus/sienna_route_receiver.py`
  - `/data/tools/SiennaTSS25Plus_route_receiver/sienna_route_receiver.py`
  - `/data/openpilot/tools/sienna_tss25_plus/osm_route_sidecar.py`
  - `/data/tools/SiennaTSS25Plus_route_receiver/osm_route_sidecar.py`
  - `/data/sienna_custom/sienna_api_bundle.tar.gz`
- Receiver behavior:
  - Saves `provider_gps` from route payloads.
  - `GET /gps` now reports `provider_gps`, `provider_gps_age_s`, and `provider_gps_fresh`.
  - `/gps` fallback priority is OSM context position, direct C3X GPS topics, then Android provider GPS.
- OSM sidecar behavior:
  - C3X GPS remains first priority.
  - If C3X GPS topics have no sample, sidecar may use fresh `provider_gps` from the current route, capped by `--provider-gps-max-age-s` default `15.0`.
- Verification:
  - Android `assembleDebug` passed.
  - Python `py_compile` passed locally and on C3X for receiver and sidecar paths.
  - C3X marker checks passed.
  - Route receiver restarted and `/health` returned OK.
  - Current `/gps` response has `provider_gps=null` because no new 0.1.37 route payload has been posted yet.

## Synced - 2026-06-12 TSS3 UI Status/Stopline Layout

- Synced to C3X: `comma@172.20.10.7`
- C3X state during sync: `IsOnroad=1`, `IsEngaged=0`; UI process was running and was not restarted.
- Remote backup: `/data/sienna_tss25_plus/backups/20260611_194913-tss3-ui-status-stopline-layout`
- Installed files:
  - `/data/openpilot/selfdrive/ui/onroad/augmented_road_view.py`
  - `/data/openpilot/selfdrive/ui/mici/onroad/augmented_road_view.py`
  - `/data/sienna_custom/augmented_road_view_onroad_brakebar_restore.py`
  - `/data/sienna_custom/augmented_road_view_mici_brakebar_restore.py`
- UI changes:
  - Intersection/source badge radius increased to `56`, near driver-monitoring icon size, with a more transparent interior and softer shadow.
  - STOP LINE detail card moved right to `rect.x + 250`, made more transparent, and changed from duplicated `STOP STOP` text to `STOP LINE + distance + source + reason`.
- Verification:
  - C3X `py_compile` passed for both UI files.
  - Live/golden marker checks passed: `radius = 56`, `x = int(rect.x + 250)`, `STOP LINE`.
- Note: UI was not restarted because the device was onroad; changes will appear after UI/openpilot restarts or after a safe manual UI restart.

## Checked/Synced - 2026-06-12 Route Window Metadata

- Checked C3X via hotspot IP: `comma@172.20.10.7`.
- Current route is not full-sent:
  - `route_id=full_e7d972874873371c_w0_0_1000`
  - `is_partial_route=true`
  - `has_more=true`
  - `window_start_distance_m=0`
  - `window_end_distance_m=1000`
  - raw payload `route_length_m=1000`
  - raw payload `full_route_length_m=11296`
  - raw payload `route_polyline` points: `44`
  - raw payload turns: `3`
- The confusing part was receiver storage: it preserved route length/provider metadata inside `raw` and route-window context, but did not copy `route_length_m`, `full_route_length_m`, and `routing_provider` to the stored route top level.
- Synced receiver fix to C3X so future stored routes keep top-level metadata:
  - `routing_provider`
  - `destination_strategy`
  - `coordinate_source`
  - `coordinate_export`
  - `route_length_m`
  - `full_route_length_m`
  - `route_time_s`
  - `traffic_light_count`
- Remote backup: `/data/sienna_tss25_plus/backups/20260611_195038-receiver-window-metadata`.
- Installed files:
  - `/data/openpilot/tools/sienna_tss25_plus/sienna_route_receiver.py`
  - `/data/tools/SiennaTSS25Plus_route_receiver/sienna_route_receiver.py`
  - `/data/sienna_custom/sienna_api_bundle.tar.gz`
- Verification after restart:
  - `/health` OK.
  - Current stored route top level now shows `route_length_m=1000`, `full_route_length_m=11296`, `routing_provider=google_routes_api_compute_routes`, and `polyline_points=44`.

## Synced - 2026-06-12 Receiver GPS UI

- Synced to C3X hotspot IP: `comma@172.20.10.7`.
- Receiver UI now has a visible `GPS 接收狀態` section above the route JSON.
- The UI fetches `/gps` every 3 seconds and shows:
  - selected GPS source
  - Android provider GPS received/fresh/stale/not received
  - provider GPS lat/lon
  - provider GPS accuracy and age
  - raw `/gps` JSON under `gpsStatus`
- `UI_VERSION=2026-06-12.1-gps-ui`; `/health` verified OK with this version.
- Remote backups:
  - `/data/sienna_tss25_plus/backups/20260611_195847-receiver-gps-ui`
  - `/data/sienna_tss25_plus/backups/20260611_200055-receiver-gps-ui-version`
- Verification on `/gps` after sync:
  - `ok=true`
  - `source=osm_context`
  - `fresh=true`
  - `provider_gps_present=true`
  - `provider_gps_fresh=false`
  - `provider_gps_age_s` was about `1024 s`, so current Android provider GPS is visible but stale until the app posts a new route/window.

## Synced - 2026-06-12 TSS3 UI Circular Brake Gauge

- Synced to C3X: `comma@172.20.10.7`
- C3X state during sync: `IsOnroad=1`, `IsEngaged=0`; UI process was running and was not restarted.
- Remote backup: `/data/sienna_tss25_plus/backups/20260611_200159-tss3-ui-brake-gauge`
- Installed files:
  - `/data/openpilot/selfdrive/ui/onroad/augmented_road_view.py`
  - `/data/openpilot/selfdrive/ui/mici/onroad/augmented_road_view.py`
  - `/data/sienna_custom/augmented_road_view_onroad_brakebar_restore.py`
  - `/data/sienna_custom/augmented_road_view_mici_brakebar_restore.py`
- UI changes:
  - Replaced bottom-center horizontal brake bar with a lower-right circular brake gauge.
  - Gauge center shows `BRK` numeric decel value and source (`TL`, `TSS3`, `LEAD`, `STOP`).
  - Outer ring uses four segments from lower-left to upper-left to upper-right to lower-right: green, yellow-green, yellow, red.
  - Current value is shown by a light progress arc and dot.
- Verification:
  - C3X `py_compile` passed for both UI files.
  - Live/golden marker checks passed: `needle_ratio`, `value_angle = 135.0 + 270.0`, `cx = int(rect.x + rect.width - 132)`.
- Note: UI was not restarted because the device was onroad; changes will appear after UI/openpilot restarts or after a safe manual UI restart.

## Synced - 2026-06-12 TSS3 UI Circular Brake Gauge Limit Size

- Synced to C3X: `comma@172.20.10.7`
- Remote backup: `/data/sienna_tss25_plus/backups/20260611_201230-tss3-ui-brake-gauge-limit-size`
- Installed files:
  - `/data/openpilot/selfdrive/ui/onroad/augmented_road_view.py`
  - `/data/openpilot/selfdrive/ui/mici/onroad/augmented_road_view.py`
  - `/data/sienna_custom/augmented_road_view_onroad_brakebar_restore.py`
  - `/data/sienna_custom/augmented_road_view_mici_brakebar_restore.py`
- UI changes:
  - Circular brake gauge resized to limit-speed-icon scale: `radius = 42`.
  - Gauge moved tighter to lower-right: `cx = rect.width - 104`, `cy = rect.height - 118`.
  - Center value size adjusted to `24` to preserve readability at the smaller size.
- Verification:
  - C3X `py_compile` passed during install.
  - Live/golden marker checks passed: `cx = int(rect.x + rect.width - 104)`, `cy = int(rect.y + rect.height - 118)`, `radius = 42`, `value_size = 24`.
- Note: UI was not restarted; changes will appear after UI/openpilot restarts or after a safe manual UI restart.
## Synced - 2026-06-12 UI Stop-Line Road Width

- Synced to C3X: `comma@192.168.31.162`
- C3X state during sync: offroad/not engaged; `ui` process was not running.
- Remote backup: `/data/sienna_tss25_plus/backups/20260611_225516-ui-stopline-road-width`
- Installed files:
  - `/data/openpilot/selfdrive/ui/onroad/augmented_road_view.py`
  - `/data/openpilot/selfdrive/ui/mici/onroad/augmented_road_view.py`
  - `/data/sienna_custom/augmented_road_view_onroad_brakebar_restore.py`
  - `/data/sienna_custom/augmented_road_view_mici_brakebar_restore.py`
- Change intent:
  - Stop-line overlay should only be about road/lane width, not span most of the screen.
  - Changed stop-line half-width formula from `rect.width * (0.11 + 0.32 * closeness**0.70)` to `rect.width * (0.09 + 0.12 * closeness**0.70)`.
- Verification:
  - Local read-only `compile()` syntax check passed.
  - C3X `py_compile=0` for all four installed/golden files.
  - Remote diff confirmed only the `half_w` formula changed in onroad/mici UI.

## Synced - 2026-06-12 UI Large Status/Brake Icons

- Synced to C3X: `comma@192.168.31.162`
- C3X state during sync: `IsOnroad=0`, `IsEngaged=0`; `ui` process was not running, so no UI restart was needed.
- Remote backup: `/data/sienna_tss25_plus/backups/20260611_224224-ui-large-status-brake-icons`
- Installed files:
  - `/data/openpilot/selfdrive/ui/onroad/augmented_road_view.py`
  - `/data/openpilot/selfdrive/ui/mici/onroad/augmented_road_view.py`
  - `/data/sienna_custom/augmented_road_view_onroad_brakebar_restore.py`
  - `/data/sienna_custom/augmented_road_view_mici_brakebar_restore.py`
- Change intent:
  - Make the left intersection/TSS vehicle-status circle and lower-right brake gauge visually match the top-left speed-limit circle.
  - Both icons now use `radius = 68`; brake gauge arc width and BRK/value/source text were enlarged.
- Verification:
  - Local read-only `compile()` syntax check passed for both source files.
  - C3X `py_compile` passed for all four installed/golden files.

## Synced - 2026-06-12 Highway Stopline Guard + Brake Gauge Size

- Synced to C3X: `comma@192.168.31.162`
- Remote backup: `/data/sienna_tss25_plus/backups/20260611_231818-tss3-highway-stopline-ui-fix`
- Installed files:
  - `/data/openpilot/selfdrive/controls/lib/longitudinal_planner.py`
  - `/data/sienna_custom/longitudinal_planner_tss3_lite_restore.py`
  - `/data/sienna_custom/restore_tss25_on_boot.sh`
  - `/data/openpilot/selfdrive/ui/onroad/augmented_road_view.py`
  - `/data/openpilot/selfdrive/ui/mici/onroad/augmented_road_view.py`
  - `/data/sienna_custom/augmented_road_view_onroad_brakebar_restore.py`
  - `/data/sienna_custom/augmented_road_view_mici_brakebar_restore.py`
- Planner change:
  - Traffic-light GPS stop-line control is now blocked whenever `v_ego >= SiennaTrafficLightGpsUrbanMaxKph` instead of allowing high-speed control when a camera red candidate exists.
  - New/explicit debug reason: `blocked_gps_high_speed_guard`.
  - Current param remains `SiennaTrafficLightGpsUrbanMaxKph=65.0`.
- UI change:
  - Circular brake gauge increased from `radius = 42` to `radius = 50`.
  - Position adjusted to `cx = rect.width - 118`, `cy = rect.height - 132`.
  - Center value size adjusted to `28`.
- Verification:
  - Local Python compile check passed for planner and UI files.
  - C3X install ran `py_compile`, `bash -n`, and restore successfully.
  - Live/golden marker checks passed.
  - C3X was offroad/not engaged for install; UI was restarted afterward while offroad/not engaged and new UI PID was observed.

## Local Pending Sync - 2026-06-12 Stop-Line TTL / Display Valid Guard

- Local package: `D:\Temp\tss3_20260612_highway_stopline_ui_fix`
- C3X sync status: pending; `192.168.31.162` and `172.20.10.7` both timed out during this session.
- Planner change:
  - Added explicit `stop_line_display_valid` and `stop_line_control_valid`.
  - `gps_intersection_distance_m` is now written as `null` unless the current red evidence is fresh, GPS distance is valid, green release is not active, and the high-speed guard is not blocking it.
  - This prevents stale/expired STOP LINE distance from being reused on highway/expressway or between surface-road intersections.
- UI change:
  - STOP LINE overlay now requires fresh debug data and `stop_line_display_valid`.
  - Fallback sources `SiennaIntersectionDistanceState` and `TaiwanStopApproachDebug` now require a fresh timestamp within 3 seconds.
  - Left status circle no longer treats stale `gps_distance_valid` or stale `status != go` as OP LONG activity.
  - Re-merged previously verified UI sizing/shape: status circle and brake gauge use `radius = 68`; stop-line width uses the narrower road-width formula.
  - STOP LINE road overlay is now semi-transparent: line alpha `118`, shadow alpha `58`, highlight alpha `86`, and label background alpha `38`, so it does not cover the original C3X camera view.
- Restore/install:
  - `longitudinal_planner_tss3_lite_restore.py` updated from the patched planner.
  - `restore_tss25_on_boot.sh` marker checks now include the stop-line TTL/display-valid UI and planner markers.
- Verification:
  - Local Codex bundled Python `py_compile` passed for planner, planner restore, onroad UI, and mici UI.
  - Re-ran UI `py_compile` after the semi-transparent STOP LINE update.

## Local Pending Sync - 2026-06-12 Full Braking Chain / Red-Light Stop-Hold Bridge

- Local package: `D:\Temp\tss3_20260612_highway_stopline_ui_fix`
- C3X sync status: pending; this update is local only until C3X is reachable.
- Planner change:
  - Added a traffic-light stop-hold bridge so GPS red-light braking can hand off to TSS3-lite final stop/hold.
  - New runtime params:
    - `SiennaTrafficLightStopHoldBridge=1`
    - `SiennaTrafficLightStopHoldBridgeStartM=80.0`
    - `SiennaTrafficLightStopHoldBridgeHoldS=4.0`
  - Bridge arms only when traffic-light GPS distance is fresh/control-valid, red evidence is current, and phase is `brake`, `hard`, or `late_hard`.
  - Bridge is cleared by green release, high-speed guard, GPS green suppression, or driver gas override.
  - TSS3-lite now treats an active bridge as `red_stop_intent=true` and uses the bridge distance as `stop_distance` when it is the nearest valid stop source.
  - This closes the prior gap where the car could slow for a red light, lose/expire distance, then let ACC/OP-long resume acceleration before final stop-hold latched.
- Debug/verification:
  - `SiennaTrafficLightPrepareDebug` now reports `stop_bridge_active`, `stop_bridge_distance_m`, `stop_bridge_phase`, `stop_bridge_reason`, and remaining hold time.
  - `SiennaTss3LiteDebug` now reports `traffic_light_bridge_active`, bridge distance, phase, reason, and remaining time.
  - Local Codex bundled Python `py_compile` passed for planner, planner restore, onroad UI, and mici UI.
  - `install_on_c3x.sh` and `restore_tss25_on_boot.sh` passed `bash -n`.

## Local Pending Sync - 2026-06-12 Multi-Source Braking Safety Fallbacks

- Local package: `D:\Temp\tss3_20260612_highway_stopline_ui_fix`
- C3X sync status: pending; this update is local only until C3X is reachable.
- Planner change:
  - Added fallback stop-hold bridge sources for GPS dropouts:
    - GPS distance bridge remains priority 1.
    - White-line / intersection-marking bridge is priority 2 when red evidence is current, white-line confidence is high, and speed is below the configured cap.
    - Red-light range bridge is priority 3 when GPS control is unavailable but camera red `target_signal_range` is `mid` or `near`.
    - Existing model/E2E/MPC/lead stop intent remains the final TSS3-lite backup source.
  - New runtime params:
    - `SiennaTrafficLightRangeStopBridge=1`
    - `SiennaTrafficLightRangeStopBridgeMaxKph=45.0`
    - `SiennaTrafficLightRangeStopBridgeMidM=55.0`
    - `SiennaTrafficLightRangeStopBridgeNearM=30.0`
    - `SiennaTrafficLightWhiteLineStopBridge=1`
    - `SiennaTrafficLightWhiteLineStopBridgeMaxKph=45.0`
    - `SiennaTrafficLightWhiteLineStopBridgeMinConfidence=0.85`
    - `SiennaTrafficLightWhiteLineStopBridgeStopM=18.0`
    - `SiennaTrafficLightWhiteLineStopBridgeEarlyM=30.0`
  - White-line bridge requires current red stop evidence, so the green-light/motorcycle-box false positive seen in qlog should not arm the bridge.
  - Added `safety_backup_source` to `SiennaTss3LiteDebug` so road tests can identify whether final stop/hold is being driven by `traffic_light_bridge`, `model`, `e2e_or_lead`, `mpc`, or `none`.
- Restore/install:
  - `longitudinal_planner_tss3_lite_restore.py` updated from the patched planner.
  - `restore_tss25_on_boot.sh` now persists all new fallback params.
  - `install_on_c3x.sh` marker checks now include range bridge, white-line bridge, and safety backup source markers.
- Verification:
  - Local Codex bundled Python `py_compile` passed for planner, planner restore, onroad UI, and mici UI.
  - `install_on_c3x.sh` and `restore_tss25_on_boot.sh` passed `bash -n`.

### Sync Attempt - 2026-06-12

- Requested sync to C3X, but no install was performed because C3X was not reachable.
- Tried:
  - `192.168.31.162`: SSH timeout; neighbor table shows unreachable.
  - `172.20.10.7`: SSH timeout.
  - `192.168.31.155`: SSH port not usable / connection refused; not accepted as C3X.
  - `comma.local` and `tici.local`: hostname resolution failed.
- Pending package remains: `D:\Temp\tss3_20260612_highway_stopline_ui_fix`

## Synced - 2026-06-12 Multi-Source Braking Safety Fallbacks

- Synced to C3X: `comma@192.168.31.162`
- C3X state during sync: `IsOnroad=0`, `IsEngaged=0`.
- Remote backup: `/data/sienna_tss25_plus/backups/20260612_112801-tss3-highway-stopline-ui-fix`
- Installed files:
  - `/data/openpilot/selfdrive/controls/lib/longitudinal_planner.py`
  - `/data/sienna_custom/longitudinal_planner_tss3_lite_restore.py`
  - `/data/sienna_custom/restore_tss25_on_boot.sh`
  - `/data/openpilot/selfdrive/ui/onroad/augmented_road_view.py`
  - `/data/openpilot/selfdrive/ui/mici/onroad/augmented_road_view.py`
  - `/data/sienna_custom/augmented_road_view_onroad_brakebar_restore.py`
  - `/data/sienna_custom/augmented_road_view_mici_brakebar_restore.py`
- Includes:
  - Stop-line TTL/display-valid guard.
  - Semi-transparent STOP LINE road overlay.
  - Large left status circle and right brake gauge UI.
  - Traffic-light stop-hold bridge.
  - Multi-source safety fallbacks: GPS distance, white-line/intersection marking, red-light range, then existing model/E2E/MPC/lead stop intent.
- Verification:
  - C3X install script completed successfully and created the backup above.
  - Live/golden/restore marker checks passed for `SiennaTrafficLightRangeStopBridge`, `SiennaTrafficLightWhiteLineStopBridge`, `safety_backup_source`, `traffic_light_bridge_active`, and `stop_line_display_valid`.
  - Runtime params confirmed on C3X:
    - `SiennaTrafficLightStopHoldBridge=1`
    - `SiennaTrafficLightRangeStopBridge=1`
    - `SiennaTrafficLightWhiteLineStopBridge=1`
    - `SiennaTrafficLightWhiteLineStopBridgeMinConfidence=0.85`
    - `SiennaTrafficLightRangeStopBridgeMaxKph=45.0`
  - Manager and UI processes were present after sync; UI process observed as `selfdrive.ui.ui`.

## Synced - 2026-06-13 Traffic-Light Bridge Deadline Brake

- Synced to C3X: `comma@192.168.31.162`
- C3X state during sync: `IsOnroad=0`, `IsEngaged=0`; UI process was running.
- Local package: `D:\Temp\tss3_20260612_highway_stopline_ui_fix`
- Remote backup: `/data/sienna_tss25_plus/backups/20260612_200002-tss3-highway-stopline-ui-fix`
- Installed files:
  - `/data/openpilot/selfdrive/controls/lib/longitudinal_planner.py`
  - `/data/sienna_custom/longitudinal_planner_tss3_lite_restore.py`
  - `/data/sienna_custom/restore_tss25_on_boot.sh`
  - `/data/openpilot/selfdrive/ui/onroad/augmented_road_view.py`
  - `/data/openpilot/selfdrive/ui/mici/onroad/augmented_road_view.py`
  - `/data/sienna_custom/augmented_road_view_onroad_brakebar_restore.py`
  - `/data/sienna_custom/augmented_road_view_mici_brakebar_restore.py`
- Planner change:
  - Traffic-light stop bridge hold defaults to 10 seconds and reads up to 20 seconds.
  - Active traffic-light bridge now acts as a red-stop intent latch unless cleared by green, high-speed guard, or gas override.
  - Existing bridge distance is not allowed to jump farther when fallback sources report a larger estimated distance.
  - Added TSS3-lite traffic-light bridge deadline brake before generic e2e/stopline envelope checks.
  - Deadline bands are persisted as params: near 30 m, hard 15 m, stop 8 m, max decel 1.6 m/s^2.
- Verification:
  - Install script completed successfully on C3X.
  - Live/golden planner marker checks passed for `SiennaTss3LiteTrafficLightBridgeDeadline`, `applied_traffic_light_bridge_deadline`, `stop_bridge_intent_active`, and `SiennaTrafficLightStopHoldBridgeHoldS`.
  - Runtime params confirmed on C3X:
    - `SiennaTrafficLightStopHoldBridgeHoldS=10.0`
    - `SiennaTss3LiteTrafficLightBridgeDeadline=1`
    - `SiennaTss3LiteTrafficLightBridgeDeadlineMaxDecel=1.6`
    - `SiennaTss3LiteTrafficLightBridgeNearM=30.0`
    - `SiennaTss3LiteTrafficLightBridgeHardM=15.0`
    - `SiennaTss3LiteTrafficLightBridgeStopM=8.0`
    - `SiennaTrafficLightStopHoldBridge=1`
    - `SiennaTrafficLightRangeStopBridge=1`
    - `SiennaTrafficLightWhiteLineStopBridge=1`

## Synced - 2026-06-13 Fast Intersection UI State

- Synced to C3X: `comma@192.168.31.162`
- C3X state during sync: `IsOnroad=0`, `IsEngaged=0`; UI process was restarted offroad after install.
- Local package: `D:\Temp\tss3_20260612_highway_stopline_ui_fix`
- Remote backup: `/data/sienna_tss25_plus/backups/20260612_203218-tss3-highway-stopline-ui-fix`
- Installed files:
  - `/data/openpilot/selfdrive/controls/lib/longitudinal_planner.py`
  - `/data/sienna_custom/longitudinal_planner_tss3_lite_restore.py`
  - `/data/sienna_custom/restore_tss25_on_boot.sh`
  - `/data/openpilot/selfdrive/ui/onroad/augmented_road_view.py`
  - `/data/openpilot/selfdrive/ui/mici/onroad/augmented_road_view.py`
  - `/data/sienna_custom/augmented_road_view_onroad_brakebar_restore.py`
  - `/data/sienna_custom/augmented_road_view_mici_brakebar_restore.py`
- Change:
  - Added low-load UI state file `/data/params/d/SiennaIntersectionStatusUiState`.
  - Planner writes compact `go/prepare/stop + ACC/OP_LONG/TSS` status at up to 0.5 s cadence without adding qlog load.
  - Left intersection status circle now prefers this fast UI state with a 1.2 s freshness gate, then falls back to the existing debug files.
  - Restore seeds the fast UI state as `GO / ACC`.
- Verification:
  - Local Python compile passed for planner, planner restore, onroad UI, and mici UI.
  - Local `bash -n` passed for install and restore scripts.
  - C3X install script completed successfully.
  - C3X marker checks passed for `SiennaIntersectionStatusUiState`, `write_sienna_intersection_status_ui_state`, and `_sienna_intersection_ui_state`.
  - UI process restarted from old PID `125939` to new PID `127268`.

## Synced - 2026-06-13 Large Intersection/Brake UI Circles

- Synced to C3X: `comma@192.168.31.162`
- C3X state during sync: `IsOnroad=0`, `IsEngaged=0`; UI process was restarted offroad after install.
- Local package: `D:\Temp\tss3_20260612_highway_stopline_ui_fix`
- Remote backup: `/data/sienna_tss25_plus/backups/20260612_204647-tss3-highway-stopline-ui-fix`
- UI change:
  - Left intersection status circle radius increased from `68` to `84`.
  - Left status text and `GO/SLOW/STOP` label enlarged.
  - Right BRK circular gauge radius increased from `68` to `84`.
  - BRK gauge moved inward to `rect.width - 158`, `rect.height - 180`.
  - BRK center value enlarged to `42`.
- Verification:
  - Local Python compile passed for onroad and mici UI files.
  - Local `bash -n` passed for install script.
  - C3X install script completed successfully.
  - Live/golden UI marker checks passed for `radius = 84` and `rect.width - 158`.
  - UI process restarted from old PID `127268` to new PID `153279`.

## Synced - 2026-06-13 Stop-Line Card Alignment

- Synced to C3X: `comma@192.168.31.162`
- C3X state during sync: `IsOnroad=0`, `IsEngaged=0`; UI process was restarted offroad after install.
- Local package: `D:\Temp\tss3_20260612_highway_stopline_ui_fix`
- Remote backup: `/data/sienna_tss25_plus/backups/20260612_210830-tss3-highway-stopline-ui-fix`
- UI change:
  - STOP LINE card moved up from `rect.height - 146` to `rect.height - 226`.
  - Card size increased from `360x74` to `386x92`.
  - STOP LINE title, distance, source, reason, and brake strip were enlarged/repositioned to align visually with the lower-left driver-monitoring circle.
- Verification:
  - Local Python compile passed for onroad and mici UI files.
  - Local `bash -n` passed for install script.
  - Local marker checks passed for `w, h = 386, 92` and `rect.height - 226`.
  - C3X install script completed successfully.
  - Live/golden UI marker checks passed for `w, h = 386, 92` and `rect.height - 226`.
  - UI process restarted from old PID `153279` to new PID `196172`.

## Synced - 2026-06-13 Stop Source Confidence

- Synced to C3X: `comma@192.168.31.162`
- C3X state during sync: `IsOnroad=0`, `IsEngaged=0`.
- Local package: `D:\Temp\tss3_20260612_highway_stopline_ui_fix`
- Remote backup: `/data/sienna_tss25_plus/backups/20260613_012913-tss3-highway-stopline-ui-fix`
- Planner change:
  - Added stable source/confidence classification for stop-distance sources.
  - `SiennaTrafficLightPrepareDebug` now reports `distance_source_kind` and `distance_confidence`.
  - `SiennaTss3LiteDebug` now reports `traffic_light_bridge_source_kind`, `traffic_light_bridge_confidence`, `safety_backup_source_kind`, and `safety_backup_confidence`.
  - Mapping:
    - GPS bridge/control: `gps / high`
    - GPS display only: `gps / mid`
    - White-line bridge: `white_line / mid`
    - Range bridge/camera range only: `range / low`
    - Model/e2e/mpc backup: `model|e2e_or_lead|mpc / mid`
  - Deadline brake now uses confidence-aware max decel:
    - high confidence keeps `SiennaTss3LiteTrafficLightBridgeDeadlineMaxDecel`.
    - mid confidence caps at `SiennaTss3LiteTrafficLightBridgeMidConfidenceMaxDecel=1.30`.
    - low confidence far caps at `SiennaTss3LiteTrafficLightBridgeLowConfidenceFarMaxDecel=0.45`.
    - low confidence near caps at `SiennaTss3LiteTrafficLightBridgeLowConfidenceNearMaxDecel=1.10`.
- Verification:
  - Local Python compile passed for planner and planner restore.
  - Local `bash -n` passed for install and restore scripts.
  - C3X install script completed successfully.
  - Live/golden planner marker checks passed for `distance_source_kind`, `safety_backup_confidence`, and `traffic_light_bridge_effective_max_decel`.
  - Runtime params confirmed on C3X:
    - `SiennaTss3LiteTrafficLightBridgeMidConfidenceMaxDecel=1.30`
    - `SiennaTss3LiteTrafficLightBridgeLowConfidenceFarMaxDecel=0.45`
    - `SiennaTss3LiteTrafficLightBridgeLowConfidenceNearMaxDecel=1.10`

## Synced - 2026-06-13 Traffic-Light Intent Latch

- Synced to C3X: `comma@172.20.10.7`
- C3X state before install: `IsOnroad=1`, `IsEngaged=0`.
- Local package: `D:\Temp\tss3_20260612_highway_stopline_ui_fix`
- Remote backup: `/data/sienna_tss25_plus/backups/20260613_032338-tss3-highway-stopline-ui-fix`
- Planner change:
  - Added a traffic-light stop intent latch to prevent ACC from immediately accelerating again when red-light distance or stop bridge briefly drops out.
  - New params:
    - `SiennaTss3LiteTrafficLightIntentLatchS=8.0`
    - `SiennaTss3LiteTrafficLightIntentNoAccelMaxKph=65.0`
  - The latch primarily applies no-accel behavior; it does not convert low-confidence distance into heavy braking.
  - Release conditions include clear green, gas override, brake override, not enabled, stock longitudinal mode, disabled param, or timeout.
- Debug:
  - `traffic_light_intent_latched`
  - `traffic_light_intent_evidence`
  - `traffic_light_intent_release_reason`
  - `traffic_light_intent_age_s`
- Verification:
  - Local Python compile passed for planner and planner restore.
  - Local `bash -n` passed for restore script.
  - C3X install script completed successfully.
  - Runtime params confirmed after install.

## Synced - 2026-06-13 Distance Failure Reasons

- Synced to C3X: `comma@172.20.10.7`
- C3X state before install: `IsOnroad=1`, `IsEngaged=0`.
- Local package: `D:\Temp\tss3_20260612_highway_stopline_ui_fix`
- Remote backup: `/data/sienna_tss25_plus/backups/20260613_040753-tss3-highway-stopline-ui-fix`
- Planner change:
  - Added distance failure diagnostics for traffic-light GPS/OSM stop distance.
  - New debug fields:
    - `gps_distance_fail_reason`
    - `osm_stop_candidate_reason`
    - `traffic_light_state_distance_valid`
    - `gps_distance_source`
  - `get_sienna_osm_stop_candidate()` now reports why a candidate is unavailable, including missing context, inactive route, stale context, non-stop event, invalid distance, or distance too far.
- UI change:
  - STOP LINE card source text now displays compact failure labels instead of only `NO DIST`.
  - Labels include `GPS NO MAP`, `GPS STALE`, `OSM NO ROUTE`, `OSM NO STOP`, `GPS HIGH SPD`, `NO RED TARGET`, `NO RED NOW`, `GPS FAR`, and `GPS WAIT`.
- Verification:
  - Local Python compile passed for planner, planner restore, onroad UI, and mici UI.
  - Local `bash -n` passed for restore script.
  - C3X install script completed successfully.
  - Post-install SSH verification could not be completed because the car hotspot timed out immediately after install, but the install script returned `[DONE]` and backup path.

# 下一步規劃

## 2026-06-13 優先項

- 先用最新 qlog 統計 `gps_distance_fail_reason` / `osm_stop_candidate_reason`，確認紅燈距離失效主要原因。
- 若主要是 `NO RED TARGET`，優先修本車道燈號與混合燈號目標選擇。
- 若主要是 `GPS NO MAP` / `OSM NO ROUTE`，優先修 intersection distance sidecar 與 OSM 候選路口。
- 若主要是 `GPS FAR`，調整 GPS start/soft/brake/hard bands，改善提早減速時機。
- 距離來源穩定後，再做最後 5-10 m stop-and-hold 與白線 offset。

完整現況整理見：[ACC-Integrated-Longitudinal-Brake-Assist 整合式縱向煞車輔助系統](acc_integrated_longitudinal_brake_assist.md)

## Stage 1: Shadow 距離驗證

- C3X 上線後，同步 GPS+OSM 距離 sidecar。
- 準備或產生 `/data/sienna_route/osm_events.geojson`。
- 確認 `SiennaIntersectionDistanceState` 在真實道路上會出現 active distance。
- 對照 qlog replay、UI 顯示和駕駛觀察。

## Stage 2: 提前減速時機

- 使用距離 bands 更早開始紅燈 prepare。
- 第一階段只放油門滑行。
- 距離仍足夠時只輕剎。
- 距離/速度顯示停不住時才升級剎車力道。

## Stage 3: 停止線與白線 shadow

- 只有紅燈意圖與 prepare 已存在時才啟用白線判斷。
- 優先選本車道、最靠近自己的停止線。
- 多條白線、機車停等區，先視為應該提早停的風險。

## Stage 4: 穩定性與可見性

- sidecar stale 時 UI 必須第一時間顯示狀態異常。
- watchdog 只重啟 sidecar，保持低負載。
- 每次實測後都產 qlog replay 報告。

## Stage 5: Patch API 包裝

- 將每個功能拆成可安裝/可移除的 Patch API 項目。
- 紅燈偵測、距離 sidecar、UI、planner control 分開管理。
- restore 必須能跨重開機保存，但不強制自動重啟 openpilot。

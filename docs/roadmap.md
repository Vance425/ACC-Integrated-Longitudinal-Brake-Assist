# 下一步規劃

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


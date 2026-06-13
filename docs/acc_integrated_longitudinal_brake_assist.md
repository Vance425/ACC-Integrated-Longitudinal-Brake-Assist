# ACC-Integrated-Longitudinal-Brake-Assist

中文名稱：整合式縱向煞車輔助系統

更新日期：2026-06-13

這份文件整理目前 Toyota Sienna TSS2.5+ 上的 `ACC-Integrated-Longitudinal-Brake-Assist`。它整合 ACC、OP-long 與 TSS assist 相關的縱向控制輔助，涵蓋加減速、跟車、紅燈 prepare、停止線 bridge、速限 cap、彎道/匝道減速與最後 stop/hold。

## 命名原因

`ACC-Integrated-Longitudinal-Brake-Assist` 比單純稱為「紅燈停車」或「TSS3-lite 煞車」更準確，原因如下：

- `ACC-Integrated`：這套系統不是獨立取代原車 ACC，而是和 ACC、OP-long、sunnypilot / openpilot 的縱向控制堆疊一起工作。
- `Longitudinal`：功能範圍是車輛縱向控制，也就是加速、減速、跟車、煞停與 stop/hold，不包含橫向轉向控制本身。
- `Brake`：目前主要優化目標仍是減速與煞車時機，包括紅燈、停止線、前車、速限與彎道減速。
- `Assist`：保留輔助系統語氣，避免讓人誤以為它是完全自動煞車、AEB，或能取代駕駛判斷。

因此，這個名稱比較符合目前實際架構：它是「整合 ACC / OP-long / TSS assist 的縱向煞車輔助層」，不是完全自動駕駛，也不是單一紅燈停止功能。

## 核心原則

- 以原廠安全邊界與 openpilot longitudinal control 為前提。
- 任何輔助都必須能被駕駛油門、剎車、disengage 立即覆蓋。
- 高速或低可信來源不能直接造成重煞。
- 紅燈與停止線距離來源必須標註可信度，避免把 camera-only 推估當成精準距離。
- sidecar / UI / qlog 只提供輔助資訊，不應拖慢 C3X 或造成 process not running。

## 目前已具備的功能

### 1. 紅燈偵測與 prepare

- 低負載 traffic-light sidecar 會產生 `/data/params/d/SiennaTrafficLightState`。
- Planner 讀取紅燈、混合燈號、本車道燈號、FAR/MID/NEAR、白線與路口標線欄位。
- 只要看到本次路口有紅燈意圖，會進入 prepare 狀態。
- 明確綠燈會釋放 prepare 與 bridge。
- 人工踩油門或剎車會立即覆蓋。

### 2. 紅燈意圖 latch，防止 ACC 回加速

2026-06-13 新增：

- `SiennaTss3LiteTrafficLightIntentLatchS=8.0`
- `SiennaTss3LiteTrafficLightIntentNoAccelMaxKph=65.0`

作用：

- 紅燈停止意圖成立後，若 stop bridge / distance 短暫消失，先限制 ACC 不要馬上補油加速。
- latch 期間主要是 no-accel，不會因低可信來源直接重煞。
- 綠燈、油門、剎車、disengage、OP-long 不可用或 8 秒超時會釋放。
- qlog/debug 欄位包含 `traffic_light_intent_latched`、`traffic_light_intent_evidence`、`traffic_light_intent_release_reason`、`traffic_light_intent_age_s`。

### 3. 停止線 / 紅燈 stop bridge

目前 bridge 來源：

- GPS/OSM traffic signal distance
- 白線 / 路口標線 sidecar
- camera FAR/MID/NEAR range fallback

主要參數：

- `SiennaTrafficLightStopHoldBridge=1`
- `SiennaTrafficLightStopHoldBridgeHoldS=10.0`
- `SiennaTrafficLightRangeStopBridge=1`
- `SiennaTrafficLightWhiteLineStopBridge=1`
- `SiennaTss3LiteTrafficLightBridgeDeadline=1`
- `SiennaTss3LiteTrafficLightBridgeNearM=30.0`
- `SiennaTss3LiteTrafficLightBridgeHardM=15.0`
- `SiennaTss3LiteTrafficLightBridgeStopM=8.0`

行為：

- GPS 距離可信且進入 brake/hard/late band 時，會 arm traffic-light bridge。
- bridge 會依車速推進距離，不允許 fallback 距離突然跳更遠。
- 進入 deadline brake 後，依距離與可信度計算需要的減速度。

### 4. 來源可信度

2026-06-13 已加入 stop-distance source confidence：

| 來源 | 可信度 | 用途 |
|---|---|---|
| GPS bridge/control | high | 可做主要 deadline braking |
| GPS display only | mid | 可顯示與輔助判斷 |
| white-line bridge | mid | 可做最後輔助，但仍需驗證穩定性 |
| range bridge / camera range | low | 遠距離只允許輕度或 no-accel |
| model/e2e/mpc | mid | 作為 OP 內部停止意圖備援 |

可信度對應制動上限：

- high：使用 `SiennaTss3LiteTrafficLightBridgeDeadlineMaxDecel`
- mid：上限 `SiennaTss3LiteTrafficLightBridgeMidConfidenceMaxDecel=1.30`
- low far：上限 `SiennaTss3LiteTrafficLightBridgeLowConfidenceFarMaxDecel=0.45`
- low near：上限 `SiennaTss3LiteTrafficLightBridgeLowConfidenceNearMaxDecel=1.10`

### 5. 距離失效原因可視化

2026-06-13 新增：

- `gps_distance_fail_reason`
- `osm_stop_candidate_reason`
- `traffic_light_state_distance_valid`

STOP LINE UI 右側會顯示短碼，不再只有 `NO DIST`：

| UI 短碼 | 意義 |
|---|---|
| `GPS NO MAP` | OSM / distance sidecar 沒有候選路口 |
| `GPS STALE` | OSM context 或距離資料過期 |
| `OSM NO ROUTE` | route/context 未 active |
| `OSM NO STOP` | OSM 候選不是 stop/traffic_signals/intersection 類型 |
| `GPS HIGH SPD` | 高速保護擋下紅燈距離控制 |
| `NO RED TARGET` | 有影像資料，但未形成目標紅燈 |
| `NO RED NOW` | 當下紅燈證據不足 |
| `GPS FAR` | 距離存在但超過控制起點 |
| `GPS WAIT` | 距離存在但尚未進控制條件 |

下一趟 qlog 可以用這些欄位統計：紅燈有看到時，到底是 GPS/OSM 缺資料、燈號目標失敗、方向過濾失敗，還是被高速保護擋掉。

### 6. 前車減速 / 跟車提前鬆油門

目前 TSS3-lite 已包含 traffic slowdown stage：

- lead / radar 前車距離與相對速度。
- 前車較慢時先 no-accel / coast。
- 距離縮短後進入輕煞與較重制動。
- stage 4 保留前車停止時的更強制動與停止輔助。

主要參數：

- `SiennaTrafficSlowdownAssist=1`
- `SiennaTrafficSlowdownLookaheadM=160.0`
- `SiennaTrafficSlowdownCoastStartM=100.0`
- `SiennaTrafficSlowdownStage=4`
- `SiennaTrafficSlowdownComfortDecelMps2=1.2`
- `SiennaTrafficSlowdownStopDRelM=8.0`

### 7. 速限 cap

- 使用 sunnypilot resolver / live map / carStateSP / OSM context 取速限。
- 目前採保守 cap，避免高速上因速限來源跳動造成強烈減速。
- 主要參數：
  - `SiennaTss3LiteOsmSpeedLimitCap=1`
  - `SiennaTss3LiteOsmSpeedLimitCapMinConfidence=0.70`
  - `SiennaTss3LiteOsmSpeedLimitCapMaxDecel=0.25`

### 8. 彎道、匝道與轉彎後加速保護

目前包含：

- ramp curve speed guard
- low-speed turn speed guard
- post-turn acceleration hold（目前預設關閉）
- turn signal lane-change gate

目的：

- 快速道路出匝道或大彎時，不讓車速維持 ACC 設定直接衝進彎。
- 低速大角度轉彎時，避免轉彎中補油過猛。
- 高速/快速道路打方向燈換道時，保留 lane-change gate，避免和彎道修正互相打架。

## UI 顯示

C3X UI 目前新增：

- 左側路口狀態圓圈：
  - 綠：正常 / GO
  - 黃：prepare / 制動準備
  - 紅：stop / hold
  - 中間顯示來源：`ACC`、`OP LONG`、`TSS`
- 左下 STOP LINE card：
  - 顯示停止線距離或 `--`
  - 顯示距離來源或失效短碼
  - 顯示目前 phase/reason
  - 半透明背景，不遮擋主要畫面
- 右下 BRK 圓形表：
  - 中間顯示 requested braking 數值
  - 外圈分四段：維持/鬆油門/輕煞/重煞

## 安全邊界

目前保護：

- `IsEngaged=1` 時 install script 會拒絕安裝。
- 高速狀態下 GPS 紅燈控制會被 `SiennaTrafficLightGpsUrbanMaxKph` 或 high-speed guard 擋下。
- 低可信距離來源遠距離只允許低 decel。
- 油門、剎車、disengage 會釋放紅燈 intent latch / stop hold。
- 綠燈穩定成立後會釋放紅燈 prepare/bridge。
- sidecar stale 時 UI 會顯示失效原因，不應悄悄假裝距離有效。

## 已知限制

- 紅燈本身有偵測，但距離仍可能缺失或不穩。
- 白線 / 機車停等格判斷尚未證明足夠穩定，目前只能作輔助。
- camera FAR/MID/NEAR 不是公尺距離，不能單獨拿來精準停車。
- 快速道路誤 STOP LINE 已加保護與失效短碼，但仍需用 qlog 驗證來源。
- OP-long 才能真正 longitudinal 介入；原廠 ACC 模式只能透過可用的 OP-long / experimental path 發揮。

## 下一步

1. 用最新 qlog 統計 `gps_distance_fail_reason` / `osm_stop_candidate_reason` 分布。
2. 若最多是 `NO RED TARGET`，優先修本車道燈號與混合燈號選擇。
3. 若最多是 `GPS NO MAP` / `OSM NO ROUTE`，優先修 intersection distance sidecar 與 OSM candidate。
4. 若最多是 `GPS FAR`，調整 GPS control start / soft / brake bands。
5. 距離穩定後，再強化最後 5-10 m stop-and-hold 與白線 offset。

## 最近 C3X 同步紀錄

- `20260613_032338-tss3-highway-stopline-ui-fix`
  - 紅燈 intent latch / no-accel 鎖定。
- `20260613_040753-tss3-highway-stopline-ui-fix`
  - GPS/OSM 距離失效原因 debug。
  - STOP LINE UI 失效短碼顯示。

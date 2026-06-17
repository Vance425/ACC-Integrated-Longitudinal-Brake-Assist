# Toyota Sienna TSS2.5+ 整合式縱向煞車輔助研究

更新日期：2026-06-17

本文整理 Toyota Sienna TSS2.5+ 在 comma C3X / sunnypilot / openpilot 架構下，針對「縱向煞車輔助」所做的研究、實作與路測觀察。此系統目前定位為駕駛輔助研究，不是自動駕駛，也不是 AEB 或取代駕駛決策的安全系統。

## 名稱與定位

建議名稱：

`ACC-Integrated-Longitudinal-Brake-Assist`

中文可稱為：

`ACC 整合式縱向煞車輔助系統`

使用這個名稱的原因是：

- `ACC-Integrated`：系統不是獨立煞車 ECU，而是建立在原廠 ACC、openpilot OP-long、sunnypilot 狀態與 TSS 輔助邏輯之上。
- `Longitudinal`：研究範圍集中在車輛縱向控制，也就是加速、放油門、跟車、減速、停車與短暫 hold。
- `Brake`：核心目標是改善前方交通、紅燈、停止線、彎道與速限情境下的煞車時機。
- `Assist`：保留輔助系統語氣，避免讓人誤解為完全自動煞車或取代駕駛判斷。

## 研究背景

Toyota Sienna TSS2.5+ 原廠 ACC 在跟車與巡航方面相對穩定，但在下列情境仍有改善空間：

- 紅燈或停止線前，ACC 可能維持巡航速度，直到駕駛介入。
- 前車突然離開或加速後，前方紅燈才暴露，系統可能再次加速。
- 快速道路匝道或大彎，ACC 可能依設定速度前進，彎中速度過高。
- 速限顯示存在，但車速限制不一定會實際約束 OP-long / ACC 目標速度。
- 模型可看到停止意圖，但距離估計、白線判斷與 stop hold 尚不穩定。

本研究的方向不是直接暴力接管煞車，而是把多個訊號來源整合成一套保守的縱向輔助策略：

- 早期以 no-accel / coasting 為主。
- 中段以舒適減速為主。
- 近距離才允許較強煞車。
- 資料可信度不足時，降級為提示或輕度控制。
- 綠燈、駕駛補油、系統異常時必須釋放。

## 系統架構

目前系統分成五層：

1. 訊號來源層
2. 判斷與距離估計層
3. 縱向策略層
4. 安全與降級層
5. UI / qlog 可觀測性層

### 1. 訊號來源層

目前使用或研究中的來源包括：

- `carState`
  - 車速、檔位、煞車、油門、ACC 狀態、cruise availability。
- `radarState` / lead vehicle
  - 前車距離、相對速度、TTC、前車停車狀態。
- `modelV2`
  - openpilot 模型的路徑、停止意圖、道路幾何與預期速度。
- `longitudinalPlan`
  - OP-long 產生的速度與加速度軌跡。
- `liveMapDataSP` / sunnypilot speed limit
  - 目前道路速限與 map context。
- GPS / OSM / route sidecar
  - 前方路口、traffic signal、stop candidate、route event、距離估算。
- Traffic-light sidecar
  - 紅燈、綠燈、混合燈號、本車道燈號、FAR/MID/NEAR 粗略距離。
- White-line / intersection marking shadow
  - 停止線、斑馬線、機車停等區等候選標線。

### 2. 判斷與距離估計層

距離目前不是單一來源，而是多來源融合：

- GPS + OSM distance
  - 目標是提供較穩定的路口距離。
  - 需要處理 route stale、off-route、OSM 無 traffic signal、GPS 不新鮮等問題。
- Camera range
  - 使用燈號大小與位置推估 FAR / MID / NEAR。
  - 優點是低成本、即時；缺點是距離不精準。
- Model / E2E stop intent
  - 可以判斷模型是否「想停」，但不一定提供可靠停止線距離。
- White-line shadow
  - 目標是在最後停車階段微調停車點，避免停到機車格後方或越線。
  - 目前仍屬不穩定來源，不應單獨觸發重煞。

目前資料可信度分級：

| 來源 | 可信度 | 用途 |
|---|---|---|
| GPS/OSM 新鮮距離 + 當前紅燈證據 | high | 可進入主要減速 / deadline brake |
| GPS 顯示可用但控制條件不足 | mid | UI 提示、保守減速 |
| White-line / intersection marking | mid | 近距離停車點修正 |
| Camera FAR/MID/NEAR | low | no-accel、coast、低可信 fallback |
| Model / E2E stop intent | mid | 輔助確認停車意圖 |
| Lead vehicle stop | high for following | 跟車停車、近距離煞停 |

## 已實現功能

### A. OP-long / TSS2.5+ 基礎整合

已實現：

- Toyota Sienna TSS2.5+ fingerprint：`TOYOTA_SIENNA_TSS25_PLUS`
- OP-long / experimental mode 相關參數持久化
- 原廠 ACC + openpilot 視覺 / planner 的縱向控制研究路徑
- 通訊異常 rescue workaround
  - `radarState` validity cascade 緩解
  - `selfdrivedLagging` grace
  - `locationdTemporaryError` gate 放寬
  - `selfdrived` realtime CPU affinity fallback
  - `SubMaster ignore_avg_freq` 版本相容修正

最新 qlog 顯示，之前的「上車系統無回應」主因不是紅燈 watchdog，而是 `selfdrived` rescue patch 使用了該版 sunnypilot 沒有的 `ignore_avg_freq` 屬性，導致 `selfdrived` crash。已改為版本相容寫法。

### B. 紅燈 prepare / no-accel

已實現：

- Traffic-light sidecar 產生紅燈 / 綠燈 / 混合燈號狀態。
- 偵測紅燈時進入 prepare。
- 若未看到明確綠燈，系統傾向先不加速。
- Traffic-light intent latch
  - 避免紅燈證據短暫消失後，ACC 立即重新加速。
  - 主要作用是 no-accel，不把低可信資料直接轉成重煞。
- 綠燈、補油、條件失效時釋放。

目的：

- 先解決「看到紅燈仍繼續拉回 ACC 設定速度」的問題。
- 讓駕駛在 UI 上第一時間知道系統是否打算停車。

### C. 紅燈距離與停止線控制

已實現：

- GPS/OSM intersection distance sidecar。
- Traffic-light GPS distance assist。
- STOP LINE display valid / TTL guard。
- 高速道路防誤判 guard：
  - 高於設定速度時，不允許 stale STOP LINE 或高速場景紅燈候選觸發大幅減速。
- Distance failure reason：
  - `GPS NO MAP`
  - `GPS STALE`
  - `OSM NO ROUTE`
  - `OSM NO STOP`
  - `GPS HIGH SPD`
  - `NO RED TARGET`
  - `NO RED NOW`
  - `GPS FAR`
  - `GPS WAIT`

目的：

- 不只顯示 `NO DIST`，而是知道為什麼沒有距離。
- 方便路測時判斷是 GPS、OSM、紅燈證據、route、還是 high-speed guard 造成。

### D. Stop bridge / stop hold

已實現：

- Traffic-light stop-hold bridge。
- 紅燈 bridge hold latch。
- bridge 距離不允許突然跳遠。
- 距離短暫掉成 0 時，短時間保留 stop intent。
- TSS3-lite final stop / hold handoff。
- Deadline bands：
  - near：約 30 m
  - hard：約 15 m
  - stop：約 8 m

目的：

- 解決「前段有減速，但接近停止線時距離掉失，ACC 又加速出去」。
- 把紅燈 prepare、距離、停止線、最後 hold 串成完整鏈。

目前限制：

- 如果白線判斷不穩，最後停車點仍可能偏前或越線。
- 如果紅燈距離來源不可信，只能保守控制，不能直接重煞。

### E. 多來源安全 fallback

已實現 fallback priority：

1. GPS/OSM stop distance
2. White-line / intersection marking bridge
3. Camera red-light range bridge
4. Model / E2E / MPC stop intent
5. Lead vehicle stop intent

已實現 confidence-aware braking：

- high confidence：允許較完整 deadline brake。
- mid confidence：限制最大減速度。
- low confidence far：只允許很輕的控制。
- low confidence near：可稍微提高減速度，但仍不視為高可信停車線。

目的：

- GPS 掉了不等於系統失明。
- 但 fallback 不能比 GPS 更激進，避免誤煞。

### F. 前車 / 交通流減速

已實現：

- Lead vehicle distance / relative speed based slowdown。
- Traffic slowdown Stage 1-4。
- 前車比本車慢時，先 no-accel / coast。
- 距離縮小後進入舒適減速。
- 近距離且前車接近停止時，進入較強減速 / stop intent。

主要參考條件：

- 前車距離 `dRel`
- 相對速度 `vRel`
- closing speed
- TTC
- dynamic headway
- lead stop velocity

目的：

- 解決前方車流變慢時，ACC 太晚反應或加速感太強。
- 在高速 / 快速道路跟車中，優先避免突然重煞。

### G. 速限 cap

已實現：

- sunnypilot / OSM / route context speed-limit cap 研究。
- 可讀取當前道路 speed limit。
- 保守最大減速度限制，避免因速限變化造成突兀煞車。

目前觀察：

- UI 顯示速限不代表縱向控制一定成功套用。
- 需要確認 speed limit source 是否進入 planner 端，而不只是 UI 顯示。
- 速限 cap 不應取代前方障礙 / 紅燈 / 彎道減速邏輯。

### H. 彎道 / 匝道速度守門

已實現：

- Ramp curve speed guard。
- Low-speed turn speed guard。
- Turn signal lane-change gate。
- 大角度轉向與低速轉彎情境的 no-surge / no-accel 研究。

目的：

- 快速道路下匝道或大彎時，不讓 ACC 盲目維持設定速度。
- 低速轉彎中避免突然加速。

目前限制：

- 大彎與匝道仍需要更穩定的道路曲率 / route event。
- 不應只靠方向盤角度，因為方向盤角度可能是駕駛修正或車道線誤差。

### I. UI 可觀測性

已實現：

- 左側路口 / 車況狀態圓形 UI。
  - 內圈：目前車況狀態，例如 GO / PREPARE / STOP。
  - 外圈：watchdog / 輔助功能狀態。
- STOP LINE card。
  - 顯示距離、來源、phase、失敗原因。
  - 改為半透明，避免蓋住原始 C3X 畫面。
- 右下 BRK circular gauge。
  - 顯示目前 requested braking / decel level。
  - 用顏色區分加速/維持、滑行、輕煞、重煞。
- qlog marker：
  - `SIENNA_TSS_EVENT`
  - `SIENNA_TRAFFIC_LIGHT_DEBUG`
  - `SIENNA_TSS3_DEBUG`
  - `SIENNA_TRAFFIC_DEBUG`
  - `SIENNA_TAIWAN_STOP_DEBUG`
  - `SIENNA_RAMP_CURVE_DEBUG`
  - `SIENNA_LOW_SPEED_TURN_DEBUG`

目的：

- 讓駕駛知道系統目前是否打算停車。
- 路測後可以從 qlog 反推為什麼煞車、為什麼不煞車、為什麼距離失效。

### J. Watchdog / 降載 / 恢復

已實現：

- Traffic-light sidecar watchdog。
- sidecar stale / processing error 偵測。
- watchdog 狀態寫入 UI。
- CPU / processing 持續超標才降載，避免瞬間 loading 就關功能。
- 自動重啟 sidecar，但不自動重啟 openpilot。
- onroad transition recorder：
  - 記錄上車 / onroad 過程中的 panda、manager、selfdrived、controlsd、CPU、watchdog 狀態。

最新調查：

- 近期「系統無回應」不是 traffic-light watchdog 造成。
- qlog 中明確看到 `selfdrived` 因 patch 相容性 crash。
- 已修正並加入 restore，避免重開後被還原。

## 路測觀察

已觀察到的有效行為：

- 有些紅燈情境能進入 prepare。
- 有時可提前 no-accel / 輕減速。
- 前車減速 / 停車情境可觸發 traffic slowdown。
- UI 能顯示 STOP LINE / BRK / 狀態圓形。
- qlog 中能看到 TSS event marker 與各 debug reason。

已觀察到的問題：

- 紅燈停車仍有越線。
- 有時偵測到紅燈後短暫煞車，又被 ACC 拉回加速。
- GPS/OSM distance 有時沒有值或 stale。
- STOP LINE 曾在高速道路誤出現，後續已加 high-speed guard 與 TTL/display-valid。
- 白線 / 機車格判斷仍不穩，不能單獨作為強煞依據。
- sidecar / OSM / curve / white-line 分析都要注意 C3X 負載。
- OP-long / selfdrived patch 需要版本相容，否則會造成 process not running。

## 安全邊界

這套系統目前必須遵守下列原則：

- 駕駛永遠負責最終煞車與通行判斷。
- 不把 camera-only 的遠距離紅燈直接轉成重煞。
- 低可信來源只允許 no-accel / coast / 輕微減速。
- 高速道路禁止 stale STOP LINE 觸發強減速。
- 補油、明確綠燈、駕駛接管、系統異常時要釋放。
- Watchdog 可以重啟 sidecar，但不應自動重啟 openpilot。
- 任何 install / restart 前必須確認 `IsEngaged=0`。

## 目前整體階段

目前比較合理的階段定位是：

`Stage 2.5 / Stage 3 early`

原因：

- 已不只是 shadow UI，已有 no-accel、coast、traffic slowdown、bridge、deadline brake、stop intent latch 等控制邏輯。
- 但紅燈停止線距離與白線最後停點仍不夠穩定。
- 仍需要路測與 qlog 回放持續校正。
- 還不能稱為完整可依賴的紅燈停車功能。

## 下一步

優先方向：

1. 修正紅燈後段越線
   - 強化 stop bridge 到 final hold 的 handoff。
   - 確認距離掉失後是否仍保留停車意圖。
   - 分析 MID / NEAR 到實際停止位置的距離誤差。

2. 穩定 GPS/OSM 距離
   - 確認 OSM candidate 是否真的是本路口 traffic signal。
   - route stale / off-route / no route 必須清楚降級。
   - 加入距離計算耗時與來源可信度統計。

3. 白線只做近距離修正
   - 不讓白線單獨觸發停車。
   - 只在紅燈 stop intent 已成立、低速、近距離時修正停車點。

4. 前車突然離開後的紅燈暴露
   - 這是高風險情境。
   - 需要 lead-away red-light reveal latch。
   - 前車消失後，如果畫面紅燈存在且速度仍高，應先 no-accel，再依距離可信度決定煞車。

5. 系統健康與自我恢復
   - onroad transition recorder 繼續收集。
   - selfdrived/controlsd crash 必須第一時間在 UI 或狀態檔可見。
   - rescue patch 需維持版本相容。

## 結論

本研究的核心成果是把 Toyota Sienna TSS2.5+ 的原廠 ACC、OP-long、模型停止意圖、紅燈偵測、GPS/OSM 距離、前車狀態與 UI/qlog 可觀測性整合成一套「縱向煞車輔助」框架。

目前已能做到：

- 看見紅燈後進入 prepare。
- 用 no-accel / coast 抑制 ACC 繼續加速。
- 根據前車距離與相對速度提早減速。
- 使用 GPS/OSM、白線、camera range、model stop intent 作為多來源 fallback。
- 在 UI 上顯示系統是否打算停車、STOP LINE 狀態與煞車力道。
- 在 qlog 中保留可分析的 debug marker。

但目前仍不能宣稱是可靠紅燈自動停車系統。它比較準確的定位是：

一套正在路測與迭代中的 ACC 整合式縱向煞車輔助研究，用來降低 ACC 在紅燈、前車、彎道與速限情境下的突兀加速與晚煞車風險，同時保留駕駛接管與多層安全降級。

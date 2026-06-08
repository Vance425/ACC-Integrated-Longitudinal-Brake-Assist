# 安全注意

這是實驗性、車輛特定的 longitudinal 輔助研究。

## 不可退讓的原則

- OSM 距離不能單獨創造停車決策。
- 必須先有 camera/sidecar 紅燈意圖，距離才可用於 prepare/braking。
- 駕駛補油、踩剎車、接管永遠優先。
- 行車中不要自動重啟 openpilot。
- watchdog 可以重啟 sidecar，但不能自動重啟 openpilot。
- C3X CPU、記憶體、磁碟負載必須保守。

## 已知風險

- 混合燈號可能被 camera-only 邏輯誤判。
- FAR/MID/NEAR 是影像狀態，不是物理距離。
- OSM traffic signal 點位可能離實際停止線有偏移。
- 沒 route 時，heading cone 可能抓到平行道路或下一個路口。
- qlog replay 能驗證邏輯，不等於 Toyota/ACC 一定執行。
- UI 狀態如果 sidecar stale，可能讓駕駛誤以為功能還在跑。

## 隱私風險

qlog 和 replay CSV 通常含 GPS 座標，不應 commit。

公開前必須清理：

- qlog / qcamera
- 含 lat/lon 的 CSV / JSONL
- VIN / DongleId
- 車牌、人臉、地點截圖
- raw CAN dump


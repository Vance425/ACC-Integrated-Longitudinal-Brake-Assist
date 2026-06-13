# SiennaTSS25Plus 紅燈輔助研究

這是 Toyota Sienna TSS2.5+ / TSS3-lite 紅燈提前減速、停止線距離、低負載 qlog replay 的研究專案。

這個 repo 主要給自己研究和復盤用，所以文件以繁體中文為主。原始 qlog、qcamera、GPS 軌跡、車輛識別資料不放進來，只保留程式、設計筆記、測試摘要和可重跑工具。

目前正式整理名稱為 `ACC-Integrated-Longitudinal-Brake-Assist`（整合式縱向煞車輔助系統）。這個名稱比較準確，因為 ACC、OP-long、TSS assist 都屬於車輛縱向控制範圍，涵蓋加減速、跟車與煞停；而 `Assist` 保留輔助系統定位，不會讓人誤以為它是完全自動煞車或取代駕駛。

## 目前狀態

- 紅燈 prepare / braking 邏輯已經在 C3X stack 上做過實車測試，但仍有「太晚才剎」「剎車力道太弱」「超線」問題。
- 最新本地版本已補上 GPS + OSM 路口事件距離計算。
- 有 route 時，會把 OSM 事件投影到路線上，算沿路線前方距離。
- 沒 route 時，會用 GPS heading cone 找前方可能屬於本車道的紅綠燈/路口事件。
- `/intersection_distance` bridge 保留為備援和測試入口，但不是主距離來源。
- qlog replay 工具已能輸出每次距離計算耗時 `distance_compute_ms`。
- 最新本地 GPS+OSM 距離 sidecar 尚未同步到 C3X，因為當時 C3X 不在線上。

## 目錄

- `sidecars/`: C3X 上低負載服務與 OSM/route helper。
- `tools/`: 離線 qlog replay / 分析工具。
- `scripts/`: C3X 啟動腳本。
- `restore/`: 重開機後恢復設定的腳本。
- `docs/`: 進度、架構、安全注意、測試結果與路線圖。

## 重要文件

- [ACC-Integrated-Longitudinal-Brake-Assist 整合式縱向煞車輔助系統](docs/acc_integrated_longitudinal_brake_assist.md)
- [目前進度](docs/progress_20260608.md)
- [系統架構](docs/architecture.md)
- [qlog replay 結果](docs/qlog_replay_results_20260608.md)
- [安全注意](docs/safety_notes.md)
- [下一步路線圖](docs/roadmap.md)

## 隱私規則

不要 commit：

- qlog / rlog / qcamera / 原始影片
- replay CSV，因為通常含 GPS 座標
- VIN、DongleId、路線軌跡、車牌、人臉、raw CAN dump
- 產生出的安裝包、壓縮包、臨時 log

這個 repo 在研究階段建議保持 private。

## 已驗證

2026-06-08 本地驗證通過：

- `sidecars/sienna_intersection_distance_sidecar.py` Python AST parse
- `tools/qlog_distance_replay.py` Python AST parse
- `scripts/start_intersection_distance_sidecar.sh` bash 語法檢查
- `restore/restore_tss25_on_boot.sh` bash 語法檢查
- `20260608.2`、`20260608.1`、`20260607.2` qlog replay baseline
- 合成 OSM 紅綠燈事件 replay，可產生 heading distance 與耗時表

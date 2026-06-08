# qlog Replay 結果 2026-06-08

## 目的

用 qlog 裡的 GPS、carState、longitudinalPlan，離線套用目前 GPS+OSM 路口距離邏輯，產出一張表。

表格重點欄位：

- `distance_m`
- `distance_mode`
- `distance_phase`
- `requested_decel_mps2`
- `distance_compute_ms`
- `v_kph`
- `plan_a_target`
- `plan_should_stop`
- `red_present`
- `signal_range`

## 本地依賴

Windows 上讀 qlog 需要額外依賴，安裝到 D:\Temp，不放 OneDrive：

```powershell
python -m pip install --target D:\Temp\qlog_pydeps_20260608 zstandard pycapnp
```

沒有完整 openpilot checkout 時，工具會使用：

`D:\Codex\.qlog_schema\cereal\log.capnp`

## 沒有 OSM event map 的基準測試

測試 qlog：

- `D:\Codex\commaai\20260608.2`
- `D:\Codex\commaai\20260608.1`
- `D:\Codex\commaai\20260607.2`

輸出：

`D:\Temp\c3x_osm_distance_20260608\qlog_distance_replay_baseline_no_map.csv`

這個 CSV 含 GPS 座標，不 commit。

row 數：

- `20260608.2`: 682
- `20260608.1`: 768
- `20260607.2`: 344
- 合計: 1794

沒有 OSM map 時的計算耗時：

| qlog | 平均 ms | P95 ms | P99 ms | 最大 ms |
|---|---:|---:|---:|---:|
| 20260608.2 | 0.5601 | 1.106 | 1.412 | 1.944 |
| 20260608.1 | 0.6877 | 1.255 | 1.651 | 2.453 |
| 20260607.2 | 0.7303 | 1.382 | 1.907 | 2.121 |

所有 row 都是 `osm_geojson_missing`，所以這只驗證 replay 流程與空地圖負載，不代表真實距離。

## 合成 OSM 紅綠燈測試

用 `20260608.2` 第一筆 GPS，在車頭前方約 120m 放一個合成 traffic signal。

結果：

- rows: 682
- 有 heading distance match 的 rows: 8
- 平均耗時: 0.4359 ms
- P95: 0.841 ms
- P99: 1.418 ms
- 最大: 1.602 ms

第一筆 match：

- 距離: 120.0 m
- 模式: `osm_geojson_heading`
- phase: `prepare_slow`
- 要求減速度: `0.45 m/s^2`
- 計算耗時: `0.59 ms`

這代表 replay 表格和距離耗時測量可用，但還不代表真實 OSM event 位置準確。


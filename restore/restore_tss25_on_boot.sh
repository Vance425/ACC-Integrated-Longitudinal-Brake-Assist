#!/usr/bin/env bash
set -u

OPENPILOT_DIR="/data/openpilot"
CUSTOM_DIR="/data/sienna_custom"
STAGE_SCRIPT="${CUSTOM_DIR}/tss25_fingerprint_stage.py"
PYTHON_BIN="/usr/local/venv/bin/python3"
SOFTWARE_PY="${OPENPILOT_DIR}/selfdrive/ui/sunnypilot/layouts/settings/software.py"
RUNTIME_PARAM_GUARD="${CUSTOM_DIR}/sienna_runtime_param_guard.sh"
RUNTIME_PARAM_GUARD_CONF="${CUSTOM_DIR}/tss3_lite_runtime_params.conf"

mkdir -p /data/params/d /cache/params "${CUSTOM_DIR}"
printf 1 > /data/params/d/DisableUpdates
printf 1 > /cache/params/DisableUpdates
rm -f /data/safe_staging/finalized/.overlay_consistent
rm -f /data/params/d/UpdaterState /cache/params/UpdaterState 2>/dev/null || true
"${OPENPILOT_DIR}/scripts/stop_updater.sh" >/dev/null 2>&1 || true

if [ -f "${STAGE_SCRIPT}" ] && [ -d "${OPENPILOT_DIR}" ]; then
  chmod +x "${STAGE_SCRIPT}" >/dev/null 2>&1 || true
  cd "${OPENPILOT_DIR}" && "${PYTHON_BIN}" "${STAGE_SCRIPT}" stage >/data/sienna_custom/last_tss25_restore.json 2>/data/sienna_custom/last_tss25_restore.err || true
fi

if [ -f "${SOFTWARE_PY}" ]; then
  "${PYTHON_BIN}" - "${SOFTWARE_PY}" <<'PY' >/dev/null 2>&1 || true
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8", errors="replace")
old = text

text = text.replace(
"""  def _on_disable_updates_toggled(self, enabled):
    dialog = ConfirmDialog(tr("System reboot required for changes to take effect. Reboot now?"), tr("Reboot"), callback=self._handle_reboot)
    gui_app.push_widget(dialog)
""",
"""  def _on_disable_updates_toggled(self, enabled):
    ui_state.params.put_bool("DisableUpdates", enabled)
    if enabled:
      os.system("/data/openpilot/scripts/stop_updater.sh >/dev/null 2>&1 || true")
    else:
      os.system("pkill -SIGUSR1 -f system.updated.updated >/dev/null 2>&1 || true")
""")

text = text.replace(
"""    show_advanced = ui_state.params.get_bool("ShowAdvancedControls")
    self.disable_updates_toggle.action_item.set_enabled(ui_state.is_offroad())
    self.disable_updates_toggle.set_visible(show_advanced)
""",
"""    self.disable_updates_toggle.action_item.set_enabled(ui_state.is_offroad())
    self.disable_updates_toggle.set_visible(True)
""")

if text != old:
  path.write_text(text, encoding="utf-8")
PY
fi

if [ -x /data/sienna_custom/restore_sienna_apis_on_boot.sh ]; then
  /data/sienna_custom/restore_sienna_apis_on_boot.sh || true
fi

restore_tss3_lite_planner() {
  local planner_py="${OPENPILOT_DIR}/selfdrive/controls/lib/longitudinal_planner.py"
  local restore_py="${CUSTOM_DIR}/longitudinal_planner_tss3_lite_restore.py"
  if [ ! -f "${restore_py}" ] || [ ! -f "${planner_py}" ]; then
    return 0
  fi
  if grep -q "apply_sienna_traffic_light_prepare_stop" "${planner_py}" 2>/dev/null &&
     grep -q "SiennaTss3LiteAssist" "${planner_py}" 2>/dev/null &&
     grep -q "SiennaTrafficSlowdownAssist" "${planner_py}" 2>/dev/null &&
     grep -q "target_signal_color" "${planner_py}" 2>/dev/null &&
     grep -q "SiennaNoSurgeHoldS" "${planner_py}" 2>/dev/null &&
     grep -q "SiennaTss3LiteOsmSpeedLimitCap" "${planner_py}" 2>/dev/null &&
     grep -q "available_sp_resolver" "${planner_py}" 2>/dev/null &&
     grep -q "gps_distance_phase" "${planner_py}" 2>/dev/null; then
    return 0
  fi
  if "${PYTHON_BIN}" -m py_compile "${restore_py}" >/dev/null 2>&1; then
    cp "${planner_py}" "${planner_py}.bak_restore_drift_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
    cp "${restore_py}" "${planner_py}"
    chmod 775 "${planner_py}" 2>/dev/null || true
  fi
}

restore_tss3_lite_planner

restore_sienna_brake_bar_ui() {
  local onroad_py="${OPENPILOT_DIR}/selfdrive/ui/onroad/augmented_road_view.py"
  local mici_py="${OPENPILOT_DIR}/selfdrive/ui/mici/onroad/augmented_road_view.py"
  local onroad_restore="${CUSTOM_DIR}/augmented_road_view_onroad_brakebar_restore.py"
  local mici_restore="${CUSTOM_DIR}/augmented_road_view_mici_brakebar_restore.py"

  if [ -f "${onroad_restore}" ] && [ -f "${onroad_py}" ] &&
     ! (grep -q "_draw_sienna_brake_bar_overlay" "${onroad_py}" 2>/dev/null &&
        grep -q "output_a_target" "${onroad_py}" 2>/dev/null &&
        grep -q "fill_w = max" "${onroad_py}" 2>/dev/null &&
        grep -q "_draw_sienna_intersection_status_overlay" "${onroad_py}" 2>/dev/null &&
        grep -q "rect.x + 122" "${onroad_py}" 2>/dev/null) &&
     "${PYTHON_BIN}" -m py_compile "${onroad_restore}" >/dev/null 2>&1; then
    cp "${onroad_py}" "${onroad_py}.bak_brake_bar_restore_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
    cp "${onroad_restore}" "${onroad_py}"
    chmod 775 "${onroad_py}" 2>/dev/null || true
  fi

  if [ -f "${mici_restore}" ] && [ -f "${mici_py}" ] &&
     ! (grep -q "_draw_sienna_brake_bar_overlay" "${mici_py}" 2>/dev/null &&
        grep -q "output_a_target" "${mici_py}" 2>/dev/null &&
        grep -q "fill_w = max" "${mici_py}" 2>/dev/null &&
        grep -q "_draw_sienna_intersection_status_overlay" "${mici_py}" 2>/dev/null &&
        grep -q "rect.x + 122" "${mici_py}" 2>/dev/null) &&
     "${PYTHON_BIN}" -m py_compile "${mici_restore}" >/dev/null 2>&1; then
    cp "${mici_py}" "${mici_py}.bak_brake_bar_restore_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
    cp "${mici_restore}" "${mici_py}"
    chmod 775 "${mici_py}" 2>/dev/null || true
  fi
}

restore_sienna_brake_bar_ui

restore_sienna_traffic_light_sidecar() {
  local sidecar_py="${OPENPILOT_DIR}/tools/sienna_tss25_plus/traffic_light_sidecar.py"
  local sidecar_restore="${CUSTOM_DIR}/traffic_light_sidecar_restore.py"
  if [ ! -f "${sidecar_restore}" ] || [ ! -f "${sidecar_py}" ]; then
    return 0
  fi
  if grep -q "camera_fallback_car_state_stale" "${sidecar_py}" 2>/dev/null &&
     grep -q "np.array(buf.data" "${sidecar_py}" 2>/dev/null &&
     grep -q "target_signal_range_source" "${sidecar_py}" 2>/dev/null &&
     grep -q "intersection_marking_type" "${sidecar_py}" 2>/dev/null &&
     grep -q "estimate_ego_lane_signal" "${sidecar_py}" 2>/dev/null &&
     grep -q "small_ego_red_candidate" "${sidecar_py}" 2>/dev/null &&
     grep -q "small_ego_red_min_pixels" "${sidecar_py}" 2>/dev/null; then
    return 0
  fi
  if "${PYTHON_BIN}" -m py_compile "${sidecar_restore}" >/dev/null 2>&1; then
    cp "${sidecar_py}" "${sidecar_py}.bak_sidecar_restore_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
    cp "${sidecar_restore}" "${sidecar_py}"
    chmod 775 "${sidecar_py}" 2>/dev/null || true
  fi
}

restore_sienna_traffic_light_sidecar

restore_sienna_traffic_light_watchdog() {
  local watchdog_py="${OPENPILOT_DIR}/tools/sienna_tss25_plus/traffic_light_watchdog.py"
  local watchdog_restore="${CUSTOM_DIR}/traffic_light_watchdog_restore.py"
  local watchdog_start="/data/tools/SiennaTSS25Plus_traffic_light/start_traffic_light_watchdog.sh"
  local need_restore=0
  if [ -f "${watchdog_restore}" ]; then
    if [ ! -f "${watchdog_py}" ]; then
      need_restore=1
    elif ! (grep -q "SiennaTrafficLightWatchdog" "${watchdog_py}" 2>/dev/null &&
            grep -q "consecutive_processing_error" "${watchdog_py}" 2>/dev/null &&
            grep -q "state_stale_while_moving" "${watchdog_py}" 2>/dev/null); then
      need_restore=1
    fi
    if [ "${need_restore}" = "1" ] &&
       "${PYTHON_BIN}" -m py_compile "${watchdog_restore}" >/dev/null 2>&1; then
      if [ -f "${watchdog_py}" ]; then
        cp "${watchdog_py}" "${watchdog_py}.bak_watchdog_restore_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
      fi
      mkdir -p "$(dirname "${watchdog_py}")"
      cp "${watchdog_restore}" "${watchdog_py}"
      chmod 775 "${watchdog_py}" 2>/dev/null || true
    fi
  fi
  if [ -f "${watchdog_start}" ]; then
    chmod +x "${watchdog_start}" 2>/dev/null || true
  fi
}

restore_sienna_traffic_light_watchdog

restore_sienna_intersection_distance_sidecar() {
  local sidecar_py="${OPENPILOT_DIR}/tools/sienna_tss25_plus/sienna_intersection_distance_sidecar.py"
  local sidecar_restore="${CUSTOM_DIR}/sienna_intersection_distance_sidecar_restore.py"
  local start_py="/data/tools/SiennaTSS25Plus_route_receiver/start_intersection_distance_sidecar.sh"
  local start_restore="${CUSTOM_DIR}/start_intersection_distance_sidecar_restore.sh"
  if [ -f "${sidecar_restore}" ]; then
    if [ ! -f "${sidecar_py}" ] || ! grep -q "intersection_distance_sidecar" "${sidecar_py}" 2>/dev/null; then
      if "${PYTHON_BIN}" -m py_compile "${sidecar_restore}" >/dev/null 2>&1; then
        if [ -f "${sidecar_py}" ]; then
          cp "${sidecar_py}" "${sidecar_py}.bak_intersection_distance_restore_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
        fi
        mkdir -p "$(dirname "${sidecar_py}")"
        cp "${sidecar_restore}" "${sidecar_py}"
        chmod +x "${sidecar_py}" 2>/dev/null || true
      fi
    fi
  fi
  if [ -f "${start_restore}" ]; then
    mkdir -p "$(dirname "${start_py}")"
    cp "${start_restore}" "${start_py}"
    chmod +x "${start_py}" 2>/dev/null || true
  fi
}

restore_sienna_intersection_distance_sidecar

write_sienna_runtime_param_guard_config() {
  mkdir -p "${CUSTOM_DIR}"
  cat > "${RUNTIME_PARAM_GUARD_CONF}" <<'EOF'
/data/params/d/ToyotaEnforceStockLongitudinal=0
/cache/params/ToyotaEnforceStockLongitudinal=0
ExperimentalMode=1
ExperimentalModeConfirmed=1
DynamicExperimentalControl=1
TaiwanStopApproachDebugOnUI=1
TaiwanStopApproachShadow=0
TaiwanStopApproachControl=0
SiennaTss3LiteShadow=1
SiennaTss3LiteAssist=1
SiennaTss3LiteMaxDecel=0.4
SiennaTss3LiteMinDistM=12.0
SiennaTss3LiteMaxDistM=120.0
SiennaTss3LiteMaxSpeedKph=60.0
SiennaTss3LiteCoastDecel=0.2
SiennaTss3LiteStopHold=1
SiennaTss3LiteStopHoldV=1.0
SiennaTss3LiteE2eStopAssist=1
SiennaTss3LiteE2eStopMinDistM=2.0
SiennaTss3LiteE2eStopMaxDistM=50.0
SiennaTss3LiteE2eStopMaxDecel=0.8
SiennaQlogDebug=1
SiennaQlogDebugLevel=error
SiennaTss3LiteOsmSpeedLimitCap=1
SiennaTss3LiteOsmSpeedLimitCapMinConfidence=0.70
SiennaTss3LiteOsmSpeedLimitCapOffsetKph=0
SiennaTss3LiteOsmSpeedLimitCapMaxDecel=0.6
SiennaTss3LiteOsmSpeedLimitCapHysteresisKph=1
SiennaIntersectionDistanceAssist=1
SiennaIntersectionDistancePeriodS=1.5
SiennaIntersectionDistanceMinSpeedKph=3.0
SiennaIntersectionDistanceMaxCrossTrackM=70.0
SiennaIntersectionDistanceLookaheadM=300.0
SiennaIntersectionDistanceMapRadiusM=350.0
SiennaIntersectionDistanceHeadingConeDeg=35.0
SiennaIntersectionDistanceMaxLateralM=55.0
SiennaIntersectionDistanceEventCrossTrackM=45.0
SiennaTrafficLightPrepareShadow=1
SiennaTrafficLightPrepareAssist=1
SiennaTrafficLightPrepareMinConfidence=0.55
SiennaTrafficLightPrepareTtlS=1.5
SiennaTrafficLightPrepareTargetKph=25.0
SiennaTrafficLightPrepareCoastDecel=0.25
SiennaTrafficLightPrepareMaxDecel=0.80
SiennaTrafficLightRangeControl=1
SiennaTrafficLightFirstRedCoast=1
SiennaTrafficLightEgoLaneGate=1
SiennaTrafficLightSmallEgoRedPrepare=1
SiennaTrafficLightSmallEgoRedMinPixels=6
SiennaTrafficLightSmallEgoRedMinConfidence=0.55
SiennaTrafficLightWatchdog=1
SiennaTrafficLightWatchdogPeriodS=3.0
SiennaTrafficLightWatchdogCooldownS=60.0
SiennaTrafficLightWatchdogMaxRestarts=5
SiennaTrafficLightWatchdogStaleS=5.0
SiennaTrafficLightWatchdogErrorLimit=3
SiennaTrafficLightWatchdogMinSpeedKph=3.0
SiennaTrafficLightFarTargetKph=48.0
SiennaTrafficLightFarCoastDecel=0.12
SiennaTrafficLightFarMaxDecel=0.35
SiennaTrafficLightMidTargetKph=30.0
SiennaTrafficLightMidBrakeMinKph=24.0
SiennaTrafficLightMidCoastDecel=0.35
SiennaTrafficLightMidMaxDecel=1.10
SiennaTrafficLightNearTargetKph=20.0
SiennaTrafficLightNearBrakeMinKph=12.0
SiennaTrafficLightNearCoastDecel=0.50
SiennaTrafficLightNearMaxDecel=1.50
SiennaTrafficLightPrepareGasOverrideS=4.0
SiennaTrafficLightPrepareGreenReleaseCount=35.0
SiennaTrafficLightPrepareGreenReleaseRedMax=2.0
SiennaTrafficLightPrepareUncertainS=12.0
SiennaTrafficLightGreenStableFrames=2
SiennaTrafficLightGpsDistanceAssist=1
SiennaTrafficLightGpsStartM=160.0
SiennaTrafficLightGpsSoftM=120.0
SiennaTrafficLightGpsBrakeM=80.0
SiennaTrafficLightGpsHardM=40.0
SiennaTrafficLightGpsLateM=20.0
SiennaTrafficLightGpsFarTargetKph=50.0
SiennaTrafficLightGpsSoftTargetKph=40.0
SiennaTrafficLightGpsBrakeTargetKph=30.0
SiennaTrafficLightGpsHardTargetKph=22.0
SiennaTrafficLightGpsFarMaxDecel=0.15
SiennaTrafficLightGpsSoftMaxDecel=0.45
SiennaTrafficLightGpsBrakeMaxDecel=0.90
SiennaTrafficLightGpsHardMaxDecel=1.30
SiennaNoSurgeHoldS=3.0
SiennaNoSurgeMaxAccelMps2=0.0
SiennaTrafficLightRedDetect=1
SiennaWhiteLineShadow=1
SiennaWhiteLineMaxSpeedKph=25.0
SiennaWhiteLineMinConfidence=0.55
SiennaIntersectionMarkingShadow=1
SiennaIntersectionMarkingMaxSpeedKph=35.0
SiennaBrakeBarOnUI=1
SiennaBrakeBarMaxDecel=2.0
SiennaIntersectionStatusOnUI=1
SiennaOsmSpeedAssist=0
SiennaOsmAssistMinConfidence=0.55
SiennaOsmAssistMaxDecel=0.8
SiennaOsmCoastStartDistanceM=700.0
SiennaOsmSoftBrakeStartDistanceM=180.0
SiennaOsmMaxSoftDecelMps2=0.4
LaneTurnDesire=0
SiennaRampCurveAssist=1
SiennaRampCurveShadow=1
SiennaRampCurveMinSpeedKph=35.0
SiennaRampCurveStartLatAccelMps2=1.15
SiennaRampCurveTargetLatAccelMps2=1.0
SiennaRampCurveMaxDecelMps2=0.5
SiennaRampCurveMaxSpeedDropKph=18.0
SiennaUrbanPostTurnAccelHold=0
SiennaUrbanPostTurnMaxAccelMps2=0.1
SiennaUrbanPostTurnHoldSeconds=5.0
SiennaUrbanPostTurnHoldDistanceM=60.0
SiennaTrafficSlowdownShadow=1
SiennaTrafficSlowdownAssist=1
SiennaTrafficSlowdownLookaheadM=160.0
SiennaTrafficSlowdownCoastStartM=100.0
SiennaTrafficSlowdownMinDRelM=8.0
SiennaTrafficSlowdownCoastAccelMps2=0.0
SiennaTrafficSlowdownMinVRelMps=-0.5
SiennaTrafficSlowdownMinClosingSpeedMps=0.5
SiennaTrafficSlowdownDynamicHeadwayS=2.0
SiennaTrafficSlowdownComfortDecelMps2=1.2
SiennaTrafficSlowdownStage=4
SiennaTrafficSlowdownMaxStage3DecelMps2=0.6
SiennaTrafficSlowdownMaxStage4DecelMps2=1.0
SiennaTrafficSlowdownStopDRelM=8.0
SiennaTrafficSlowdownStopVMps=2.0
SiennaTrafficSlowdownLeadStopVMps=0.5
EOF
}

start_sienna_runtime_param_guard() {
  if [ ! -x "${RUNTIME_PARAM_GUARD}" ]; then
    return 0
  fi
  rm -f "${CUSTOM_DIR}/sienna_runtime_param_guard.disabled" 2>/dev/null || true
  if pgrep -f "${RUNTIME_PARAM_GUARD}" >/dev/null 2>&1; then
    return 0
  fi
  nohup "${RUNTIME_PARAM_GUARD}" >/data/sienna_custom/sienna_runtime_param_guard.log 2>&1 &
}

restore_today_runtime_params() {
  local params_dir="/data/params/d"
  local cache_dir="/cache/params"
  mkdir -p "${params_dir}" "${cache_dir}" /data/sienna_route
  write_sienna_runtime_param_guard_config

  printf 0 > "${params_dir}/ToyotaEnforceStockLongitudinal"
  printf 0 > "${cache_dir}/ToyotaEnforceStockLongitudinal"
  printf 1 > "${params_dir}/ExperimentalMode"
  printf 1 > "${params_dir}/ExperimentalModeConfirmed"
  printf 1 > "${params_dir}/DynamicExperimentalControl"

  printf 1 > "${params_dir}/TaiwanStopApproachDebugOnUI"
  printf 0 > "${params_dir}/TaiwanStopApproachShadow"
  printf 0 > "${params_dir}/TaiwanStopApproachControl"

  printf 1 > "${params_dir}/SiennaTss3LiteShadow"
  printf 1 > "${params_dir}/SiennaTss3LiteAssist"
  printf 0.4 > "${params_dir}/SiennaTss3LiteMaxDecel"
  printf 12.0 > "${params_dir}/SiennaTss3LiteMinDistM"
  printf 120.0 > "${params_dir}/SiennaTss3LiteMaxDistM"
  printf 60.0 > "${params_dir}/SiennaTss3LiteMaxSpeedKph"
  printf 0.2 > "${params_dir}/SiennaTss3LiteCoastDecel"
  printf 1 > "${params_dir}/SiennaTss3LiteStopHold"
  printf 1.0 > "${params_dir}/SiennaTss3LiteStopHoldV"
  printf 1 > "${params_dir}/SiennaTss3LiteE2eStopAssist"
  printf 2.0 > "${params_dir}/SiennaTss3LiteE2eStopMinDistM"
  printf 50.0 > "${params_dir}/SiennaTss3LiteE2eStopMaxDistM"
  printf 0.8 > "${params_dir}/SiennaTss3LiteE2eStopMaxDecel"
  printf 1 > "${params_dir}/SiennaQlogDebug"
  printf error > "${params_dir}/SiennaQlogDebugLevel"
  printf 1 > "${params_dir}/SiennaTss3LiteOsmSpeedLimitCap"
  printf 0.70 > "${params_dir}/SiennaTss3LiteOsmSpeedLimitCapMinConfidence"
  printf 0 > "${params_dir}/SiennaTss3LiteOsmSpeedLimitCapOffsetKph"
  printf 0.6 > "${params_dir}/SiennaTss3LiteOsmSpeedLimitCapMaxDecel"
  printf 1 > "${params_dir}/SiennaTss3LiteOsmSpeedLimitCapHysteresisKph"
  printf 1 > "${params_dir}/SiennaIntersectionDistanceAssist"
  printf 1.5 > "${params_dir}/SiennaIntersectionDistancePeriodS"
  printf 3.0 > "${params_dir}/SiennaIntersectionDistanceMinSpeedKph"
  printf 70.0 > "${params_dir}/SiennaIntersectionDistanceMaxCrossTrackM"
  printf 300.0 > "${params_dir}/SiennaIntersectionDistanceLookaheadM"
  printf 350.0 > "${params_dir}/SiennaIntersectionDistanceMapRadiusM"
  printf 35.0 > "${params_dir}/SiennaIntersectionDistanceHeadingConeDeg"
  printf 55.0 > "${params_dir}/SiennaIntersectionDistanceMaxLateralM"
  printf 45.0 > "${params_dir}/SiennaIntersectionDistanceEventCrossTrackM"
  printf 1 > "${params_dir}/SiennaTrafficLightPrepareShadow"
  printf 1 > "${params_dir}/SiennaTrafficLightPrepareAssist"
  printf 0.55 > "${params_dir}/SiennaTrafficLightPrepareMinConfidence"
  printf 1.5 > "${params_dir}/SiennaTrafficLightPrepareTtlS"
  printf 25.0 > "${params_dir}/SiennaTrafficLightPrepareTargetKph"
  printf 0.25 > "${params_dir}/SiennaTrafficLightPrepareCoastDecel"
  printf 0.80 > "${params_dir}/SiennaTrafficLightPrepareMaxDecel"
  printf 1 > "${params_dir}/SiennaTrafficLightRangeControl"
  printf 1 > "${params_dir}/SiennaTrafficLightFirstRedCoast"
  printf 1 > "${params_dir}/SiennaTrafficLightEgoLaneGate"
  printf 1 > "${params_dir}/SiennaTrafficLightSmallEgoRedPrepare"
  printf 6 > "${params_dir}/SiennaTrafficLightSmallEgoRedMinPixels"
  printf 0.55 > "${params_dir}/SiennaTrafficLightSmallEgoRedMinConfidence"
  printf 1 > "${params_dir}/SiennaTrafficLightWatchdog"
  printf 3.0 > "${params_dir}/SiennaTrafficLightWatchdogPeriodS"
  printf 60.0 > "${params_dir}/SiennaTrafficLightWatchdogCooldownS"
  printf 5 > "${params_dir}/SiennaTrafficLightWatchdogMaxRestarts"
  printf 5.0 > "${params_dir}/SiennaTrafficLightWatchdogStaleS"
  printf 3 > "${params_dir}/SiennaTrafficLightWatchdogErrorLimit"
  printf 3.0 > "${params_dir}/SiennaTrafficLightWatchdogMinSpeedKph"
  printf 48.0 > "${params_dir}/SiennaTrafficLightFarTargetKph"
  printf 0.12 > "${params_dir}/SiennaTrafficLightFarCoastDecel"
  printf 0.35 > "${params_dir}/SiennaTrafficLightFarMaxDecel"
  printf 30.0 > "${params_dir}/SiennaTrafficLightMidTargetKph"
  printf 24.0 > "${params_dir}/SiennaTrafficLightMidBrakeMinKph"
  printf 0.35 > "${params_dir}/SiennaTrafficLightMidCoastDecel"
  printf 1.10 > "${params_dir}/SiennaTrafficLightMidMaxDecel"
  printf 20.0 > "${params_dir}/SiennaTrafficLightNearTargetKph"
  printf 12.0 > "${params_dir}/SiennaTrafficLightNearBrakeMinKph"
  printf 0.50 > "${params_dir}/SiennaTrafficLightNearCoastDecel"
  printf 1.50 > "${params_dir}/SiennaTrafficLightNearMaxDecel"
  printf 4.0 > "${params_dir}/SiennaTrafficLightPrepareGasOverrideS"
  printf 35.0 > "${params_dir}/SiennaTrafficLightPrepareGreenReleaseCount"
  printf 2.0 > "${params_dir}/SiennaTrafficLightPrepareGreenReleaseRedMax"
  printf 12.0 > "${params_dir}/SiennaTrafficLightPrepareUncertainS"
  printf 2 > "${params_dir}/SiennaTrafficLightGreenStableFrames"
  printf 1 > "${params_dir}/SiennaTrafficLightGpsDistanceAssist"
  printf 160.0 > "${params_dir}/SiennaTrafficLightGpsStartM"
  printf 120.0 > "${params_dir}/SiennaTrafficLightGpsSoftM"
  printf 80.0 > "${params_dir}/SiennaTrafficLightGpsBrakeM"
  printf 40.0 > "${params_dir}/SiennaTrafficLightGpsHardM"
  printf 20.0 > "${params_dir}/SiennaTrafficLightGpsLateM"
  printf 50.0 > "${params_dir}/SiennaTrafficLightGpsFarTargetKph"
  printf 40.0 > "${params_dir}/SiennaTrafficLightGpsSoftTargetKph"
  printf 30.0 > "${params_dir}/SiennaTrafficLightGpsBrakeTargetKph"
  printf 22.0 > "${params_dir}/SiennaTrafficLightGpsHardTargetKph"
  printf 0.15 > "${params_dir}/SiennaTrafficLightGpsFarMaxDecel"
  printf 0.45 > "${params_dir}/SiennaTrafficLightGpsSoftMaxDecel"
  printf 0.90 > "${params_dir}/SiennaTrafficLightGpsBrakeMaxDecel"
  printf 1.30 > "${params_dir}/SiennaTrafficLightGpsHardMaxDecel"
  printf 3.0 > "${params_dir}/SiennaNoSurgeHoldS"
  printf 0.0 > "${params_dir}/SiennaNoSurgeMaxAccelMps2"
  printf 1 > "${params_dir}/SiennaTrafficLightRedDetect"
  printf 1 > "${params_dir}/SiennaWhiteLineShadow"
  printf 25.0 > "${params_dir}/SiennaWhiteLineMaxSpeedKph"
  printf 0.55 > "${params_dir}/SiennaWhiteLineMinConfidence"
  printf 1 > "${params_dir}/SiennaIntersectionMarkingShadow"
  printf 35.0 > "${params_dir}/SiennaIntersectionMarkingMaxSpeedKph"
  printf 1 > "${params_dir}/SiennaBrakeBarOnUI"
  printf 2.0 > "${params_dir}/SiennaBrakeBarMaxDecel"
  printf 1 > "${params_dir}/SiennaIntersectionStatusOnUI"

  printf 0 > "${params_dir}/SiennaOsmSpeedAssist"
  printf 0.55 > "${params_dir}/SiennaOsmAssistMinConfidence"
  printf 0.8 > "${params_dir}/SiennaOsmAssistMaxDecel"
  printf 700.0 > "${params_dir}/SiennaOsmCoastStartDistanceM"
  printf 180.0 > "${params_dir}/SiennaOsmSoftBrakeStartDistanceM"
  printf 0.4 > "${params_dir}/SiennaOsmMaxSoftDecelMps2"

  printf 0 > "${params_dir}/LaneTurnDesire"
  printf 1 > "${params_dir}/SiennaRampCurveAssist"
  printf 1 > "${params_dir}/SiennaRampCurveShadow"
  printf 35.0 > "${params_dir}/SiennaRampCurveMinSpeedKph"
  printf 1.15 > "${params_dir}/SiennaRampCurveStartLatAccelMps2"
  printf 1.0 > "${params_dir}/SiennaRampCurveTargetLatAccelMps2"
  printf 0.5 > "${params_dir}/SiennaRampCurveMaxDecelMps2"
  printf 18.0 > "${params_dir}/SiennaRampCurveMaxSpeedDropKph"

  printf 0 > "${params_dir}/SiennaUrbanPostTurnAccelHold"
  printf 0.1 > "${params_dir}/SiennaUrbanPostTurnMaxAccelMps2"
  printf 5.0 > "${params_dir}/SiennaUrbanPostTurnHoldSeconds"
  printf 60.0 > "${params_dir}/SiennaUrbanPostTurnHoldDistanceM"

  printf 1 > "${params_dir}/SiennaTrafficSlowdownShadow"
  printf 1 > "${params_dir}/SiennaTrafficSlowdownAssist"
  printf 160.0 > "${params_dir}/SiennaTrafficSlowdownLookaheadM"
  printf 100.0 > "${params_dir}/SiennaTrafficSlowdownCoastStartM"
  printf 8.0 > "${params_dir}/SiennaTrafficSlowdownMinDRelM"
  printf 0.0 > "${params_dir}/SiennaTrafficSlowdownCoastAccelMps2"
  printf '%s' '-0.5' > "${params_dir}/SiennaTrafficSlowdownMinVRelMps"
  printf 0.5 > "${params_dir}/SiennaTrafficSlowdownMinClosingSpeedMps"
  printf 2.0 > "${params_dir}/SiennaTrafficSlowdownDynamicHeadwayS"
  printf 1.2 > "${params_dir}/SiennaTrafficSlowdownComfortDecelMps2"
  printf 4 > "${params_dir}/SiennaTrafficSlowdownStage"
  printf 0.6 > "${params_dir}/SiennaTrafficSlowdownMaxStage3DecelMps2"
  printf 1.0 > "${params_dir}/SiennaTrafficSlowdownMaxStage4DecelMps2"
  printf 8.0 > "${params_dir}/SiennaTrafficSlowdownStopDRelM"
  printf 2.0 > "${params_dir}/SiennaTrafficSlowdownStopVMps"
  printf 0.5 > "${params_dir}/SiennaTrafficSlowdownLeadStopVMps"

  printf '{"mode":"shadow","reason":"restored_waiting","stop_distance":0.0,"requested_decel":0.0}' > "${params_dir}/TaiwanStopApproachDebug"
  printf '{"mode":"tss3_lite_stage2a","reason":"restored_waiting","assist_enabled":true,"shadow_enabled":true,"applied":false,"phase":"waiting","stop_distance":0.0,"source":"none","plan_stop_distance":0.0,"e2e_stop_enabled":true}' > "${params_dir}/SiennaTss3LiteDebug"
  printf '{"reason":"restored_waiting","approach_distance_m":null,"target_speed_mps":null}' > "${params_dir}/SiennaOsmAssistDebug"
  printf '{"mode":"ramp_curve_speed_guard","reason":"restored_waiting","applied":false,"lat_accel":0.0,"target_speed_kph":0.0}' > "${params_dir}/SiennaRampCurveAssistDebug"
  printf '{"reason":"restored_waiting","hold_distance_m":0.0,"hold_elapsed_s":0.0}' > "${params_dir}/SiennaUrbanPostTurnDebug"
  printf '{"mode":"traffic_slowdown_stage4","reason":"restored_waiting","phase":"waiting","d_rel":0.0,"v_rel":0.0,"dynamic_n":0.0,"applied":false,"traffic_should_stop":false}' > "${params_dir}/SiennaTrafficSlowdownDebug"
  printf '{"red_present":false,"mixed_signal":false,"confidence":0.0,"updated_at_ms":0,"source":"restore_seed"}' > "${params_dir}/SiennaTrafficLightState"
  printf '{"schema":"sienna_intersection_distance_state_v1","status":"restored_waiting","updated_at_ms":0}' > "${params_dir}/SiennaIntersectionDistanceState"
  printf '{"status":"wait","reason":"restored_waiting","enabled":true,"sidecar_alive":false,"sidecar_pid":0,"state_reason":"restore_seed","state_age_s":null,"consecutive_errors":0,"restarts":0,"v_ego_kph":0.0,"updated_at_ms":0}' > "${params_dir}/SiennaTrafficLightWatchdogState"
  printf '{"mode":"traffic_light_red_present_prepare","reason":"restored_waiting","phase":"watch","assist_enabled":true,"shadow_enabled":true,"applied":false,"red_present":false,"mixed_signal":false,"confidence":0.0}' > "${params_dir}/SiennaTrafficLightPrepareDebug"
}

restore_today_runtime_params
start_sienna_runtime_param_guard


if [ -x /data/tools/SiennaTSS25Plus_route_receiver/start_route_receiver.sh ]; then
  /data/tools/SiennaTSS25Plus_route_receiver/start_route_receiver.sh >/dev/null 2>&1 || true
fi

if [ -x /data/tools/SiennaTSS25Plus_traffic_light/start_traffic_light_sidecar.sh ]; then
  /data/tools/SiennaTSS25Plus_traffic_light/start_traffic_light_sidecar.sh >/dev/null 2>&1 || true
fi

if [ -x /data/tools/SiennaTSS25Plus_traffic_light/start_traffic_light_watchdog.sh ]; then
  /data/tools/SiennaTSS25Plus_traffic_light/start_traffic_light_watchdog.sh >/dev/null 2>&1 || true
fi

if [ -f /data/tools/SiennaTSS25Plus_patch_api/start_patch_api.sh ]; then
  chmod +x /data/tools/SiennaTSS25Plus_patch_api/start_patch_api.sh /data/tools/SiennaTSS25Plus_patch_api/patch_api.py 2>/dev/null || true
  bash /data/tools/SiennaTSS25Plus_patch_api/start_patch_api.sh >/dev/null 2>&1 || true
fi

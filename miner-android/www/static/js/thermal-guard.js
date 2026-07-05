/**
 * Android-only: pause mining or shut down the local node when device temperature is high.
 */

import { fleetPlugin } from "./device-fleet.js";
import { isAndroidAppContext, whenCapacitorReady } from "./capacitor-ready.js";
import { stopLocalNode } from "./local-node.js";

const PAUSE_TEMP_KEY = "bloodstone-thermal-pause-c";
const SHUTDOWN_TEMP_KEY = "bloodstone-thermal-shutdown-c";
const THERMAL_GUARD_KEY = "bloodstone-thermal-guard-enabled";

const DEFAULT_PAUSE_TEMP_C = 42;
const DEFAULT_SHUTDOWN_TEMP_C = 48;
const THERMAL_STATUS_SEVERE = 3;
const THERMAL_STATUS_CRITICAL = 4;

let lastStatus = null;
let listenerHandle = null;
let onThermalAction = null;
let guardUiHooked = false;
let lastAction = "";

export function isThermalGuardEnabled() {
  if (!isAndroidAppContext()) return false;
  try {
    const raw = localStorage.getItem(THERMAL_GUARD_KEY);
    return raw !== "0";
  } catch (_) {
    return true;
  }
}

export function setThermalGuardEnabled(enabled) {
  if (!isAndroidAppContext()) return false;
  try {
    localStorage.setItem(THERMAL_GUARD_KEY, enabled ? "1" : "0");
  } catch (_) {
    return false;
  }
  updateThermalBanner(lastStatus);
  return true;
}

export function thermalPauseThresholdC() {
  try {
    const raw = Number(localStorage.getItem(PAUSE_TEMP_KEY));
    if (Number.isFinite(raw) && raw >= 35 && raw <= 55) return raw;
  } catch (_) {
    /* ignore */
  }
  return DEFAULT_PAUSE_TEMP_C;
}

export function thermalShutdownThresholdC() {
  try {
    const raw = Number(localStorage.getItem(SHUTDOWN_TEMP_KEY));
    if (Number.isFinite(raw) && raw >= 40 && raw <= 60) return raw;
  } catch (_) {
    /* ignore */
  }
  return DEFAULT_SHUTDOWN_TEMP_C;
}

export function setThermalThresholds({ pauseC, shutdownC } = {}) {
  try {
    if (Number.isFinite(pauseC)) {
      localStorage.setItem(PAUSE_TEMP_KEY, String(Math.round(pauseC)));
    }
    if (Number.isFinite(shutdownC)) {
      localStorage.setItem(SHUTDOWN_TEMP_KEY, String(Math.round(shutdownC)));
    }
  } catch (_) {
    return false;
  }
  updateThermalBanner(lastStatus);
  return true;
}

function thermalLabel(status) {
  const temp = Number(status?.batteryTempC);
  const thermal = Number(status?.thermalStatus);
  const parts = [];
  if (Number.isFinite(temp) && temp > 0) {
    parts.push(`${temp.toFixed(1)}°C battery`);
  }
  if (Number.isFinite(thermal) && thermal >= 0) {
    const names = ["none", "light", "moderate", "severe", "critical", "emergency", "shutdown"];
    parts.push(`thermal ${names[thermal] || thermal}`);
  }
  return parts.length ? parts.join(" · ") : "temperature unknown";
}

export function evaluateThermalAction(status = lastStatus) {
  if (!isAndroidAppContext() || !isThermalGuardEnabled() || !status) {
    return { level: "ok", reason: "" };
  }

  const pauseAt = thermalPauseThresholdC();
  const shutdownAt = thermalShutdownThresholdC();
  const temp = Number(status.batteryTempC);
  const thermal = Number(status.thermalStatus);

  if (Number.isFinite(thermal) && thermal >= THERMAL_STATUS_CRITICAL) {
    return {
      level: "shutdown",
      reason: `Device thermal status critical (${thermalLabel(status)})`,
    };
  }
  if (Number.isFinite(temp) && temp >= shutdownAt) {
    return {
      level: "shutdown",
      reason: `Battery temperature ${temp.toFixed(1)}°C ≥ shutdown ${shutdownAt}°C`,
    };
  }
  if (Number.isFinite(thermal) && thermal >= THERMAL_STATUS_SEVERE) {
    return {
      level: "pause",
      reason: `Device thermal status severe (${thermalLabel(status)})`,
    };
  }
  if (Number.isFinite(temp) && temp >= pauseAt) {
    return {
      level: "pause",
      reason: `Battery temperature ${temp.toFixed(1)}°C ≥ pause ${pauseAt}°C`,
    };
  }
  return { level: "ok", reason: "" };
}

export function updateThermalBanner(status = lastStatus) {
  const el = document.getElementById("android-thermal-banner");
  if (!el || !isAndroidAppContext()) return;

  lastStatus = status;
  if (!isThermalGuardEnabled()) {
    el.hidden = true;
    return;
  }

  const action = evaluateThermalAction(status);
  const tempLine = thermalLabel(status);
  const pauseAt = thermalPauseThresholdC();
  const shutdownAt = thermalShutdownThresholdC();

  const textEl = document.getElementById("android-thermal-banner-text");
  if (action.level === "shutdown") {
    if (textEl) {
      textEl.textContent = `Overheating — node shut down. ${action.reason}`;
    }
    el.classList.add("thermal-shutdown");
    el.classList.remove("thermal-pause", "thermal-ok");
    el.hidden = false;
    return;
  }
  if (action.level === "pause") {
    if (textEl) {
      textEl.textContent = `High temperature — mining paused. ${action.reason}`;
    }
    el.classList.add("thermal-pause");
    el.classList.remove("thermal-shutdown", "thermal-ok");
    el.hidden = false;
    return;
  }

  if (textEl) {
    textEl.textContent = tempLine !== "temperature unknown"
      ? `Thermal guard on (pause ${pauseAt}°C · shutdown ${shutdownAt}°C) — ${tempLine}`
      : `Thermal guard on (pause ${pauseAt}°C · shutdown ${shutdownAt}°C)`;
  }
  el.classList.add("thermal-ok");
  el.classList.remove("thermal-pause", "thermal-shutdown");
  el.hidden = tempLine === "temperature unknown";
}

async function fetchThermalStatus() {
  await whenCapacitorReady();
  const plugin = fleetPlugin();
  if (!plugin?.getPowerStatus) return null;
  try {
    return await plugin.getPowerStatus();
  } catch (_) {
    return null;
  }
}

export async function refreshThermalStatus() {
  const status = await fetchThermalStatus();
  if (status) lastStatus = status;
  updateThermalBanner(status);
  return status;
}

export function onThermalGuardAction(callback) {
  onThermalAction = callback;
}

export async function applyThermalGuard(status = lastStatus) {
  if (!isThermalGuardEnabled()) return "ok";
  const action = evaluateThermalAction(status);
  if (action.level === "ok") {
    lastAction = "";
    return "ok";
  }
  if (action.level === lastAction) return action.level;

  lastAction = action.level;
  if (action.level === "shutdown") {
    onThermalAction?.({ level: "shutdown", reason: action.reason, stopNode: true });
    await stopLocalNode({ foregroundOnly: false });
  } else if (action.level === "pause") {
    onThermalAction?.({ level: "pause", reason: action.reason, stopNode: false });
  }
  updateThermalBanner(status);
  return action.level;
}

function hookThermalGuardUi() {
  if (guardUiHooked || !isAndroidAppContext()) return;
  guardUiHooked = true;

  const panel = document.getElementById("android-thermal-panel");
  const enabled = document.getElementById("android-thermal-guard-enabled");
  const pauseInput = document.getElementById("android-thermal-pause-c");
  const shutdownInput = document.getElementById("android-thermal-shutdown-c");

  if (panel) panel.hidden = false;
  if (enabled) {
    enabled.checked = isThermalGuardEnabled();
    enabled.addEventListener("change", () => {
      setThermalGuardEnabled(enabled.checked);
    });
  }
  if (pauseInput) {
    pauseInput.value = String(thermalPauseThresholdC());
    pauseInput.addEventListener("change", () => {
      setThermalThresholds({
        pauseC: Number(pauseInput.value),
        shutdownC: Number(shutdownInput?.value),
      });
    });
  }
  if (shutdownInput) {
    shutdownInput.value = String(thermalShutdownThresholdC());
    shutdownInput.addEventListener("change", () => {
      setThermalThresholds({
        pauseC: Number(pauseInput?.value),
        shutdownC: Number(shutdownInput.value),
      });
    });
  }
}

export async function initThermalGuard() {
  if (!isAndroidAppContext()) return null;
  hookThermalGuardUi();
  const status = await refreshThermalStatus();
  const plugin = fleetPlugin();
  if (plugin?.addListener && !listenerHandle) {
    try {
      listenerHandle = await plugin.addListener("powerStateChanged", (next) => {
        lastStatus = next;
        updateThermalBanner(next);
        void applyThermalGuard(next);
      });
    } catch (_) {
      /* listener unavailable */
    }
  }
  await applyThermalGuard(status);
  return status;
}

export function cachedThermalStatus() {
  return lastStatus;
}
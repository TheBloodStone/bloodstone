/**
 * Android-only: mining is allowed only on external power and via the local node.
 * Users may bypass the power sensor when detection is wrong.
 */

import { fleetPlugin } from "./device-fleet.js";
import { isAndroidAppContext, whenCapacitorReady } from "./capacitor-ready.js";

const POWER_BYPASS_KEY = "bloodstone-android-power-bypass";
const POWER_RETRY_MS = 400;
const POWER_RETRY_ATTEMPTS = 12;

let lastStatus = null;
let listenerHandle = null;
let onChangeCallback = null;
let visibilityHooked = false;
let bypassUiHooked = false;

export function androidPowerMiningRequired() {
  return isAndroidAppContext();
}

export function isAndroidPowerBypassEnabled() {
  if (!androidPowerMiningRequired()) return false;
  try {
    return localStorage.getItem(POWER_BYPASS_KEY) === "1";
  } catch (_) {
    return false;
  }
}

export function setAndroidPowerBypassEnabled(enabled) {
  if (!androidPowerMiningRequired()) return false;
  try {
    localStorage.setItem(POWER_BYPASS_KEY, enabled ? "1" : "0");
  } catch (_) {
    return false;
  }
  updateAndroidPowerBanner(lastStatus);
  onChangeCallback?.(lastStatus);
  return true;
}

async function readNativePowerStatus() {
  const cap = await whenCapacitorReady();
  if (cap?.nativePromise) {
    try {
      const status = await cap.nativePromise("BloodstoneDevicePool", "getPowerStatus", {});
      if (status && typeof status === "object") {
        return status;
      }
    } catch (_) {
      /* fall through */
    }
  }
  const plugin = fleetPlugin();
  if (plugin?.getPowerStatus) {
    return plugin.getPowerStatus();
  }
  return null;
}

export async function fetchAndroidPowerStatus() {
  if (!androidPowerMiningRequired()) {
    return { allowed: true, charging: false, plugged: false, level: null };
  }

  for (let attempt = 0; attempt < POWER_RETRY_ATTEMPTS; attempt += 1) {
    try {
      const status = await readNativePowerStatus();
      if (status) {
        lastStatus = status;
        return status;
      }
    } catch (_) {
      /* retry */
    }
    await new Promise((resolve) => setTimeout(resolve, POWER_RETRY_MS));
  }

  return { allowed: true, charging: false, plugged: false, level: null, unknown: true };
}

async function resolvePowerPlugin() {
  const cap = await whenCapacitorReady();
  return cap?.Plugins?.BloodstoneDevicePool || fleetPlugin();
}

export function cachedAndroidPowerStatus() {
  return lastStatus;
}

export function isAndroidPowerMiningAllowed(status = lastStatus) {
  if (!androidPowerMiningRequired()) return true;
  if (isAndroidPowerBypassEnabled()) return true;
  if (!status || status.unknown) return true;
  return Boolean(status.allowed);
}

export function androidPowerBlockReason(status = lastStatus) {
  if (!androidPowerMiningRequired()) return "";
  if (isAndroidPowerBypassEnabled()) return "";
  if (!status || status.unknown) return "";
  if (isAndroidPowerMiningAllowed(status)) return "";
  return "Plug in to charge before mining — or bypass the power sensor below.";
}

function sensorPowerLabel(status = lastStatus) {
  if (!status || status.unknown) return "power status unknown";
  if (status.allowed) {
    const parts = [];
    if (status.plugged) {
      parts.push(
        status.plugType === "usb"
          ? "USB power"
          : status.plugType === "wireless"
            ? "wireless charge"
            : "AC power",
      );
    }
    if (status.charging) parts.push("charging");
    return parts.join(", ") || "external power";
  }
  const pct = status.levelPercent != null ? ` (${status.levelPercent}% battery)` : "";
  return `on battery${pct}`;
}

export function formatAndroidPowerLabel(status = lastStatus) {
  if (!androidPowerMiningRequired()) return "";
  if (isAndroidPowerBypassEnabled()) {
    const sensor = sensorPowerLabel(status);
    return `Power sensor bypassed — mining allowed (${sensor})`;
  }
  if (!status || status.unknown) {
    return "Checking power status…";
  }
  if (status.allowed) {
    const pct = status.levelPercent != null ? ` · ${status.levelPercent}%` : "";
    return `Power OK (${sensorPowerLabel(status)})${pct} — local node mining enabled`;
  }
  const pct = status.levelPercent != null ? ` (${status.levelPercent}% battery)` : "";
  return `On battery${pct} — plug in to mine, or bypass the power sensor below`;
}

export function updateAndroidPowerBanner(status = lastStatus) {
  const el = document.getElementById("android-power-banner");
  if (!el || !androidPowerMiningRequired()) return;
  const text = formatAndroidPowerLabel(status);
  if (!text) {
    el.hidden = true;
    return;
  }
  const textEl = document.getElementById("android-power-banner-text");
  if (textEl) {
    textEl.textContent = text;
  } else {
    el.textContent = text;
  }
  el.hidden = false;
  const bypassed = isAndroidPowerBypassEnabled();
  const blocked = Boolean(status) && !status.unknown && !status.allowed && !bypassed;
  el.classList.toggle("power-ok", Boolean(status?.allowed) || bypassed);
  el.classList.toggle("power-blocked", blocked);
  el.classList.toggle("power-pending", Boolean(status?.unknown) && !bypassed);
  el.classList.toggle("power-bypassed", bypassed);

  const bypassBtn = document.getElementById("android-power-bypass-btn");
  if (bypassBtn) {
    bypassBtn.hidden = bypassed || !blocked;
  }
}

function hookAndroidPowerBypassUi() {
  if (bypassUiHooked || !androidPowerMiningRequired()) return;
  bypassUiHooked = true;

  const wrap = document.getElementById("android-power-bypass-wrap");
  const checkbox = document.getElementById("android-power-bypass");
  const bypassBtn = document.getElementById("android-power-bypass-btn");

  if (wrap) wrap.hidden = false;
  if (checkbox) {
    checkbox.checked = isAndroidPowerBypassEnabled();
    checkbox.addEventListener("change", () => {
      setAndroidPowerBypassEnabled(checkbox.checked);
    });
  }
  if (bypassBtn) {
    bypassBtn.addEventListener("click", () => {
      setAndroidPowerBypassEnabled(true);
      if (checkbox) checkbox.checked = true;
    });
  }
}

export async function refreshAndroidPowerStatus() {
  const status = await fetchAndroidPowerStatus();
  updateAndroidPowerBanner(status);
  return status;
}

export function onAndroidPowerChange(callback) {
  onChangeCallback = callback;
}

function hookPowerVisibilityRefresh() {
  if (visibilityHooked || !androidPowerMiningRequired()) return;
  visibilityHooked = true;
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      void refreshAndroidPowerStatus().then((status) => onChangeCallback?.(status));
    }
  });
}

export async function initAndroidPowerGuard() {
  if (!androidPowerMiningRequired()) return null;
  hookAndroidPowerBypassUi();
  await whenCapacitorReady();
  const status = await refreshAndroidPowerStatus();
  const plugin = await resolvePowerPlugin();
  if (plugin?.addListener && !listenerHandle) {
    try {
      listenerHandle = await plugin.addListener("powerStateChanged", (next) => {
        lastStatus = next;
        updateAndroidPowerBanner(next);
        if (!isAndroidPowerBypassEnabled()) {
          onChangeCallback?.(next);
        }
      });
    } catch (_) {
      /* listener unavailable */
    }
  }
  hookPowerVisibilityRefresh();
  onChangeCallback?.(status);
  return status;
}
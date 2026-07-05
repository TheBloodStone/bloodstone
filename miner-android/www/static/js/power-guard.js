/**
 * Android-only: mining is allowed only on external power and via the local node.
 * Users may bypass the power sensor when detection is wrong.
 */

import { fleetPlugin } from "./device-fleet.js";
import { isAndroidAppContext, whenCapacitorReady } from "./capacitor-ready.js";

const POWER_BYPASS_KEY = "bloodstone-android-power-bypass";
const POWER_RETRY_MS = 350;
const POWER_RETRY_ATTEMPTS = 20;
const POWER_POLL_MS = 5000;
const NATIVE_CALL_TIMEOUT_MS = 2500;

let lastStatus = null;
let powerFetchState = "pending";
let listenerHandle = null;
let onChangeCallback = null;
let visibilityHooked = false;
let bypassUiHooked = false;
let backgroundPollTimer = null;

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

function withTimeout(promise, ms = NATIVE_CALL_TIMEOUT_MS) {
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      setTimeout(() => reject(new Error("power status timeout")), ms);
    }),
  ]);
}

async function readNativePowerStatus() {
  await whenCapacitorReady();

  const plugin = fleetPlugin();
  if (plugin?.getPowerStatus) {
    try {
      const status = await withTimeout(plugin.getPowerStatus());
      if (status && typeof status === "object") {
        return status;
      }
    } catch (_) {
      /* try legacy bridge next */
    }
  }

  const cap = window.Capacitor;
  if (cap?.nativePromise) {
    try {
      const status = await withTimeout(
        cap.nativePromise("BloodstoneDevicePool", "getPowerStatus", {}),
      );
      if (status && typeof status === "object") {
        return status;
      }
    } catch (_) {
      /* exhausted */
    }
  }

  return null;
}

function markPowerReady(status) {
  lastStatus = status;
  powerFetchState = "ready";
  stopBackgroundPowerPoll();
}

function markPowerUnknown() {
  powerFetchState = "unknown";
  lastStatus = { allowed: true, charging: false, plugged: false, level: null, unknown: true };
}

function startBackgroundPowerPoll() {
  if (backgroundPollTimer || powerFetchState === "ready") return;
  backgroundPollTimer = setInterval(() => {
    void refreshAndroidPowerStatus().then((status) => {
      if (status && !status.unknown) {
        onChangeCallback?.(status);
      }
    });
  }, POWER_POLL_MS);
}

function stopBackgroundPowerPoll() {
  if (!backgroundPollTimer) return;
  clearInterval(backgroundPollTimer);
  backgroundPollTimer = null;
}

export async function fetchAndroidPowerStatus() {
  if (!androidPowerMiningRequired()) {
    powerFetchState = "ready";
    return { allowed: true, charging: false, plugged: false, level: null };
  }

  powerFetchState = "pending";

  for (let attempt = 0; attempt < POWER_RETRY_ATTEMPTS; attempt += 1) {
    try {
      const status = await readNativePowerStatus();
      if (status) {
        markPowerReady(status);
        return status;
      }
    } catch (_) {
      /* retry */
    }
    await new Promise((resolve) => setTimeout(resolve, POWER_RETRY_MS));
  }

  markPowerUnknown();
  startBackgroundPowerPoll();
  return lastStatus;
}

async function resolvePowerPlugin() {
  await whenCapacitorReady();
  return window.Capacitor?.Plugins?.BloodstoneDevicePool || fleetPlugin();
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
  if (!status || status.unknown) return "power sensor unavailable";
  if (status.allowed) {
    const parts = [];
    if (status.plugged) {
      parts.push(
        status.plugType === "usb"
          ? "USB power"
          : status.plugType === "wireless"
            ? "wireless charge"
            : status.plugType === "ac"
              ? "AC power"
              : "external power",
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
  if (powerFetchState === "pending" && (!status || status.unknown)) {
    return "Checking power status…";
  }
  if (!status || status.unknown) {
    return "Power sensor unavailable — mining allowed. Plug in, or bypass below if stuck.";
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
  const pending = powerFetchState === "pending" && !bypassed;
  el.classList.toggle("power-ok", Boolean(status?.allowed) || bypassed || Boolean(status?.unknown));
  el.classList.toggle("power-blocked", blocked);
  el.classList.toggle("power-pending", pending);
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
  await whenCapacitorReady(12000);
  const status = await refreshAndroidPowerStatus();
  const plugin = await resolvePowerPlugin();
  if (plugin?.addListener && !listenerHandle) {
    try {
      listenerHandle = await plugin.addListener("powerStateChanged", (next) => {
        if (next && typeof next === "object") {
          markPowerReady(next);
        }
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
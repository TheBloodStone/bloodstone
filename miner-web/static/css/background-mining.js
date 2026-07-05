/**
 * Keep browser mining alive on mobile when the tab is backgrounded or the screen locks.
 * Uses Wake Lock, silent Web Audio, Media Session, visibility/resume hooks, and worker pings.
 */

let wakeLockHandle = null;
let silentAudio = null;
let visibilityBound = false;
let lifecycleBound = false;
let keepaliveTimer = null;
let throttleTimer = null;
let lastHashrateAt = 0;
let lastHashrateHps = 0;
let peakHashrateHps = 0;
let backgroundCallbacks = null;

function isNativeCapacitor() {
  try {
    return window.Capacitor?.isNativePlatform?.() === true;
  } catch (_) {
    return false;
  }
}

function isNativeAndroid() {
  try {
    return window.Capacitor?.getPlatform?.() === "android";
  } catch (_) {
    return false;
  }
}

export function isMobileWebBrowser() {
  if (isNativeCapacitor()) return false;
  return /android|iphone|ipad|ipod/i.test(navigator.userAgent || "");
}

async function requestNativeKeepAwake() {
  if (!isNativeAndroid()) return;
  const keepAwake = window.Capacitor?.Plugins?.KeepAwake;
  if (!keepAwake) return;
  try {
    await keepAwake.keepAwake();
  } catch (_) {
    /* plugin unavailable */
  }
}

async function releaseNativeKeepAwake() {
  if (!isNativeAndroid()) return;
  const keepAwake = window.Capacitor?.Plugins?.KeepAwake;
  if (!keepAwake) return;
  try {
    await keepAwake.allowSleep();
  } catch (_) {
    /* ignore */
  }
}

const BATTERY_EXEMPT_DEFER_KEY = "bloodstone-battery-exempt-deferred";

async function requestBatteryExemption({ force = false } = {}) {
  if (!isNativeAndroid()) return;
  const plugin = window.Capacitor?.Plugins?.BloodstoneDevicePool;
  if (!plugin?.requestBatteryExemption) return;
  try {
    const status = await plugin.isBatteryExempt?.();
    if (status?.exempt) return;
    if (!force) {
      try {
        if (localStorage.getItem(BATTERY_EXEMPT_DEFER_KEY) === "1") return;
      } catch (_) {
        /* ignore */
      }
      return;
    }
    await plugin.requestBatteryExemption();
  } catch (_) {
    /* user may dismiss system dialog */
  }
}

export function deferBatteryExemptionPrompt() {
  if (!isNativeAndroid()) return;
  try {
    localStorage.setItem(BATTERY_EXEMPT_DEFER_KEY, "1");
  } catch (_) {
    /* ignore */
  }
}

export async function openBatteryExemptionPrompt() {
  await requestBatteryExemption({ force: true });
}

async function requestWakeLock() {
  await requestNativeKeepAwake();
  if (!("wakeLock" in navigator)) return;
  try {
    if (wakeLockHandle) return;
    wakeLockHandle = await navigator.wakeLock.request("screen");
    wakeLockHandle.addEventListener("release", () => {
      wakeLockHandle = null;
    });
  } catch (_) {
    /* denied or unsupported while hidden */
  }
}

async function releaseWakeLock() {
  if (!wakeLockHandle) return;
  try {
    await wakeLockHandle.release();
  } catch (_) {
    /* ignore */
  }
  wakeLockHandle = null;
  await releaseNativeKeepAwake();
}

function startSilentAudio() {
  if (silentAudio) return;
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return;
  try {
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    gain.gain.value = 0.00001;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    void ctx.resume();
    silentAudio = { ctx, osc, gain };
  } catch (_) {
    /* autoplay policy */
  }
}

function stopSilentAudio() {
  if (!silentAudio) return;
  try {
    silentAudio.osc.stop();
    void silentAudio.ctx.close();
  } catch (_) {
    /* ignore */
  }
  silentAudio = null;
}

function updateMediaSession(active) {
  if (!("mediaSession" in navigator)) return;
  try {
    if (!active) {
      navigator.mediaSession.playbackState = "none";
      navigator.mediaSession.metadata = null;
      return;
    }
    navigator.mediaSession.metadata = new MediaMetadata({
      title: "Bloodstone Mining",
      artist: "Bloodstone Pool",
      album: "CPU miner active",
    });
    navigator.mediaSession.playbackState = "playing";
  } catch (_) {
    /* ignore */
  }
}

function setBackgroundBanner(visible, message = "") {
  const el = document.getElementById("background-mining-banner");
  if (!el) return;
  el.hidden = !visible;
  if (message) {
    const text = el.querySelector("[data-banner-text]");
    if (text) text.textContent = message;
  }
}

async function maybeNotifyThrottled() {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  try {
    const n = new Notification("Bloodstone mining slowed", {
      body: "Open the miner tab to restore full hashrate.",
      tag: "bloodstone-mining-throttle",
      renotify: true,
    });
    n.onclick = () => {
      window.focus();
      n.close();
    };
  } catch (_) {
    /* ignore */
  }
}

function checkThrottling() {
  if (!backgroundCallbacks?.isRunning?.()) return;
  if (!document.hidden) {
    setBackgroundBanner(false);
    return;
  }
  const staleMs = Date.now() - lastHashrateAt;
  const hps = lastHashrateHps;
  const peak = Math.max(peakHashrateHps, hps, 1);
  const ratio = hps / peak;
  if (staleMs > 45000 || ratio < 0.08) {
    setBackgroundBanner(
      true,
      "Tab in background — mining may be throttled. Keep this tab open or return to restore speed.",
    );
    void maybeNotifyThrottled();
    backgroundCallbacks?.onThrottled?.();
  }
}

function pingWorkers() {
  backgroundCallbacks?.pingWorkers?.();
}

function onVisibilityChange() {
  if (!backgroundCallbacks?.isRunning?.()) return;
  if (document.visibilityState === "visible") {
    void requestWakeLock();
    setBackgroundBanner(false);
    backgroundCallbacks?.onForeground?.();
  } else {
    void requestWakeLock();
    if (isNativeAndroid()) {
      setBackgroundBanner(
        true,
        "Mining in background — notification keeps CPU active. Screen stays on while the app is open.",
      );
    } else if (isMobileWebBrowser()) {
      setBackgroundBanner(
        true,
        "Mining in background — keep this tab open. Add to Home Screen for best results on iPhone.",
      );
    }
    backgroundCallbacks?.onBackground?.();
  }
}

function onPageResume() {
  if (!backgroundCallbacks?.isRunning?.()) return;
  void requestWakeLock();
  backgroundCallbacks?.onForeground?.();
}

function bindLifecycle() {
  if (visibilityBound) return;
  visibilityBound = true;
  document.addEventListener("visibilitychange", onVisibilityChange);
  window.addEventListener("focus", () => {
    if (backgroundCallbacks?.isRunning?.()) void requestWakeLock();
  });
  window.addEventListener("pageshow", onPageResume);
  if ("onresume" in document) {
    document.addEventListener("resume", onPageResume);
    lifecycleBound = true;
  }
}

function startKeepaliveTimers() {
  stopKeepaliveTimers();
  keepaliveTimer = setInterval(() => {
    if (!backgroundCallbacks?.isRunning?.()) return;
    if (document.hidden) pingWorkers();
  }, 12000);
  throttleTimer = setInterval(checkThrottling, 15000);
}

function stopKeepaliveTimers() {
  if (keepaliveTimer) clearInterval(keepaliveTimer);
  if (throttleTimer) clearInterval(throttleTimer);
  keepaliveTimer = null;
  throttleTimer = null;
}

async function requestNotificationPermission() {
  if (!isMobileWebBrowser() || !("Notification" in window)) return;
  if (Notification.permission !== "default") return;
  try {
    await Notification.requestPermission();
  } catch (_) {
    /* ignore */
  }
}

export function noteMiningHashrate(hps) {
  lastHashrateAt = Date.now();
  lastHashrateHps = hps;
  if (hps > peakHashrateHps) peakHashrateHps = hps;
}

export async function startBackgroundMining(callbacks = {}) {
  backgroundCallbacks = callbacks;
  peakHashrateHps = 0;
  lastHashrateAt = Date.now();
  lastHashrateHps = 0;
  bindLifecycle();
  await requestWakeLock();
  startSilentAudio();
  updateMediaSession(true);
  startKeepaliveTimers();
  void requestNotificationPermission();
  if (document.hidden) {
    onVisibilityChange();
  } else if (isNativeAndroid()) {
    setBackgroundBanner(
      true,
      "Screen keep-awake enabled — mining continues in background via notification.",
    );
    setTimeout(() => {
      if (!document.hidden) setBackgroundBanner(false);
    }, 8000);
  } else if (isMobileWebBrowser()) {
    setBackgroundBanner(
      true,
      "Background mining enabled — you can switch apps; keep this browser tab open.",
    );
    setTimeout(() => {
      if (!document.hidden) setBackgroundBanner(false);
    }, 8000);
  }
}

export async function stopBackgroundMining() {
  stopKeepaliveTimers();
  stopSilentAudio();
  await releaseWakeLock();
  await releaseNativeKeepAwake();
  updateMediaSession(false);
  setBackgroundBanner(false);
  backgroundCallbacks = null;
  peakHashrateHps = 0;
}
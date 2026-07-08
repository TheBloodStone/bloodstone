/** Wait for Capacitor native plugins in the Android WebView (remote URL load race). */

const CORE_PLUGINS = [
  "BloodstoneStratum",
  "BloodstoneDevicePool",
  "BloodstoneChainMesh",
  "BloodstoneLocalNode",
];

export function isAndroidAppContext() {
  if (document.body?.dataset?.androidApp === "1") return true;
  const params = new URLSearchParams(window.location.search);
  if (params.get("app") === "android") return true;
  try {
    if (window.Capacitor?.getPlatform?.() === "android") return true;
  } catch (_) {
    /* ignore */
  }
  return false;
}

/** True when UI is served from the APK/OTA bundle (https://localhost/...), not the live portal. */
export function isBundledMinerOrigin() {
  try {
    const host = String(window.location.hostname || "").toLowerCase();
    return host === "localhost" || host === "127.0.0.1" || host.endsWith(".localhost");
  } catch (_) {
    return false;
  }
}

/** Open the offline bundled miner — required for reliable native local-node plugins. */
export function openBundledMinerScreen(query = "") {
  const q = query || "?app=android";
  const suffix = q.startsWith("?") ? q : `?${q}`;
  window.location.href = `${window.location.protocol}//localhost/offline-mine.html${suffix}`;
}

export function hasNativeCapacitorBridge() {
  const cap = window.Capacitor;
  if (!cap) return false;
  if (typeof cap.nativePromise === "function") return true;
  return CORE_PLUGINS.some((name) => Boolean(cap.Plugins?.[name]));
}

function hasCapacitorPlugin(cap, name) {
  return Boolean(cap?.Plugins?.[name]);
}

function hasNativeBridge(cap) {
  return typeof cap?.nativePromise === "function";
}

function capacitorBridgeReady(cap) {
  if (!cap) return false;
  if (hasNativeBridge(cap)) return true;
  return CORE_PLUGINS.every((name) => hasCapacitorPlugin(cap, name));
}

export async function whenCapacitorReady(maxMs = 12000) {
  if (!isAndroidAppContext()) return window.Capacitor || null;
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    const cap = window.Capacitor;
    if (capacitorBridgeReady(cap)) {
      return cap;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return window.Capacitor || null;
}

/** Wait until BloodstoneStratum is registered (do not use WebSocket on Android before this). */
export async function whenStratumPluginReady(maxMs = 12000) {
  if (!isAndroidAppContext()) return null;
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    const cap = window.Capacitor;
    if (cap?.getPlatform?.() === "android" && hasCapacitorPlugin(cap, "BloodstoneStratum")) {
      return cap;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  return null;
}
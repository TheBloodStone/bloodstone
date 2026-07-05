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

function hasCapacitorPlugin(cap, name) {
  return Boolean(cap?.Plugins?.[name]);
}

function capacitorBridgeReady(cap) {
  if (!cap) return false;
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
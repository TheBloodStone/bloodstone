/** Wait for Capacitor native plugins in the Android WebView (remote URL load race). */

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

function capacitorBridgeReady(cap) {
  if (!cap) return false;
  if (typeof cap.nativePromise === "function") return true;
  return Boolean(
    cap?.Plugins?.BloodstoneStratum &&
      cap?.Plugins?.BloodstoneDevicePool &&
      cap?.Plugins?.BloodstoneChainMesh &&
      cap?.Plugins?.BloodstoneLocalNode,
  );
}

export async function whenCapacitorReady(maxMs = 8000) {
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
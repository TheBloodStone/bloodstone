/** Decentralized VPS device pool — Capacitor Android fleet node helpers. */

import { isAndroidAppContext } from "./capacitor-ready.js";

export const FLEET_ROLE = "decentralized-vps-node";

let fleetIdentity = null;
let lastNodeStatus = null;

function nodeIsSyncing(status) {
  if (!status || (status.running && status.mode === "gateway")) return false;
  const local = Number(status?.blockHeight) || 0;
  const network = Number(status?.networkBlockHeight) || 0;
  if (network > 0 && local > 0 && network - local > 20) return true;
  const progress = Number(status?.syncProgress);
  if (!Number.isFinite(progress) || progress < 0) {
    return Boolean(status.running && status.mode === "full" && status.bloodstonedAlive !== false);
  }
  return progress < 0.999;
}

export function setFleetNodeStatus(status) {
  lastNodeStatus = status || null;
}

export function isCapacitorAndroid() {
  try {
    if (window.Capacitor?.getPlatform?.() === "android") return true;
    // Remote portal inside the APK WebView still has native plugins via nativePromise.
    if (
      isAndroidAppContext()
      && typeof window.Capacitor?.nativePromise === "function"
    ) {
      return true;
    }
  } catch (_) {
    return false;
  }
  return false;
}

export function fleetPlugin() {
  return window.Capacitor?.Plugins?.BloodstoneDevicePool || null;
}

export async function loadFleetIdentity() {
  if (fleetIdentity) return fleetIdentity;
  const plugin = fleetPlugin();
  if (!plugin) return null;
  try {
    fleetIdentity = await plugin.getIdentity();
    return fleetIdentity;
  } catch (_) {
    return null;
  }
}

export function fleetDeviceId() {
  return fleetIdentity?.deviceId || "";
}

export function fleetDeviceModel() {
  return fleetIdentity?.model || "";
}

export async function startFleetNode(meta = {}) {
  const plugin = fleetPlugin();
  if (plugin) {
    try {
      await plugin.startFleetNode({
        address: meta.address || "",
        algo: meta.algo || "",
      });
    } catch (_) {
      /* notification permission may be denied on older Android */
    }
  }
  const keepAwake = window.Capacitor?.Plugins?.KeepAwake;
  if (keepAwake) {
    try {
      await keepAwake.keepAwake();
    } catch (_) {
      /* ignore */
    }
  }
}

export async function stopFleetNode() {
  const plugin = fleetPlugin();
  if (plugin) {
    try {
      await plugin.stopFleetNode();
    } catch (_) {
      /* ignore */
    }
  }
  const keepAwake = window.Capacitor?.Plugins?.KeepAwake;
  if (keepAwake) {
    try {
      await keepAwake.allowSleep();
    } catch (_) {
      /* ignore */
    }
  }
}

export function transportKind(stratumTransport) {
  if (!stratumTransport) return "unknown";
  return stratumTransport.kind === "native-tcp" ? "native-tcp" : "websocket";
}

function updateLocalVpsLine() {
  const line = document.getElementById("local-vps-line");
  if (!line) return;
  let meta = null;
  try {
    const raw = localStorage.getItem("bloodstone-chain-mesh-meta");
    meta = raw ? JSON.parse(raw) : null;
  } catch (_) {
    meta = null;
  }
  const chunksEl = document.getElementById("local-vps-chunks");
  const offlineEl = document.getElementById("local-vps-offline");
  if (!meta?.chunks_held) {
    line.hidden = true;
    return;
  }
  line.hidden = false;
  if (chunksEl) chunksEl.textContent = String(meta.chunks_held);
  if (offlineEl) {
    offlineEl.textContent = meta.offline_capable
      ? "offline mining ready"
      : "sync with VPS to enable offline mining";
  }
}

function readNodeModePreference() {
  try {
    const raw = localStorage.getItem("bloodstone-local-node-mode");
    if (
    raw === "full"
    || raw === "mesh"
    || raw === "pruned"
    || raw === "consensus"
    || raw === "consensus-witness"
  ) return raw;
  } catch (_) {
    /* ignore */
  }
  return "pruned";
}

export function updateFleetPanel({
  identity,
  transport,
  fleetStats,
  mining,
  networkNodes,
}) {
  updateLocalVpsLine();
  const panel = document.getElementById("device-fleet-panel");
  if (!panel) return;

  const isOffload =
    isCapacitorAndroid() && transport === "native-tcp";
  const inApp = isAndroidAppContext() || isCapacitorAndroid();
  panel.hidden = !inApp && !isOffload && !identity?.deviceId;

  const roleEl = document.getElementById("fleet-role");
  const deviceEl = document.getElementById("fleet-device-id");
  const transportEl = document.getElementById("fleet-transport");
  const poolEl = document.getElementById("fleet-pool-size");
  const statusEl = document.getElementById("fleet-status");

  if (roleEl) {
    if (inApp) {
      const mode = readNodeModePreference();
      if (isOffload) {
        roleEl.textContent = "Decentralized VPS pool node";
      } else if (mode === "full") {
        roleEl.textContent = "Full chain node on this device";
      } else if (mode === "mesh") {
        roleEl.textContent = "Mesh federation node";
      } else {
        roleEl.textContent = "Local VPS chain node";
      }
    } else {
      roleEl.textContent = isOffload
        ? "Decentralized VPS pool node"
        : "Browser bridge (uses VPS WebSocket)";
    }
  }
  if (deviceEl && identity?.deviceId) {
    const short = `${identity.deviceId.slice(0, 8)}…`;
    const model = identity.model ? ` · ${identity.model}` : "";
    deviceEl.textContent = `${short}${model}`;
  }
  if (transportEl) {
    if (inApp) {
      transportEl.textContent =
        transport === "native-tcp"
          ? readNodeModePreference() === "lan-client"
            ? "Direct stratum TCP (LAN full node)"
            : "Direct stratum TCP (local node)"
          : "Capacitor app — LAN discovery + native plugins";
    } else {
      transportEl.textContent =
        transport === "native-tcp"
          ? "Direct stratum TCP (VPS bridge bypassed)"
          : "WebSocket via VPS";
    }
  }
  if (poolEl && fleetStats) {
    poolEl.textContent = `${fleetStats.offload_nodes || 0} offload nodes · ${fleetStats.active_devices || 0} active devices`;
  }
  const fleetNetworkEl = document.getElementById("fleet-network-nodes");
  if (fleetNetworkEl && networkNodes?.total_connected != null) {
    const total = Number(networkNodes.total_connected) || 0;
    fleetNetworkEl.textContent = `${total} network node${total === 1 ? "" : "s"} connected`;
  }
  if (statusEl) {
    if (mining) {
      statusEl.textContent = "Contributing hashrate to the shared pool";
    } else if (inApp && lastNodeStatus) {
      const mode = readNodeModePreference();
      if (mode === "lan-client") {
        statusEl.textContent = "LAN client — searching Wi‑Fi for full node host";
      } else if (lastNodeStatus.batteryDormant && !lastNodeStatus.running) {
        statusEl.textContent =
          mode === "full"
            ? "Full node dormant — tap Start full node"
            : "Node dormant — tap Start node";
      } else if (lastNodeStatus.running && nodeIsSyncing(lastNodeStatus)) {
        const raw = Number(lastNodeStatus.syncProgress);
        const local = Number(lastNodeStatus.blockHeight) || 0;
        const network = Number(lastNodeStatus.networkBlockHeight) || 0;
        let pct = Number.isFinite(raw) && raw > 0 ? Math.round(raw * 100) : null;
        if (pct == null && local > 0 && network > local) {
          pct = Math.max(1, Math.min(99, Math.round((local / network) * 100)));
        }
        statusEl.textContent = pct != null
          ? `Chain download ${pct}% — pool mines on VPS meanwhile`
          : "Chain download in progress — pool mines on VPS meanwhile";
      } else if (lastNodeStatus.running) {
        statusEl.textContent =
          mode === "full"
            ? "Full node active — mining optional"
            : "Local node active — mining optional";
      } else {
        statusEl.textContent = "Starting local node…";
      }
    } else {
      statusEl.textContent = "Idle";
    }
  }
}

export async function refreshFleetStats(apiUrl) {
  try {
    const res = await fetch(apiUrl("/api/pool/device-fleet"));
    if (!res.ok) return null;
    return await res.json();
  } catch (_) {
    return null;
  }
}
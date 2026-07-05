/** Local VPS node — Android Capacitor + LAN peer discovery (pruned, full, or mesh). */

import { apiUrl } from "./miner-paths.js";
import { isCapacitorAndroid } from "./device-fleet.js";
import { isAndroidAppContext, whenCapacitorReady } from "./capacitor-ready.js";

const NODE_MODE_KEY = "bloodstone-local-node-mode";
const DEFAULT_PRUNE_MIB = 550;

let nearbyCache = null;
let nearbyFetchedAt = 0;
const NEARBY_TTL_MS = 45000;

const LOCAL_STRATUM_PORTS = {
  neoscrypt: 3437,
  yespower: 3438,
  rod_neoscrypt: 3440,
};

export const NODE_MODES = {
  LAN_CLIENT: "lan-client",
  PRUNED: "pruned",
  FULL: "full",
  MESH: "mesh",
};

let discoveredLanPeersCache = [];
let activeLanPeer = null;
let lanDiscoveryTimer = null;

export function localNodePlugin() {
  try {
    return window.Capacitor?.Plugins?.BloodstoneLocalNode || null;
  } catch (_) {
    return null;
  }
}

export function getNodeModePreference() {
  try {
    const raw = localStorage.getItem(NODE_MODE_KEY);
    if (
      raw === NODE_MODES.FULL
      || raw === NODE_MODES.MESH
      || raw === NODE_MODES.PRUNED
      || raw === NODE_MODES.LAN_CLIENT
    ) {
      return raw;
    }
  } catch (_) {
    /* ignore */
  }
  return isCapacitorAndroid() || isAndroidAppContext()
    ? NODE_MODES.LAN_CLIENT
    : NODE_MODES.PRUNED;
}

export function setNodeModePreference(mode) {
  const normalized =
    mode === NODE_MODES.FULL
    || mode === NODE_MODES.MESH
    || mode === NODE_MODES.LAN_CLIENT
      ? mode
      : NODE_MODES.PRUNED;
  try {
    localStorage.setItem(NODE_MODE_KEY, normalized);
  } catch (_) {
    /* ignore */
  }
  return normalized;
}

export function shouldHostLocalNode(mode = getNodeModePreference()) {
  return mode === NODE_MODES.FULL
    || mode === NODE_MODES.MESH
    || mode === NODE_MODES.PRUNED;
}

export function isLanClientMode(mode = getNodeModePreference()) {
  return mode === NODE_MODES.LAN_CLIENT;
}

export function getActiveLanPeer() {
  return activeLanPeer;
}

export function setActiveLanPeer(peer) {
  activeLanPeer = peer || null;
}

export async function getNodeStorageInfo() {
  const plugin = localNodePlugin();
  if (!plugin?.getNodeStorageInfo) return null;
  try {
    return await plugin.getNodeStorageInfo();
  } catch (_) {
    return null;
  }
}

export async function resolvePreferredNodeOptions(overrides = {}) {
  const nodeMode = overrides.nodeMode || getNodeModePreference();
  const storage = await getNodeStorageInfo();
  return {
    nodeMode,
    pruneMiB: overrides.pruneMiB || DEFAULT_PRUNE_MIB,
    storage,
    storageWarning:
      nodeMode === NODE_MODES.FULL && storage && !storage.canRunFullNode
        ? "low_storage"
        : null,
  };
}

export async function startLocalNode(options = {}) {
  const plugin = localNodePlugin();
  if (!plugin) return null;
  try {
    const preferred = await resolvePreferredNodeOptions(options);
    const upstreamUrl = options.upstreamUrl || apiUrl("/api/local-node/rpc");
    const foreground =
      options.foreground === true || preferred.nodeMode === NODE_MODES.FULL;
    const result = await plugin.startLocalNode({
      upstreamUrl,
      pruneMiB: preferred.pruneMiB,
      nodeMode: preferred.nodeMode,
      foreground,
    });
    const waitMs = options.waitForStratumMs;
    if (waitMs === 0) return result || (await getLocalNodeStatus());
    return await waitForLocalNodeStratum(
      waitMs ?? (foreground ? 8000 : 2000),
    );
  } catch (_) {
    return null;
  }
}

/** Keep full-node foreground service alive when user chose full chain mode. */
export async function ensureFullNodeForeground() {
  if (getNodeModePreference() !== NODE_MODES.FULL) return null;
  const status = await getLocalNodeStatus();
  if (localStratumAvailable(status)) return status;
  return startLocalNode({
    nodeMode: NODE_MODES.FULL,
    foreground: true,
    waitForStratumMs: 0,
  });
}

export async function stopLocalNode(options = {}) {
  const plugin = localNodePlugin();
  if (!plugin) return;
  try {
    await plugin.stopLocalNode({
      foregroundOnly: options.foregroundOnly !== false,
    });
  } catch (_) {
    /* ignore */
  }
}

export async function getLocalNodeStatus() {
  const plugin = localNodePlugin();
  if (!plugin) return null;
  try {
    return await plugin.getLocalNodeStatus();
  } catch (_) {
    return null;
  }
}

export async function registerLanOnNetwork() {
  const plugin = localNodePlugin();
  if (!plugin?.registerLan) {
    throw new Error("LAN registration is only available in the Bloodstone miner app");
  }
  const result = await plugin.registerLan();
  if (!result?.ok) {
    const httpCode = result?.httpCode;
    const serverErr = result?.response?.error || result?.responseText;
    const detail = [
      result?.error,
      serverErr,
      httpCode ? `HTTP ${httpCode}` : null,
    ].filter(Boolean).join(" · ");
    throw new Error(detail || "LAN registration failed");
  }
  return result;
}

/** Host nodes push LAN endpoints to the pool registry (also runs every 60s natively). */
export async function ensureLanRegistration() {
  if (!isCapacitorAndroid() || isLanClientMode()) return null;
  try {
    return await registerLanOnNetwork();
  } catch (err) {
    console.warn("LAN register:", err?.message || err);
    return null;
  }
}

export async function discoverMdnsLanNodes() {
  const plugin = localNodePlugin();
  if (!plugin?.discoverLanPeers) return [];
  try {
    const result = await plugin.discoverLanPeers();
    return Array.isArray(result?.nodes) ? result.nodes : [];
  } catch (_) {
    return [];
  }
}

export async function fetchNearbyLanNodes() {
  if (Date.now() - nearbyFetchedAt < NEARBY_TTL_MS && nearbyCache) {
    return nearbyCache;
  }
  try {
    const res = await fetch(apiUrl("/api/local-node/nearby"));
    if (!res.ok) return [];
    const data = await res.json();
    nearbyCache = data.nodes || [];
    nearbyFetchedAt = Date.now();
    return nearbyCache;
  } catch (_) {
    return [];
  }
}

function localStratumPort(status, poolKey) {
  const ports = status?.stratumPorts || {};
  if (poolKey === "yespower") {
    return Number(ports.yespower || status.stratumPortYespower || LOCAL_STRATUM_PORTS.yespower);
  }
  if (poolKey === "rod_neoscrypt") {
    return Number(ports.rod_neoscrypt || LOCAL_STRATUM_PORTS.rod_neoscrypt);
  }
  return Number(ports.neoscrypt || status.stratumPort || LOCAL_STRATUM_PORTS.neoscrypt);
}

function nearbyStratumPort(node, poolKey) {
  if (poolKey === "yespower") {
    return Number(node.stratum_port_yespower || node.stratum_port || LOCAL_STRATUM_PORTS.yespower);
  }
  return Number(node.stratum_port || LOCAL_STRATUM_PORTS.neoscrypt);
}

function nodePriority(node) {
  if (!node) return 0;
  const mode = String(node.mode || "").toLowerCase();
  const pruned = Boolean(node.pruned);
  const sync = Number(node.sync_progress ?? node.syncProgress);
  let score = 10;
  if (mode === "full" && !pruned) score = 100;
  else if (mode === "mesh") score = 60;
  else if (mode === "pruned") score = 40;
  if (Number.isFinite(sync) && sync >= 0.999) score += 5;
  return score;
}

function isFullNodePeer(node) {
  if (!node) return false;
  const mode = String(node.mode || "").toLowerCase();
  return mode === "full" && !node.pruned;
}

function peerMatchesFilter(node, options = {}) {
  if (!node) return false;
  if (options.fullOnly && !isFullNodePeer(node)) return false;
  if (options.minSync != null) {
    const sync = Number(node.sync_progress ?? node.syncProgress);
    if (Number.isFinite(sync) && sync < options.minSync) return false;
  }
  return true;
}

export function localStratumAvailable(status) {
  if (!status?.running) return false;
  if (isCapacitorAndroid()) return true;
  return Boolean(status.stratumHost || status.lanIp);
}

export async function waitForLocalNodeStratum(maxWaitMs = 8000) {
  if (!isCapacitorAndroid()) return null;
  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    const status = await getLocalNodeStatus();
    if (localStratumAvailable(status)) {
      return status;
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  return null;
}

export async function listDiscoveredLanPeers(options = {}) {
  const mdnsNodes = isCapacitorAndroid() ? await discoverMdnsLanNodes() : [];
  const nearby = await fetchNearbyLanNodes();
  const seen = new Set();
  const merged = [];
  for (const node of [...mdnsNodes, ...nearby]) {
    const ip = node.lan_ip || node.host;
    if (!ip) continue;
    const key = `${ip}:${node.stratum_port || node.stratum_port_yespower || 0}`;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(node);
  }
  const filtered = merged.filter((n) => peerMatchesFilter(n, options));
  filtered.sort((a, b) => nodePriority(b) - nodePriority(a));
  discoveredLanPeersCache = filtered;
  return filtered;
}

export async function resolveLanStratumEndpoint(poolKey, options = {}) {
  const localOnly = options.localOnly === true;
  const skipLocal = options.skipLocal === true || isLanClientMode();
  if (isCapacitorAndroid() && !skipLocal) {
    const status = await getLocalNodeStatus();
    if (localStratumAvailable(status) && shouldHostLocalNode(getNodeModePreference())) {
      return {
        host: "127.0.0.1",
        port: localStratumPort(status, poolKey),
        source: "local-node",
        displayHost: status.stratumHost || status.lanIp || "127.0.0.1",
        mode: status.mode,
        algo: poolKey,
      };
    }
    if (localOnly) {
      return null;
    }
  }
  if (localOnly) {
    return null;
  }

  const selfStatus = isCapacitorAndroid() ? await getLocalNodeStatus() : null;
  const ownLan = selfStatus?.lanIp || "";

  const peers = await listDiscoveredLanPeers(options);
  const node = peers[0];
  if (node) {
    const lanIp = node.lan_ip || node.host;
    const sameDevice = ownLan && lanIp === ownLan;
    const endpoint = {
      host: sameDevice ? "127.0.0.1" : lanIp,
      port: nearbyStratumPort(node, poolKey),
      source: sameDevice ? "local-node" : (node.source === "mdns" ? "mdns" : "lan-peer"),
      displayHost: lanIp,
      rpcUser: node.rpc_user,
      mode: node.mode,
      algo: poolKey,
      deviceId: node.device_id,
      blockHeight: node.block_height,
      syncProgress: node.sync_progress ?? node.syncProgress,
    };
    setActiveLanPeer(endpoint);
    return endpoint;
  }
  setActiveLanPeer(null);
  return null;
}

function formatBytes(bytes) {
  const n = Number(bytes || 0);
  if (n >= 1024 * 1024 * 1024) return `${(n / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(0)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${n} B`;
}

function syncProgressRatio(status) {
  const raw = Number(status?.syncProgress);
  if (!Number.isFinite(raw) || raw < 0) return null;
  return Math.max(0, Math.min(1, raw));
}

async function fetchNetworkBlockHeightFromUpstream() {
  try {
    const res = await fetch(apiUrl("/api/local-node/rpc"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "1.0",
        id: "net-height",
        method: "getblockcount",
        params: [],
      }),
    });
    if (!res.ok) return 0;
    const data = await res.json();
    return Number(data?.result) || 0;
  } catch (_) {
    return 0;
  }
}

function estimateSyncProgress(status) {
  const reported = syncProgressRatio(status);
  const local = Number(status?.blockHeight) || 0;
  const network = Number(status?.networkBlockHeight) || 0;
  if (reported != null && reported > 0.01 && reported < 0.999) return reported;
  if (local > 0 && network > local) {
    return Math.max(0.01, Math.min(0.99, local / network));
  }
  if (status?.running && reported != null && reported < 0.999) return reported;
  return reported;
}

export function isNodeSyncing(status) {
  if (!status) return false;
  if (status.mode === "gateway" && status.running) return false;
  const progress = estimateSyncProgress(status);
  const local = Number(status?.blockHeight) || 0;
  const network = Number(status?.networkBlockHeight) || 0;
  if (network > 0 && local > 0 && network - local > 20) return true;
  if (progress == null) {
    return Boolean(
      status.running
        && (status.mode === NODE_MODES.FULL || status.mode === NODE_MODES.MESH)
        && status.bloodstonedAlive !== false,
    );
  }
  if (progress < 0.999) return true;
  return network > 0 && local > 0 && network - local > 20;
}

export function isLocalNodeStratumReady(status) {
  return localStratumAvailable(status);
}

/** Stratum routing for Android — LAN full node first, local host, then VPS. */
export async function resolveAndroidStratumOptions(miningMode = "pool", poolKey = "yespower") {
  if (!isAndroidAppContext()) return {};
  const nodeMode = getNodeModePreference();
  const status = await getLocalNodeStatus();
  const syncing = isNodeSyncing(status);
  const hosting = shouldHostLocalNode(nodeMode);
  const ready = hosting && isLocalNodeStratumReady(status);
  const poolMode = miningMode !== "solo";

  if (isLanClientMode(nodeMode)) {
    const peer = await resolveLanStratumEndpoint(poolKey, { skipLocal: true, fullOnly: true });
    if (peer) {
      return {
        localNodeOnly: false,
        lanPoolRelay: poolMode,
        noVpsFallback: !poolMode,
        forceVps: false,
        nodeStatus: status,
        chainSyncing: false,
        lanPeer: peer,
      };
    }
    return {
      localNodeOnly: false,
      lanPoolRelay: false,
      noVpsFallback: !poolMode,
      forceVps: true,
      lanPeerMissing: true,
      nodeStatus: status,
      chainSyncing: false,
    };
  }

  if (poolMode && ready && syncing) {
    const peer = await resolveLanStratumEndpoint(poolKey, { skipLocal: true, fullOnly: true });
    if (peer) {
      return {
        localNodeOnly: false,
        lanPoolRelay: true,
        noVpsFallback: false,
        forceVps: false,
        nodeStatus: status,
        chainSyncing: true,
        lanPeer: peer,
      };
    }
    return {
      localNodeOnly: false,
      lanPoolRelay: false,
      noVpsFallback: false,
      forceVps: true,
      nodeStatus: status,
      chainSyncing: true,
    };
  }

  if (poolMode && ready) {
    return {
      localNodeOnly: true,
      lanPoolRelay: true,
      noVpsFallback: false,
      nodeStatus: status,
      chainSyncing: false,
    };
  }

  if (!poolMode && ready && !syncing) {
    return {
      localNodeOnly: true,
      lanPoolRelay: false,
      noVpsFallback: true,
      nodeStatus: status,
      chainSyncing: false,
    };
  }

  const peer = await resolveLanStratumEndpoint(poolKey, {
    skipLocal: !ready,
    fullOnly: poolMode,
  });
  if (peer && peer.source !== "local-node") {
    return {
      localNodeOnly: false,
      lanPoolRelay: poolMode,
      noVpsFallback: !poolMode,
      forceVps: false,
      nodeStatus: status,
      chainSyncing: syncing,
      lanPeer: peer,
    };
  }

  return {
    localNodeOnly: false,
    lanPoolRelay: false,
    noVpsFallback: false,
    forceVps: true,
    nodeStatus: status,
    chainSyncing: syncing,
  };
}

function chainDownloadPhase(status, progress, local, network) {
  if (status?.bloodstonedAlive === false || status?.mode === "gateway") return "unavailable";
  const behind = network > 0 && local > 0 ? Math.max(0, network - local) : 0;
  if (progress != null && progress >= 0.999 && behind <= 20) return "complete";
  if (progress != null && progress >= 0.95) return "verifying";
  if (local > 0 && network > local) return "downloading";
  if (status?.running && (progress == null || progress < 0.02)) return "starting";
  if (status?.syncScheduled || status?.batteryDormant) return "scheduled";
  if (status?.running) return "downloading";
  return "idle";
}

function shouldShowChainDownloadPanel(status) {
  if (!isCapacitorAndroid() && !isAndroidAppContext()) return false;
  if (isLanClientMode()) return false;
  if (!shouldHostLocalNode(getNodeModePreference())) return false;
  if (status?.mode === "gateway" && status?.running) return false;
  if (status?.bloodstonedAlive === false && status?.running) return false;
  if (isNodeSyncing(status)) return true;
  const local = Number(status?.blockHeight) || 0;
  const network = Number(status?.networkBlockHeight) || 0;
  if (status?.running && network > local + 20) return true;
  if (status?.running && local === 0 && network === 0) return true;
  if (status?.running && getNodeModePreference() === NODE_MODES.FULL) return true;
  return false;
}

export function getChainDownloadSnapshot(status) {
  const progress = estimateSyncProgress(status);
  const local = Number(status?.blockHeight) || 0;
  const network = Number(status?.networkBlockHeight) || 0;
  const behind = network > 0 && local > 0 ? Math.max(0, network - local) : 0;
  const pct = progress != null ? Math.round(progress * 100) : null;
  const phase = chainDownloadPhase(status, progress, local, network);
  return {
    progress,
    percent: pct,
    phase,
    local,
    network,
    behind,
    chainBytes: Number(status?.chainBytes) || 0,
    mode: status?.mode || getNodeModePreference(),
    show: shouldShowChainDownloadPanel(status),
  };
}

export function updateNodeSyncProgress(status) {
  const wrap = document.getElementById("local-node-sync-wrap");
  if (!wrap) return;
  const snap = getChainDownloadSnapshot(status);
  wrap.hidden = !snap.show;
  if (!snap.show) {
    wrap.classList.remove("is-starting", "is-complete");
    return;
  }

  const pct =
    snap.percent != null
      ? snap.percent
      : snap.phase === "starting"
        ? 0
        : snap.local > 0 && snap.network > snap.local
          ? Math.max(1, Math.min(99, Math.round((snap.local / snap.network) * 100)))
          : 0;
  const barWidth = snap.phase === "complete" ? 100 : Math.max(snap.phase === "starting" ? 0 : 2, pct);

  const fill = document.getElementById("local-node-sync-fill");
  const bar = document.getElementById("local-node-sync-bar");
  const title = document.getElementById("local-node-sync-title");
  const phaseEl = document.getElementById("local-node-sync-phase");
  const label = document.getElementById("local-node-sync-label");
  const pctEl = document.getElementById("local-node-sync-pct");
  const detail = document.getElementById("local-node-sync-detail");
  const heightEl = document.getElementById("local-node-sync-height");
  const networkEl = document.getElementById("local-node-sync-network");
  const behindEl = document.getElementById("local-node-sync-behind");
  const diskEl = document.getElementById("local-node-sync-disk");

  wrap.classList.toggle("is-starting", snap.phase === "starting");
  wrap.classList.toggle("is-complete", snap.phase === "complete");

  if (fill) {
    if (snap.phase === "starting") {
      fill.style.width = "";
      fill.style.marginLeft = "";
    } else {
      fill.style.marginLeft = "0";
      fill.style.width = `${barWidth}%`;
    }
  }
  if (bar) bar.setAttribute("aria-valuenow", String(pct));
  if (pctEl) pctEl.textContent = `${pct}%`;

  const mode = snap.mode;
  if (title) {
    title.textContent =
      mode === NODE_MODES.FULL ? "Full chain download" : mode === NODE_MODES.MESH ? "Mesh tip sync" : "Pruned chain download";
  }
  if (phaseEl) {
    const phaseLabels = {
      starting: "Starting",
      downloading: "Downloading",
      verifying: "Verifying",
      complete: "Up to date",
      scheduled: "Battery sync",
      unavailable: "Unavailable",
      idle: "Idle",
    };
    phaseEl.textContent = phaseLabels[snap.phase] || "Syncing";
  }
  if (label) {
    if (snap.phase === "complete") {
      label.textContent = "Chain synced — local stratum ready for household miners";
    } else if (snap.phase === "verifying") {
      label.textContent = "Verifying downloaded blocks…";
    } else if (snap.phase === "starting") {
      label.textContent = "Starting bloodstoned on device…";
    } else if (mode === NODE_MODES.FULL) {
      label.textContent = "Downloading and validating full blockchain";
    } else if (mode === NODE_MODES.MESH) {
      label.textContent = "Syncing pruned tip for mesh federation";
    } else {
      label.textContent = "Downloading pruned chain blocks";
    }
  }

  if (heightEl) heightEl.textContent = snap.local > 0 ? String(snap.local) : "—";
  if (networkEl) networkEl.textContent = snap.network > 0 ? String(snap.network) : "—";
  if (behindEl) {
    behindEl.textContent =
      snap.network > 0 && snap.local > 0
        ? snap.behind > 0
          ? String(snap.behind)
          : "0"
        : "—";
  }
  if (diskEl) diskEl.textContent = snap.chainBytes > 0 ? formatBytes(snap.chainBytes) : "—";

  if (detail) {
    if (snap.phase === "complete") {
      detail.textContent = "Download complete. Pool mining can use local stratum; LAN clients on your Wi‑Fi can connect.";
    } else if (status?.bloodstonedAlive === false) {
      detail.textContent = "bloodstoned did not start — free storage, plug in, and restart. Chain download is off.";
    } else if (snap.phase === "starting") {
      detail.textContent = "Keep the app open on Wi‑Fi and plugged in. Progress updates every few seconds.";
    } else {
      detail.textContent = `Downloading blocks ${snap.local > 0 ? snap.local : "…"} → ${snap.network > 0 ? snap.network : "…"} · keep app open on Wi‑Fi`;
    }
  }
}

let statusPollTimer = null;

export function initLocalNodeStatusPolling(onStatus) {
  if (!isCapacitorAndroid()) return;
  const tick = async () => {
    let status = await getLocalNodeStatus();
    if (status?.running) {
      const local = Number(status.blockHeight) || 0;
      const network = Number(status.networkBlockHeight) || 0;
      if (network <= local || network === 0) {
        const netH = await fetchNetworkBlockHeightFromUpstream();
        if (netH > 0) {
          status = { ...status, networkBlockHeight: netH };
        }
      }
    }
    updateLocalNodePanel(status);
    updateNodeSyncProgress(status);
    onStatus?.(status);
  };
  void tick();
  if (statusPollTimer) clearInterval(statusPollTimer);
  statusPollTimer = setInterval(() => {
    void tick();
  }, 2500);
}

function modeLabel(mode) {
  if (mode === NODE_MODES.LAN_CLIENT) return "LAN client";
  if (mode === NODE_MODES.FULL) return "full chain";
  if (mode === NODE_MODES.MESH) return "mesh federation";
  if (mode === "gateway") return "gateway relay";
  return "pruned";
}

export function updateLanPeersPanel(peers = discoveredLanPeersCache, active = activeLanPeer) {
  const wrap = document.getElementById("lan-peers-wrap");
  const summary = document.getElementById("lan-peers-summary");
  const list = document.getElementById("lan-peers-list");
  if (!wrap) return;
  const show = isLanClientMode() || peers.length > 0 || active;
  wrap.hidden = !show;
  if (!show) return;
  if (summary) {
    if (active) {
      summary.textContent = `mining via ${active.displayHost || active.host}:${active.port} (${active.mode || "node"})`;
    } else if (peers.length) {
      summary.textContent = `${peers.length} full node${peers.length === 1 ? "" : "s"} on Wi‑Fi`;
    } else {
      summary.textContent = "searching Wi‑Fi for full nodes…";
    }
  }
  if (list) {
    list.innerHTML = "";
    for (const peer of peers.slice(0, 5)) {
      const li = document.createElement("li");
      const ip = peer.lan_ip || peer.host || "?";
      const mode = peer.mode || "node";
      const height = peer.block_height ? ` · h${peer.block_height}` : "";
      const sync = peer.sync_progress != null
        ? ` · ${Math.round(Number(peer.sync_progress) * 100)}%`
        : "";
      const activeMark = active && (active.displayHost === ip || active.host === ip) ? " ✓" : "";
      li.textContent = `${ip} · ${mode}${height}${sync}${activeMark}`;
      list.appendChild(li);
    }
  }
}

export function initLanPeerDiscovery(intervalMs = 15000) {
  if (!isCapacitorAndroid()) return;
  const plugin = localNodePlugin();
  if (plugin?.startLanBrowse) {
    void plugin.startLanBrowse().catch(() => {});
  }
  const tick = async () => {
    const peers = await listDiscoveredLanPeers({ fullOnly: isLanClientMode() });
    updateLanPeersPanel(peers, getActiveLanPeer());
  };
  void tick();
  if (lanDiscoveryTimer) clearInterval(lanDiscoveryTimer);
  lanDiscoveryTimer = setInterval(() => {
    void tick();
  }, intervalMs);
}

export function updateLocalNodePanel(status) {
  updateNodeSyncProgress(status);
  const line = document.getElementById("local-node-line");
  if (!line) return;
  const rpcEl = document.getElementById("local-node-rpc");
  const modeEl = document.getElementById("local-node-mode");
  const detailEl = document.getElementById("local-node-detail");
  if (isLanClientMode()) {
    line.hidden = false;
    const peer = getActiveLanPeer();
    if (rpcEl) {
      rpcEl.textContent = peer
        ? `${peer.displayHost || peer.host}:${peer.port}`
        : "searching LAN…";
    }
    if (modeEl) {
      modeEl.textContent = peer
        ? `LAN full node · ${peer.mode || "full"} · stratum :${peer.port}`
        : `${modeLabel(NODE_MODES.LAN_CLIENT)} · no host on this device`;
    }
    if (detailEl) {
      detailEl.textContent = peer
        ? " — mining through a household full node on Wi‑Fi; this phone does not download the chain."
        : " — scans mDNS and the pool LAN registry for a synced full node. Pick Full chain on one plugged-in device to host for the household.";
    }
    updateLanPeersPanel();
    return;
  }
  if (!status?.running && !status?.batteryDormant && !status?.syncScheduled && !isNodeSyncing(status)) {
    line.hidden = true;
    return;
  }
  line.hidden = false;
  if (!status?.running && (status?.batteryDormant || status?.syncScheduled)) {
    if (rpcEl) rpcEl.textContent = "Battery sync — node dormant";
    if (modeEl) {
      const local = status.blockHeight || 0;
      const network = status.networkBlockHeight || 0;
      const behind = Math.max(0, network - local);
      modeEl.textContent =
        `${modeLabel(status.mode)} · checks every ${status.syncIntervalMinutes || 15} min` +
        (local > 0 ? ` · height ${local}` : "") +
        (network > 0 ? ` · network ${network}` : "") +
        (behind > 20 ? ` · ${behind} blocks behind` : behind > 0 ? ` · ${behind} behind` : " · up to date");
    }
    if (detailEl) {
      detailEl.textContent =
        "WorkManager wakes the node when 20+ blocks behind, syncs briefly, then sleeps.";
    }
    return;
  }
  if (rpcEl) {
    rpcEl.textContent = status.rpcUrl || `${status.lanIp}:${status.rpcPort}`;
  }
  if (modeEl) {
    const yp = status.stratumPortYespower || status.stratumPorts?.yespower || 3438;
    const neo = status.stratumPort || status.stratumPorts?.neoscrypt || 3437;
    const syncPct =
      status.mode === NODE_MODES.FULL && status.syncProgress != null
        ? ` · sync ${Math.round((status.syncProgress || 0) * 100)}%`
        : "";
    const height = status.blockHeight ? ` · height ${status.blockHeight}` : "";
    modeEl.textContent = `${modeLabel(status.mode)} · LAN stratum :${neo} / yespower :${yp}${height}${syncPct}`;
  }
  if (detailEl) {
    if (status.mode === "gateway" || status.bloodstonedAlive === false) {
      detailEl.textContent =
        " — bloodstoned did not start on this device (storage, binary, or crash). Chain download is off; stratum/RPC relay through the VPS. Plug in, free space, then restart mining.";
    } else if (status.mode === NODE_MODES.FULL) {
      detailEl.textContent =
        " — full bloodstoned on device (no wallet); validates chain, serves LAN RPC/stratum, and peers on :17333 so the central VPS can be retired once enough devices sync.";
    } else if (status.mode === NODE_MODES.MESH) {
      detailEl.textContent =
        " — pruned tip node plus federated block-file backups across phones; helps rebuild chain data if the VPS goes offline.";
    } else {
      detailEl.textContent =
        " — pruned bloodstoned on this device; LAN miners use its RPC/stratum.";
    }
  }
}

const NODE_MODE_SELECT_OPTIONS = [
  {
    value: NODE_MODES.LAN_CLIENT,
    label: "LAN client — mine from household full node (no chain download)",
  },
  { value: NODE_MODES.PRUNED, label: "Pruned (~550 MiB) — host lightweight node" },
  { value: NODE_MODES.FULL, label: "Full chain — host for household (needs ~2 GB free)" },
  { value: NODE_MODES.MESH, label: "Mesh federation — pruned tip + block backups" },
];

function ensureNodeModeSelectOptions(select) {
  if (!select) return;
  for (const { value, label } of NODE_MODE_SELECT_OPTIONS) {
    if (!select.querySelector(`option[value="${value}"]`)) {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = label;
      select.appendChild(opt);
    }
  }
}

export async function initLocalNodeModeUi() {
  if (!isCapacitorAndroid() && !isAndroidAppContext()) return;
  const wrap = document.getElementById("local-node-mode-wrap");
  const select = document.getElementById("local-node-mode-select");
  const hint = document.getElementById("local-node-mode-hint");
  if (!wrap || !select) return;
  ensureNodeModeSelectOptions(select);
  wrap.hidden = false;
  select.value = getNodeModePreference();
  await whenCapacitorReady();
  const storage = await getNodeStorageInfo();
  if (hint) {
    if (isLanClientMode(select.value)) {
      hint.textContent = "Searches Wi‑Fi for a synced full node — no bloodstoned on this phone.";
    } else if (storage) {
      hint.textContent = `Free ${formatBytes(storage.freeBytes)} · full node needs ${formatBytes(storage.fullNodeMinFreeBytes)}+ free`;
      if (!storage.canRunFullNode) {
        hint.textContent += " — low free space; full node still runs but may sync slowly";
      }
    }
  }
  select.addEventListener("change", async () => {
    const mode = setNodeModePreference(select.value);
    const { configureMeshForNodeMode } = await import("./chain-mesh.js");
    await configureMeshForNodeMode(mode);
    let status = null;
    if (shouldHostLocalNode(mode)) {
      status = await startLocalNode({
        nodeMode: mode,
        foreground: mode === NODE_MODES.FULL,
      });
    } else {
      await stopLocalNode({ foregroundOnly: true });
      status = await getLocalNodeStatus();
      void listDiscoveredLanPeers({ fullOnly: true });
    }
    updateLocalNodePanel(status);
    updateNodeSyncProgress(status);
    updateLanPeersPanel();
    const { updateFleetPanel } = await import("./device-fleet.js");
    updateFleetPanel({
      identity: null,
      transport: "native-tcp",
      fleetStats: null,
      mining: false,
      networkNodes: null,
    });
  });
}
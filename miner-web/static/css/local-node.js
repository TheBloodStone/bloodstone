/** Local VPS node — Android Capacitor + LAN peer discovery (pruned, full, or mesh). */

import { apiUrl } from "./miner-paths.js";
import { isCapacitorAndroid } from "./device-fleet.js";
import {
  hasNativeCapacitorBridge,
  isAndroidAppContext,
  isBundledMinerOrigin,
  openBundledMinerScreen,
  whenCapacitorReady,
} from "./capacitor-ready.js";

const NODE_MODE_KEY = "bloodstone-local-node-mode";
const NODE_ONLY_SESSION_KEY = "bloodstone-node-only-active";
const DEFAULT_PRUNE_MIB = 550;
const FULL_CHAIN_ESTIMATE_BYTES = 550 * 1024 * 1024;
const PRUNED_CHAIN_ESTIMATE_BYTES = 550 * 1024 * 1024;

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
  CONSENSUS: "consensus",
  CONSENSUS_WITNESS: "consensus-witness",
};

let discoveredLanPeersCache = [];
let activeLanPeer = null;
let lanDiscoveryTimer = null;
let chainDownloadPanelForced = false;
let nodeActivateInFlight = false;
let lastBloodstonedDeathAt = 0;
let nodeStartAttemptAt = 0;
const NODE_START_STALE_MS = 45000;
const NODE_BRIDGE_STALE_MS = 20000;

export function setChainDownloadPanelForced(forced) {
  chainDownloadPanelForced = forced === true;
}

function buildLocalNodePluginAdapter() {
  const cap = window.Capacitor;
  if (!cap) return null;
  const raw = cap.Plugins?.BloodstoneLocalNode;
  const hasNative = typeof cap.nativePromise === "function";
  if (!raw && !hasNative) return null;
  const call = (method, args = {}) => {
    if (raw && typeof raw[method] === "function") {
      return raw[method](args);
    }
    if (hasNative) {
      return cap.nativePromise("BloodstoneLocalNode", method, args);
    }
    throw new Error(`BloodstoneLocalNode.${method} unavailable`);
  };
  return {
    startLocalNode: (opts) => call("startLocalNode", opts),
    stopLocalNode: (opts) => call("stopLocalNode", opts),
    getLocalNodeStatus: () => call("getLocalNodeStatus"),
    getNodeStorageInfo: () => call("getNodeStorageInfo"),
    registerLan: () => call("registerLan"),
    discoverLanPeers: () => call("discoverLanPeers"),
    resetLocalNodeChain: (opts) => call("resetLocalNodeChain", opts),
  };
}

export function localNodePlugin() {
  try {
    return buildLocalNodePluginAdapter();
  } catch (_) {
    return null;
  }
}

function describeCapacitorBridge() {
  const cap = window.Capacitor;
  if (!cap) return "Capacitor not loaded";
  const platform = typeof cap.getPlatform === "function" ? cap.getPlatform() : "?";
  const hasPlugin = Boolean(cap.Plugins?.BloodstoneLocalNode);
  const hasNative = typeof cap.nativePromise === "function";
  return `platform=${platform} plugin=${hasPlugin ? "yes" : "no"} nativePromise=${hasNative ? "yes" : "no"}`;
}

export async function waitForLocalNodePlugin(maxWaitMs = 15000) {
  const deadline = Date.now() + maxWaitMs;
  let lastDiag = "";
  while (Date.now() < deadline) {
    await whenCapacitorReady(Math.min(2000, deadline - Date.now()));
    const plugin = localNodePlugin();
    if (plugin?.startLocalNode) return plugin;
    lastDiag = describeCapacitorBridge();
    await new Promise((r) => setTimeout(r, 400));
  }
  let hint =
    "Install APK 1.3.44 from Updates → Downloads, then Check for updates (UI 1.3.68-web+).";
  if (isAndroidAppContext() && !isBundledMinerOrigin()) {
    hint =
      "You are on the live portal inside the app — full node needs the bundled miner screen. "
      + "Switching now…";
    openBundledMinerScreen("?app=android");
  } else if (!hasNativeCapacitorBridge()) {
    hint += " Open the Bloodstone app icon (not Chrome).";
  }
  const err = new Error(
    `Local node bridge unavailable (${lastDiag || describeCapacitorBridge()}). ${hint}`,
  );
  err.code = "LOCAL_NODE_PLUGIN_MISSING";
  throw err;
}

export function getNodeModePreference() {
  try {
    const raw = localStorage.getItem(NODE_MODE_KEY);
    if (
      raw === NODE_MODES.FULL
      || raw === NODE_MODES.MESH
      || raw === NODE_MODES.PRUNED
      || raw === NODE_MODES.LAN_CLIENT
      || raw === NODE_MODES.CONSENSUS
      || raw === NODE_MODES.CONSENSUS_WITNESS
    ) {
      return raw;
    }
  } catch (_) {
    /* ignore */
  }
  return NODE_MODES.PRUNED;
}

/** Prefer the mode dropdown — localStorage can be empty after Clear data. */
export function readNodeModeFromUi() {
  const select = document.getElementById("local-node-mode-select");
  const fromSelect = String(select?.value || "").trim();
  if (
    fromSelect === NODE_MODES.FULL
    || fromSelect === NODE_MODES.MESH
    || fromSelect === NODE_MODES.PRUNED
    || fromSelect === NODE_MODES.LAN_CLIENT
    || fromSelect === NODE_MODES.CONSENSUS
    || fromSelect === NODE_MODES.CONSENSUS_WITNESS
  ) {
    return setNodeModePreference(fromSelect);
  }
  return getNodeModePreference();
}

function setNodeOnlyStatusMessage(text, kind = "") {
  const statusEl = document.getElementById("node-only-status");
  if (!statusEl) return;
  statusEl.textContent = text || "";
  statusEl.classList.remove("node-status-error", "node-status-ok", "node-status-warn");
  if (kind === "error") statusEl.classList.add("node-status-error");
  else if (kind === "ok") statusEl.classList.add("node-status-ok");
  else if (kind === "warn") statusEl.classList.add("node-status-warn");
}

export function isNodeOnlyActive() {
  try {
    return sessionStorage.getItem(NODE_ONLY_SESSION_KEY) === "1";
  } catch (_) {
    return false;
  }
}

function setNodeOnlyActive(active) {
  try {
    if (active) {
      sessionStorage.setItem(NODE_ONLY_SESSION_KEY, "1");
    } else {
      sessionStorage.removeItem(NODE_ONLY_SESSION_KEY);
    }
  } catch (_) {
    /* ignore */
  }
}

function nodeActivateLabel(mode) {
  if (mode === NODE_MODES.FULL) return "Start full node";
  if (mode === NODE_MODES.MESH) return "Start mesh node";
  if (mode === NODE_MODES.CONSENSUS) return "Start consensus node";
  if (mode === NODE_MODES.CONSENSUS_WITNESS) return "Start witness node";
  if (mode === NODE_MODES.PRUNED) return "Start pruned node";
  return "Start node";
}

export function updateNodeOnlyControls(status, { mining = false } = {}) {
  const wrap = document.getElementById("node-only-actions");
  const activateBtn = document.getElementById("btn-activate-node");
  const stopBtn = document.getElementById("btn-stop-node");
  const statusEl = document.getElementById("node-only-status");
  if (!wrap || !activateBtn || !stopBtn) return;

  const mode = readNodeModeFromUi();
  const hosting = shouldHostLocalNode(mode);
  wrap.hidden = false;

  if (!hosting) {
    setNodeOnlyActive(false);
    activateBtn.textContent = "Start node";
    activateBtn.disabled = mining;
    stopBtn.disabled = true;
    if (statusEl && !statusEl.classList.contains("node-status-error")) {
      statusEl.textContent =
        "LAN client — pick Pruned or Full chain above to download the blockchain on this phone.";
    }
    return;
  }

  activateBtn.textContent = nodeActivateLabel(mode);
  const running = Boolean(status?.running && !status?.batteryDormant);
  activateBtn.disabled = mining || running;
  stopBtn.disabled = mining || !running;

  if (statusEl) {
    if (mining && running) {
      statusEl.textContent =
        "Node is running — mining is also active on this device.";
    } else if (running) {
      statusEl.textContent =
        isConsensusMode(mode)
          ? "Consensus node is active — validates blocks and witnesses the chain. No LAN stratum; use Pool mode or a household full node to mine."
          : mode === NODE_MODES.FULL
            ? "Full node is active — syncing the chain and serving LAN RPC/stratum. Mining is optional."
            : "Local node is active — household miners can use the LAN endpoints below. Mining is optional.";
    } else if (mode === NODE_MODES.FULL) {
      statusEl.textContent =
        "Run a full bloodstoned node on this phone without mining — validates the chain and hosts your household.";
    } else {
      statusEl.textContent =
        "Start bloodstoned on this device without mining — opens RPC/stratum for other rigs on your Wi‑Fi.";
    }
  }
}

export async function activateNodeWithoutMining({ onLog, onStatus } = {}) {
  if (!isCapacitorAndroid() && !isAndroidAppContext()) return null;
  if (nodeActivateInFlight) {
    const msg = "Node start already in progress…";
    onLog?.(msg, "warn");
    setNodeOnlyStatusMessage(msg, "warn");
    return getLocalNodeStatus();
  }
  const mode = readNodeModeFromUi();
  if (!shouldHostLocalNode(mode)) {
    const msg =
      "LAN client mode does not host a node — pick Pruned, Full chain, or Mesh in the dropdown above, then tap Start again.";
    onLog?.(msg, "error");
    setNodeOnlyStatusMessage(msg, "error");
    return null;
  }
  let plugin = null;
  try {
    plugin = await waitForLocalNodePlugin(15000);
  } catch (err) {
    const msg = String(err?.message || err || "Local node plugin missing");
    onLog?.(msg, "error");
    setNodeOnlyStatusMessage(msg, "error");
    if (typeof window.__bloodstoneRunAndroidUpdate === "function") {
      onLog?.("Trying UI/APK update to restore native bridge…", "warn");
      try {
        await window.__bloodstoneRunAndroidUpdate({ auto: true });
      } catch (_) {
        /* ignore */
      }
    }
    return null;
  }
  nodeActivateInFlight = true;
  try {
  nodeStartAttemptAt = Date.now();
  setNodeOnlyActive(true);
  setChainDownloadPanelForced(true);
  setNodeOnlyStatusMessage(`Starting ${modeLabel(mode)}…`, "warn");
  updateNodeSyncProgress(nodeStartPlaceholderStatus(mode));
  const storage = await getNodeStorageInfo();
  if (storage && storage.freeBytes < 96 * 1024 * 1024) {
    onLog?.(
      `Only ${formatBytes(storage.freeBytes)} free — need at least 96 MB before bloodstoned can start`,
      "error",
    );
  }
  const uiVer =
    document.body?.dataset?.webUiVersion
    || document.body?.dataset?.webBundleVersion
    || "bundled";
  onLog?.(`UI ${uiVer} · starting ${modeLabel(mode)} node (no mining)…`);
  const startResult = await startLocalNode({
    nodeMode: mode,
    foreground: true,
    waitForStratumMs: 0,
  });
  if (!startResult) {
    const msg = "Node start returned no status — restart the app and try again";
    onLog?.(msg, "error");
    setNodeOnlyStatusMessage(msg, "error");
    return null;
  }
  if (startResult?.startError) {
    const status = startResult;
    const errText = formatNodeStartError(status, mode);
    updateNodeSyncProgress(status);
    onLog?.(errText, "error");
    setNodeOnlyStatusMessage(errText, "error");
    updateNodeOnlyControls(status);
    onStatus?.(status);
    return status;
  }
  // Do not block the UI for minutes — status polling drives the download panel.
  let status = startResult || (await getLocalNodeStatus());
  status = (await waitForNodeRunning(12000)) || status || (await getLocalNodeStatus());
  updateNodeSyncProgress(status || nodeStartPlaceholderStatus(mode));
  if (status?.startError) {
    onLog?.(formatNodeStartError(status, mode), "error");
    updateNodeOnlyControls(status);
    onStatus?.(status);
    return status;
  }
  if (status?.bloodstonedAlive === false && !status?.nodeStarting && !status?.chainBootstrapping) {
    onLog?.(formatNodeStartError(status, mode), "error");
    updateNodeOnlyControls(status);
    onStatus?.(status);
    return status;
  }
  if (status?.running) {
    const reg = await ensureLanRegistration();
    if (reg?.ok) {
      onLog?.("LAN registered — other devices can find this node on your Wi‑Fi", "success");
    }
    if (localStratumAvailable(status)) {
      onLog?.(
        `Node active — RPC ${status.rpcUrl || status.lanIp || "127.0.0.1"} · stratum :${status.stratumPort || 3437}`,
        "success",
      );
    } else if (isNodeSyncing(status)) {
      onLog?.("Node started — chain download in progress", "success");
    } else {
      onLog?.("Node started — waiting for stratum ports", "warn");
    }
  } else {
    const msg = status?.chainBootstrapping
      ? "Installing pre-downloaded chain — keep the app open on Wi‑Fi"
      : "Node is starting — keep the app open on Wi‑Fi and plugged in";
    onLog?.(msg, "warn");
    setNodeOnlyStatusMessage(msg, "warn");
  }
  updateLocalNodePanel(status || nodeStartPlaceholderStatus(mode));
  updateNodeSyncProgress(status || nodeStartPlaceholderStatus(mode));
  updateNodeOnlyControls(status || nodeStartPlaceholderStatus(mode));
  onStatus?.(status);
  return status;
  } finally {
    nodeActivateInFlight = false;
  }
}

export async function deactivateNodeWithoutMining({ onLog, mining = false, onStatus } = {}) {
  if (mining) {
    onLog?.("Stop mining first, then you can stop the node", "warn");
    return null;
  }
  setNodeOnlyActive(false);
  setChainDownloadPanelForced(false);
  await stopLocalNode({ foregroundOnly: false });
  const status = await getLocalNodeStatus();
  updateLocalNodePanel(status);
  updateNodeSyncProgress(status);
  updateNodeOnlyControls(status);
  onStatus?.(status);
  onLog?.("Local node stopped", "success");
  return status;
}

export function initNodeOnlyControls({ onLog, getMining, onStatus } = {}) {
  if (!isCapacitorAndroid() && !isAndroidAppContext()) return;
  const activateBtn = document.getElementById("btn-activate-node");
  const stopBtn = document.getElementById("btn-stop-node");
  if (!activateBtn || !stopBtn) return;

  const refreshControls = async () => {
    const status = await getLocalNodeStatus();
    updateNodeOnlyControls(status, { mining: getMining?.() === true });
    updateNodeSyncProgress(status || nodeStartPlaceholderStatus());
    return status;
  };

  activateBtn.addEventListener("click", async () => {
    activateBtn.disabled = true;
    try {
      await activateNodeWithoutMining({ onLog, onStatus });
    } finally {
      await refreshControls();
    }
  });

  stopBtn.addEventListener("click", async () => {
    stopBtn.disabled = true;
    try {
      await deactivateNodeWithoutMining({
        onLog,
        mining: getMining?.() === true,
        onStatus,
      });
    } finally {
      await refreshControls();
    }
  });

  void refreshControls();
}

export function isConsensusMode(mode = getNodeModePreference()) {
  return mode === NODE_MODES.CONSENSUS || mode === NODE_MODES.CONSENSUS_WITNESS;
}

export function shouldHostStratum(mode = getNodeModePreference()) {
  return shouldHostLocalNode(mode) && !isConsensusMode(mode);
}

export function setNodeModePreference(mode) {
  const normalized =
    mode === NODE_MODES.FULL
    || mode === NODE_MODES.MESH
    || mode === NODE_MODES.LAN_CLIENT
    || mode === NODE_MODES.CONSENSUS
    || mode === NODE_MODES.CONSENSUS_WITNESS
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
    || mode === NODE_MODES.PRUNED
    || mode === NODE_MODES.CONSENSUS
    || mode === NODE_MODES.CONSENSUS_WITNESS;
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
      options.foreground !== false && shouldHostLocalNode(preferred.nodeMode);
    if (shouldHostLocalNode(preferred.nodeMode)) {
      setChainDownloadPanelForced(true);
      updateNodeSyncProgress(await getLocalNodeStatus());
    }
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
  } catch (err) {
    const msg = String(err?.message || err || "startLocalNode failed");
    console.warn("startLocalNode failed:", msg);
    const status = await getLocalNodeStatus();
    return { ...(status || {}), startError: msg, running: false, nodeStarting: false };
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

function normalizePluginPayload(raw) {
  if (raw == null) return null;
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw);
    } catch (_) {
      return null;
    }
  }
  if (typeof raw !== "object") return null;
  if (raw.value != null && typeof raw.value === "object") return raw.value;
  return raw;
}

async function rawGetLocalNodeStatus() {
  const plugin = localNodePlugin();
  if (plugin?.getLocalNodeStatus) {
    try {
      const status = normalizePluginPayload(await plugin.getLocalNodeStatus());
      if (status) return status;
    } catch (_) {
      /* fall through */
    }
  }
  const cap = window.Capacitor;
  if (typeof cap?.nativePromise === "function") {
    try {
      const status = normalizePluginPayload(
        await cap.nativePromise("BloodstoneLocalNode", "getLocalNodeStatus", {}),
      );
      if (status) return status;
    } catch (_) {
      /* ignore */
    }
  }
  return null;
}

export async function getLocalNodeStatus() {
  return enrichNodeStartStatus(await rawGetLocalNodeStatus());
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
  else if (mode === "consensus") score = 50;
  else if (mode === "pruned") score = 40;
  else if (mode === "consensus-witness" || mode === "consensus_witness") score = 30;
  if (Number.isFinite(sync) && sync >= 0.999) score += 5;
  return score;
}

function isFullNodePeer(node) {
  if (!node) return false;
  const mode = String(node.mode || "").toLowerCase();
  return mode === "full" && !node.pruned;
}

function isStratumPeer(node) {
  if (!node) return false;
  const mode = String(node.mode || "").toLowerCase();
  if (mode === "consensus" || mode === "consensus-witness" || mode === "consensus_witness") {
    return false;
  }
  if (node.consensus_only === true || node.consensus_only === 1) return false;
  const neo = Number(node.stratum_port || 0);
  const yp = Number(node.stratum_port_yespower || 0);
  return neo > 0 || yp > 0;
}

function peerMatchesFilter(node, options = {}) {
  if (!node) return false;
  if (options.fullOnly && !isFullNodePeer(node)) return false;
  if (options.stratumOnly && !isStratumPeer(node)) return false;
  if (options.minSync != null) {
    const sync = Number(node.sync_progress ?? node.syncProgress);
    if (Number.isFinite(sync) && sync < options.minSync) return false;
  }
  return true;
}

export function localStratumAvailable(status) {
  if (!status?.running) return false;
  const mode = effectiveNodeMode(status);
  if (isConsensusMode(mode)) return false;
  if (isCapacitorAndroid()) return shouldHostStratum(mode);
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

/** Poll until foreground service reports running or bloodstoned failure. */
export async function waitForNodeRunning(maxWaitMs = 20000) {
  if (!isCapacitorAndroid() && !isAndroidAppContext()) return null;
  const deadline = Date.now() + maxWaitMs;
  let last = null;
  while (Date.now() < deadline) {
    last = await getLocalNodeStatus();
    if (last?.running) return last;
    if (last?.startError) return last;
    if (last?.bloodstonedAlive === false && !last?.nodeStarting) return last;
    await new Promise((r) => setTimeout(r, 500));
  }
  return last;
}

function formatNodeStartError(status, mode = getNodeModePreference()) {
  const raw = String(status?.startError || "").trim();
  if (raw) {
    if (/ForegroundServiceStartNotAllowed|background/i.test(raw)) {
      return "Android blocked background start — keep the miner app open in front, then tap Start again";
    }
    if (/not allowed to start service|SecurityException/i.test(raw)) {
      return "Android denied the node service — allow notifications, disable battery saver for this app, then retry";
    }
    if (/EADDRINUSE|Address already in use|bind/i.test(raw)) {
      return "Node ports busy — tap Stop node, wait 5 seconds, then Start again";
    }
    if (/storage|space|ENOSPC/i.test(raw)) {
      return "Not enough free storage — free at least 400 MB on the phone";
    }
    return `Local node failed: ${raw}`;
  }
  const storage = status?.storageWarning === "low_storage";
  if (mode === NODE_MODES.FULL && storage) {
    return "Low free storage — free at least 400 MB, plug in on Wi‑Fi, then tap Start full node";
  }
  if (status?.bloodstonedAlive === false) {
    const restarts = Number(status?.bloodstonedRestartAttempts) || 0;
    if (restarts > 0) {
      return `bloodstoned crashed — auto-restart ${restarts}/8 in progress. Keep app open on Wi‑Fi, plugged in, battery saver off`;
    }
    return "bloodstoned did not start — 64-bit ARM required, ~400 MB free, stay on Wi‑Fi plugged in";
  }
  return "Node did not report running — allow notifications, plug in on Wi‑Fi, keep app open, tap Start again";
}

function nodeStartPlaceholderStatus(mode = getNodeModePreference()) {
  return {
    running: false,
    nodeStarting: true,
    requestedMode: mode,
    mode,
    bloodstonedAlive: undefined,
    blockHeight: 0,
    networkBlockHeight: 0,
    headerHeight: 0,
    syncProgress: 0,
    chainBytes: 0,
  };
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
    if (
      localStratumAvailable(status)
      && shouldHostStratum(getNodeModePreference())
    ) {
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
  const clamped = Math.max(0, Math.min(1, raw));
  // verificationprogress stays at 0 for most of initial block download.
  if (clamped === 0 && status?.running && status?.bloodstonedAlive !== false) {
    return null;
  }
  return clamped;
}

async function fetchNetworkBlockHeightFromUpstream() {
  const payload = {
    jsonrpc: "1.0",
    id: "net-height",
    method: "getblockcount",
    params: [],
  };
  const url = apiUrl("/api/local-node/rpc");
  const cap = window.Capacitor;
  if (cap?.nativePromise) {
    try {
      const response = await cap.nativePromise("CapacitorHttp", "request", {
        url,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        data: payload,
      });
      const status = Number(response?.status) || 0;
      if (status >= 200 && status < 300) {
        const raw = response?.data;
        const data = typeof raw === "string" ? JSON.parse(raw) : raw;
        return Number(data?.result) || 0;
      }
    } catch (_) {
      /* fall through */
    }
  }
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) return 0;
    const data = await res.json();
    return Number(data?.result) || 0;
  } catch (_) {
    return 0;
  }
}

function networkTipHeight(status) {
  const local = Number(status?.blockHeight) || 0;
  const network = Number(status?.networkBlockHeight) || 0;
  const headers = Number(status?.headerHeight) || 0;
  return Math.max(network, headers, local);
}

function chainBytesProgress(status) {
  const chainBytes = Number(status?.chainBytes) || 0;
  if (chainBytes < 2 * 1024 * 1024) return null;
  const mode = effectiveNodeMode(status);
  const estimate = mode === NODE_MODES.FULL
    ? FULL_CHAIN_ESTIMATE_BYTES
    : PRUNED_CHAIN_ESTIMATE_BYTES;
  return Math.max(0.02, Math.min(0.96, chainBytes / estimate));
}

export function estimateSyncProgress(status) {
  const local = Number(status?.blockHeight) || 0;
  const headers = Number(status?.headerHeight) || 0;
  const tip = networkTipHeight(status);
  const reported = syncProgressRatio(status);

  if (local > 0 && tip > local) {
    return Math.max(0.01, Math.min(0.99, local / tip));
  }
  if (headers > 0 && tip > headers) {
    return Math.max(0.01, Math.min(0.95, headers / tip));
  }
  if (headers > 0 && headers > local) {
    return Math.max(0.01, Math.min(0.9, local / headers));
  }
  if (reported != null && reported > 0.001 && reported < 0.999) return reported;
  const bytesProgress = chainBytesProgress(status);
  if (bytesProgress != null) return bytesProgress;
  if (status?.running && status?.bloodstonedAlive !== false && local === 0) {
    const chainBytes = Number(status?.chainBytes) || 0;
    if (chainBytes > 512 * 1024) {
      const bytesProgress = chainBytesProgress(status);
      if (bytesProgress != null) return Math.max(0.05, bytesProgress);
      return 0.08;
    }
  }
  if (status?.running && status?.nodeStarting && status?.bloodstonedAlive) return 0.08;
  if (isActivelyStartingNode(status)) return 0.02;
  if (status?.running && status?.bloodstonedAlive !== false) {
    return 0.05;
  }
  return reported;
}

export function displaySyncPercent(status) {
  const progress = estimateSyncProgress(status);
  if (progress == null) {
    return isNodeSyncing(status) ? 1 : null;
  }
  if (progress >= 0.999) return 100;
  return Math.max(1, Math.round(progress * 100));
}

export function isNodeSyncing(status) {
  if (!status) return isNodeOnlyActive() || chainDownloadPanelForced;
  if (isActivelyStartingNode(status)) return true;
  const requested = effectiveNodeMode(status);
  if (status.mode === "gateway" && status.running && !shouldHostLocalNode(requested)) return false;
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
  const ready = hosting && shouldHostStratum(nodeMode) && isLocalNodeStratumReady(status);
  const poolMode = miningMode !== "solo";

  if (isConsensusMode(nodeMode)) {
    const peer = await resolveLanStratumEndpoint(poolKey, {
      skipLocal: true,
      fullOnly: poolMode,
      stratumOnly: true,
    });
    if (peer) {
      return {
        localNodeOnly: false,
        lanPoolRelay: poolMode,
        noVpsFallback: !poolMode,
        forceVps: false,
        nodeStatus: status,
        chainSyncing: isNodeSyncing(status),
        lanPeer: peer,
        consensusOnly: true,
      };
    }
    return {
      localNodeOnly: false,
      lanPoolRelay: false,
      noVpsFallback: !poolMode,
      forceVps: true,
      nodeStatus: status,
      chainSyncing: isNodeSyncing(status),
      consensusOnly: true,
    };
  }

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

function effectiveNodeMode(status) {
  return String(status?.requestedMode || status?.mode || getNodeModePreference() || "").trim();
}

function isNodeStartStale() {
  return nodeStartAttemptAt > 0 && Date.now() - nodeStartAttemptAt > NODE_START_STALE_MS;
}

function clearNodeStartAttempt() {
  nodeStartAttemptAt = 0;
}

/** Surface actionable errors when native status never arrives or boot stalls. */
function enrichNodeStartStatus(status) {
  const mode = effectiveNodeMode(status || nodeStartPlaceholderStatus());
  if (status?.startError && !status?.running && !status?.nodeStarting) {
    return status;
  }
  if (
    status?.running
    || status?.nodeStarting
    || status?.chainBootstrapping
    || (status?.bloodstonedAlive && status?.running)
  ) {
    if (status?.running && (status?.bloodstonedAlive || Number(status?.chainBytes) > 0)) {
      clearNodeStartAttempt();
    }
    return status;
  }
  if (!shouldHostLocalNode(mode) || (!isNodeOnlyActive() && !chainDownloadPanelForced)) {
    return status;
  }
  const bridgeStale =
    status == null
    && nodeStartAttemptAt > 0
    && Date.now() - nodeStartAttemptAt > NODE_BRIDGE_STALE_MS;
  if (!isNodeStartStale() && !bridgeStale) return status;
  const plugin = localNodePlugin();
  const bridgeHint = plugin?.getLocalNodeStatus
    ? ""
    : " Open Updates → Check for updates (need UI 1.3.66-web+) and APK 1.3.44+.";
  const err =
    status?.startError
    || (status == null
      ? `Native node bridge not responding — keep app open on Wi‑Fi, allow notifications.${bridgeHint}`
      : "Node start timed out — allow notifications, disable battery saver, tap Stop then Start again.");
  return {
    ...(status || nodeStartPlaceholderStatus(mode)),
    startError: err,
    nodeStarting: false,
    running: false,
    bloodstonedAlive: false,
  };
}

function isActivelyStartingNode(status) {
  if (status?.startError && isNodeStartStale()) return false;
  if (status?.chainBootstrapping) return true;
  if (status?.nodeStarting) return true;
  const mode = effectiveNodeMode(status);
  if (!shouldHostLocalNode(mode)) return false;
  if (status?.running) return false;
  if (isNodeStartStale() && status?.bloodstonedAlive === false) return false;
  return chainDownloadPanelForced || isNodeOnlyActive();
}

function chainDownloadPhase(status, progress, local, network) {
  const mode = effectiveNodeMode(status);
  if (status?.startError && !status?.nodeStarting && !status?.running) return "unavailable";
  if (status?.chainBootstrapping) return "bootstrap";
  if (status?.nodeStarting && status?.running) {
    const chainBytes = Number(status?.chainBytes) || 0;
    if (status?.bloodstonedAlive || chainBytes > 512 * 1024 || local > 0) return "loading";
    return "starting";
  }
  if (status?.bloodstonedAlive === false && shouldHostLocalNode(mode)) {
    return status?.running ? "unavailable" : "unavailable";
  }
  if (status?.mode === "gateway" && !shouldHostLocalNode(mode)) return "unavailable";
  const headers = Number(status?.headerHeight) || 0;
  const tip = Math.max(network, headers, local);
  const behind = tip > 0 && local > 0 ? Math.max(0, tip - local) : 0;
  const chainBytes = Number(status?.chainBytes) || 0;
  if (progress != null && progress >= 0.999 && behind <= 20) return "complete";
  if (progress != null && progress >= 0.95 && behind <= 5) return "verifying";
  if (local > 0 && tip > local) return "downloading";
  if (headers > 0 && tip > headers) return "downloading";
  if (
    status?.running
    && status?.bloodstonedAlive !== false
    && local === 0
    && chainBytes > 512 * 1024
  ) {
    return "loading";
  }
  if (chainBytes > 2 * 1024 * 1024 && progress != null && progress < 0.999) return "downloading";
  if (status?.running && status?.bloodstonedAlive !== false) {
    if (headers > 0 || chainBytes > 512 * 1024 || local > 0) return "downloading";
    return "loading";
  }
  if (isActivelyStartingNode(status)) return "starting";
  if (status?.running && status?.bloodstonedAlive !== false && (progress == null || progress <= 0.02)) {
    return chainBytes > 512 * 1024 || headers > 0 ? "downloading" : "starting";
  }
  if ((status?.syncScheduled || status?.batteryDormant) && !isActivelyStartingNode(status)) {
    return "scheduled";
  }
  if (status?.running) return "downloading";
  if (shouldHostLocalNode(mode) && (chainDownloadPanelForced || isNodeOnlyActive())) {
    return "starting";
  }
  return "idle";
}

function shouldShowChainDownloadPanel(status) {
  if (!isCapacitorAndroid() && !isAndroidAppContext()) return false;
  if (isLanClientMode()) return false;
  const prefMode = getNodeModePreference();
  if (lastBloodstonedDeathAt && shouldHostLocalNode(prefMode)) {
    return true;
  }
  if ((chainDownloadPanelForced || isNodeOnlyActive()) && shouldHostLocalNode(prefMode)) {
    return true;
  }
  const mode = effectiveNodeMode(status);
  if (!shouldHostLocalNode(mode)) return false;
  if (status?.bloodstonedAlive === false && status?.running) return true;
  if (status?.mode === "gateway" && status?.running && !shouldHostLocalNode(mode)) return false;
  if (isNodeSyncing(status)) return true;
  const local = Number(status?.blockHeight) || 0;
  const network = Number(status?.networkBlockHeight) || 0;
  if (status?.running && network > local + 20) return true;
  if (status?.running && local === 0 && network === 0) return true;
  if (status?.running && mode === NODE_MODES.FULL) return true;
  return false;
}

export function getChainDownloadSnapshot(status) {
  const progress = estimateSyncProgress(status);
  const local = Number(status?.blockHeight) || 0;
  const network = Number(status?.networkBlockHeight) || 0;
  const tip = networkTipHeight(status);
  const behind = tip > 0 && local > 0 ? Math.max(0, tip - local) : 0;
  const pct = progress != null ? Math.round(progress * 100) : null;
  const phase = chainDownloadPhase(status, progress, local, network);
  return {
    progress,
    percent: pct,
    phase,
    local,
    network: tip,
    behind,
    chainBytes: Number(status?.chainBytes) || 0,
    mode: effectiveNodeMode(status),
    show: shouldShowChainDownloadPanel(status),
  };
}

export function updateNodeSyncProgress(status) {
  const wrap = document.getElementById("local-node-sync-wrap");
  if (!wrap) return;
  const snap = getChainDownloadSnapshot(status || nodeStartPlaceholderStatus());
  wrap.hidden = !snap.show;
  if (!snap.show) {
    wrap.classList.remove("is-starting", "is-complete");
    return;
  }

  let pct =
    snap.percent != null
      ? snap.percent
      : snap.local > 0 && snap.network > snap.local
        ? Math.max(1, Math.min(99, Math.round((snap.local / snap.network) * 100)))
        : 0;
  if (snap.phase === "starting" && pct < 1) pct = 1;
  if (snap.phase === "downloading" && pct < 2) pct = Math.max(pct, 2);
  const barWidth = snap.phase === "complete" ? 100 : Math.max(2, pct);

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
      mode === NODE_MODES.FULL
        ? "Full chain download"
        : mode === NODE_MODES.MESH
          ? "Mesh tip sync"
          : mode === NODE_MODES.CONSENSUS
            ? "Consensus chain sync"
            : mode === NODE_MODES.CONSENSUS_WITNESS
              ? "Witness chain sync"
              : "Pruned chain download";
  }
  const displayPhase =
    snap.phase === "idle" && snap.show ? "starting" : snap.phase;
  if (phaseEl) {
    const phaseLabels = {
      bootstrap: "Pre-download",
      starting: "Starting",
      loading: "Loading chain",
      downloading: "Downloading",
      verifying: "Verifying",
      complete: "Up to date",
      scheduled: "Battery sync",
      unavailable: "Node failed to start",
      idle: "Waiting",
    };
    phaseEl.textContent = phaseLabels[displayPhase] || "Syncing";
  }
  if (label) {
    if (snap.phase === "complete") {
      label.textContent = "Chain synced — local stratum ready for household miners";
    } else if (snap.phase === "verifying") {
      label.textContent = "Verifying downloaded blocks…";
    } else if (snap.phase === "bootstrap" || displayPhase === "bootstrap") {
      const pct = Number(status?.chainBootstrapPct) || 0;
      label.textContent = pct > 0
        ? `Installing pre-downloaded chain (${pct}%)…`
        : "Installing pre-downloaded chain snapshot…";
    } else if (snap.phase === "loading" || displayPhase === "loading") {
      label.textContent = "Loading chain index from pre-downloaded blocks…";
    } else if (snap.phase === "starting" || displayPhase === "starting") {
      label.textContent = "Starting bloodstoned on device…";
    } else if (mode === NODE_MODES.FULL) {
      label.textContent = "Downloading and validating full blockchain";
    } else if (mode === NODE_MODES.MESH) {
      label.textContent = "Syncing pruned tip for mesh federation";
    } else if (mode === NODE_MODES.CONSENSUS) {
      label.textContent = "Downloading pruned chain and validating consensus (P2P peer)";
    } else if (mode === NODE_MODES.CONSENSUS_WITNESS) {
      label.textContent = "Witnessing chain headers and blocks — consensus only, no stratum";
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
      detail.textContent = isConsensusMode(mode)
        ? "Chain synced — this device witnesses consensus only. Use Pool mode or a household full node to mine."
        : "Download complete. Pool mining can use local stratum; LAN clients on your Wi‑Fi can connect.";
    } else if (status?.bloodstonedAlive === false) {
      const restarts = Number(status?.bloodstonedRestartAttempts) || 0;
      detail.textContent = restarts > 0
        ? `bloodstoned exited during download — native auto-restart ${restarts}/8. Keep the app in front on Wi‑Fi; disable battery saver for Bloodstone.`
        : "bloodstoned did not start — need ~400 MB free, stay on Wi‑Fi, plug in, then tap Start again. "
          + "Only 64-bit ARM phones are supported today.";
    } else if (snap.phase === "bootstrap" || displayPhase === "bootstrap") {
      const phase = String(status?.chainBootstrapPhase || "installing").trim();
      detail.textContent = phase === "extracting"
        ? "Unpacking verified chain blocks — much faster than syncing from scratch."
        : phase === "verifying"
          ? "Verifying chain snapshot checksum…"
          : "Downloading ~5 MB chain snapshot from Bloodstone — then bloodstoned catches up the tip.";
    } else if (snap.phase === "loading" || displayPhase === "loading") {
      detail.textContent = "bloodstoned is rebuilding the chain index (reindex) — can take 2–10 min on a phone. "
        + "Keep the app open on Wi‑Fi and plugged in; progress will move once blocks are verified.";
    } else if (status?.startError && (snap.phase === "unavailable" || isNodeStartStale())) {
      detail.textContent = String(status.startError);
    } else if (snap.phase === "starting" || displayPhase === "starting") {
      detail.textContent = status?.nodeStarting
        ? "Starting local node service and bloodstoned — keep the app open on Wi‑Fi and plugged in."
        : "Keep the app open on Wi‑Fi and plugged in. Progress updates every few seconds.";
    } else if (snap.phase === "idle" && snap.show) {
      detail.textContent = mode === NODE_MODES.FULL
        ? "Tap Start node above — full node installs a ~5 MB chain snapshot first, then syncs the tip."
        : "Tap Start node above — keep the app open on Wi‑Fi while bloodstoned starts.";
    } else {
      const headers = Number(status?.headerHeight) || 0;
      const tipLabel = snap.network > 0 ? snap.network : headers > 0 ? headers : "…";
      detail.textContent = `Downloading blocks ${snap.local > 0 ? snap.local : "…"} → ${tipLabel}`
        + (snap.chainBytes > 0 ? ` · ${formatBytes(snap.chainBytes)} on disk` : "")
        + " · keep app open on Wi‑Fi";
    }
  }
}

let statusPollTimer = null;

function trackBloodstonedDeath(status) {
  if (status?.bloodstonedAlive === false && status?.running) {
    if (!lastBloodstonedDeathAt) {
      lastBloodstonedDeathAt = Date.now();
      setChainDownloadPanelForced(true);
    }
    return;
  }
  if (status?.bloodstonedAlive !== false) {
    lastBloodstonedDeathAt = 0;
  }
}

export function initLocalNodeStatusPolling(onStatus) {
  if (!isCapacitorAndroid() && !isAndroidAppContext()) return;
  const tick = async () => {
    try {
      let status = await getLocalNodeStatus();
      if (status?.startError) {
        setNodeOnlyStatusMessage(status.startError, "error");
        setChainDownloadPanelForced(true);
      }
      trackBloodstonedDeath(status);
      if (status?.nodeStarting || isActivelyStartingNode(status)) {
        setChainDownloadPanelForced(true);
      }
      if (status?.running || status?.nodeStarting) {
        const local = Number(status.blockHeight) || 0;
        const tip = networkTipHeight(status);
        if (tip <= local || tip === 0) {
          const netH = await fetchNetworkBlockHeightFromUpstream();
          if (netH > 0) {
            status = {
              ...status,
              networkBlockHeight: Math.max(netH, Number(status.networkBlockHeight) || 0),
            };
          }
        }
      }
      updateLocalNodePanel(status);
      updateNodeSyncProgress(status);
      onStatus?.(status);
    } catch (err) {
      console.warn("local node status poll failed:", err?.message || err);
      if (isNodeOnlyActive() || chainDownloadPanelForced) {
        updateNodeSyncProgress(nodeStartPlaceholderStatus());
      }
    }
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
  if (mode === NODE_MODES.CONSENSUS) return "consensus";
  if (mode === NODE_MODES.CONSENSUS_WITNESS) return "consensus witness";
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
        "WorkManager wakes the node when 8+ blocks behind, syncs up to 30 minutes, then sleeps.";
    }
    return;
  }
  if (rpcEl) {
    rpcEl.textContent = status.rpcUrl || `${status.lanIp}:${status.rpcPort}`;
  }
  if (modeEl) {
    const syncPctNum = displaySyncPercent(status);
    const syncPct =
      syncPctNum != null && (status.mode === NODE_MODES.FULL || isConsensusMode(status.mode))
        ? ` · sync ${syncPctNum}%`
        : "";
    const height = status.blockHeight ? ` · height ${status.blockHeight}` : "";
    if (isConsensusMode(status.mode)) {
      modeEl.textContent = `${modeLabel(status.mode)} · consensus only · RPC ${status.rpcPort || 18340}${height}${syncPct}`;
    } else {
      const yp = status.stratumPortYespower || status.stratumPorts?.yespower || 3438;
      const neo = status.stratumPort || status.stratumPorts?.neoscrypt || 3437;
      modeEl.textContent = `${modeLabel(status.mode)} · LAN stratum :${neo} / yespower :${yp}${height}${syncPct}`;
    }
  }
  if (detailEl) {
    if (status.mode === "gateway" || status.bloodstonedAlive === false) {
      detailEl.textContent =
        " — bloodstoned did not start on this device (storage, binary, or crash). Chain download is off; stratum/RPC relay through the VPS. Plug in, free space, then restart mining.";
    } else if (isConsensusMode(status.mode)) {
      detailEl.textContent =
        status.mode === NODE_MODES.CONSENSUS
          ? " — pruned validator on device; participates in P2P consensus on :17333, no LAN stratum or mesh hosting."
          : " — lightweight witness; validates chain via outbound peers only, no stratum or mining on this phone.";
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
  { value: NODE_MODES.PRUNED, label: "Pruned (~550 MiB) — host lightweight node" },
  {
    value: NODE_MODES.LAN_CLIENT,
    label: "LAN client — mine from household full node (no chain download)",
  },
  {
    value: NODE_MODES.CONSENSUS,
    label: "Consensus — validate chain + P2P witness (~550 MiB, no stratum)",
  },
  {
    value: NODE_MODES.CONSENSUS_WITNESS,
    label: "Consensus witness — lightweight witness only (no stratum, no inbound P2P)",
  },
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
  try {
    const stored = localStorage.getItem(NODE_MODE_KEY);
    select.value = stored || select.value || NODE_MODES.PRUNED;
  } catch (_) {
    select.value = select.value || NODE_MODES.PRUNED;
  }
  setNodeModePreference(select.value);
  await whenCapacitorReady();
  const storage = await getNodeStorageInfo();
  if (hint) {
    if (isLanClientMode(select.value)) {
      hint.textContent = "Searches Wi‑Fi for a synced full node — no bloodstoned on this phone.";
    } else if (isConsensusMode(select.value)) {
      hint.textContent = select.value === NODE_MODES.CONSENSUS
        ? "Validates blocks and witnesses consensus — no LAN stratum. Mine via Pool or a household full node."
        : "Lightest witness mode — outbound sync only, no stratum hosting.";
    } else if (storage) {
      hint.textContent = `Free ${formatBytes(storage.freeBytes)} · full node needs ${formatBytes(storage.fullNodeMinFreeBytes)}+ free`;
      if (!storage.canRunFullNode) {
        hint.textContent += " — low free space; full node still runs but may sync slowly";
      }
    }
  }
  select.addEventListener("change", async () => {
    const mode = setNodeModePreference(select.value);
    if (!shouldHostLocalNode(mode)) {
      setNodeOnlyActive(false);
      setChainDownloadPanelForced(false);
    } else {
      setChainDownloadPanelForced(true);
    }
    const { configureMeshForNodeMode } = await import("./chain-mesh.js");
    await configureMeshForNodeMode(mode);
    let status = null;
    if (shouldHostLocalNode(mode)) {
      status = await startLocalNode({
        nodeMode: mode,
        foreground: true,
        waitForStratumMs: shouldHostLocalNode(mode) ? 0 : undefined,
      });
    } else {
      await stopLocalNode({ foregroundOnly: true });
      status = await getLocalNodeStatus();
      void listDiscoveredLanPeers({ fullOnly: true });
    }
    updateLocalNodePanel(status);
    updateNodeSyncProgress(status);
    updateNodeOnlyControls(status);
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
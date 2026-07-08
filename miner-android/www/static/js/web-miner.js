import {
  parseSha256dNotify,
  stratumDifficultyToTarget,
  stratumDifficultyToDisplayTargetHex,
  targetFromHex,
  targetToDisplayHex,
  formatHashrate,
} from "./mining-math.js";
import { localAssetPrefix, staticUrl, urlPrefix } from "./miner-paths.js";
import {
  canUseNativeStratum,
  createStratumTransport,
} from "./stratum-transport.js";
import {
  fleetDeviceId,
  fleetDeviceModel,
  isCapacitorAndroid,
  loadFleetIdentity,
  refreshFleetStats,
  setFleetNodeStatus,
  startFleetNode,
  stopFleetNode,
  transportKind,
  updateFleetPanel,
} from "./device-fleet.js";
import {
  canMineOffline,
  chainMeshMeta,
  drainPendingShares,
  getCachedMiningSession,
  pendingShareCount,
  queuePendingShare,
  resolveDeviceId,
  saveJobCacheLocal,
  startChainMeshPeer,
} from "./chain-mesh.js";
import { waitForBloodstoneBridge } from "./capacitor-ready.js";
import { initNodeDiagnostics } from "./node-diagnostics.js";
import { initMeshChainRestoreUi } from "./mesh-chain-restore.js";
import {
  ensureFullNodeForeground,
  ensureLanRegistration,
  startLanRegistrationHeartbeat,
  getLocalNodeStatus,
  getNodeModePreference,
  discoverMdnsLanNodes,
  initLanPeerDiscovery,
  initLocalNodeModeUi,
  initLocalNodeStatusPolling,
  ensureForegroundChainSync,
  needsInitialChainSync,
  isLanClientMode,
  isNodeSyncing,
  listDiscoveredLanPeers,
  localStratumAvailable,
  NODE_MODES,
  resolveAndroidStratumOptions,
  shouldHostLocalNode,
  supportsOnDeviceWallet,
  startLocalNode,
  stopLocalNode,
  initNodeOnlyControls,
  isNodeOnlyActive,
  updateNodeOnlyControls,
  updateLanPeersPanel,
  updateLocalNodePanel,
  waitForLocalNodeStratum,
} from "./local-node.js";
import { initLocalWalletPanel } from "./local-wallet.js";
import {
  initNodeNetworkStats,
  refreshNodeNetworkStats,
} from "./node-network-stats.js";
import {
  initDeviceNetworkPanel,
  refreshDeviceNetworkPanel,
} from "./device-network-info.js";
import { initMiningSetupInstructions } from "./mining-setup-instructions.js";
import { isAndroidAppContext, whenCapacitorReady } from "./capacitor-ready.js";
import {
  androidPowerBlockReason,
  androidPowerMiningRequired,
  cachedAndroidPowerStatus,
  initAndroidPowerGuard,
  isAndroidPowerMiningAllowed,
  onAndroidPowerChange,
  refreshAndroidPowerStatus,
} from "./power-guard.js";
import {
  cachedNetworkNodes,
  initRegisterLanButton,
  refreshNetworkNodes,
  startNetworkNodesPolling,
} from "./network-nodes.js";
import {
  initThermalGuard,
  onThermalGuardAction,
  refreshThermalStatus,
} from "./thermal-guard.js";
import { initAndroidAppUpdate, initAndroidUpdateOptions } from "./app-update.js";
import {
  deferBatteryExemptionPrompt,
  isMobileWebBrowser,
  noteMiningHashrate,
  startBackgroundMining,
  stopBackgroundMining,
} from "./background-mining.js";

const MAX_MINER_THREADS = 64;
const THREADS_STORAGE_KEY = "bloodstone-miner-threads";
const ROD_ADDR_STORAGE_KEY = "bloodstone-web-miner-rod-address";
const STONE_ADDR_STORAGE_KEY = "bloodstone-web-miner-stone-address";
const WORKER_SUFFIX_STORAGE_KEY = "bloodstone-web-miner-worker-suffix";
const MINING_RESUME_KEY = "bloodstone-mining-resume";
const MINING_RESUME_MAX_AGE_MS = 30 * 60 * 1000;
const ROD_ADDR_RE = /^[XR][1-9A-HJ-NP-Za-km-z]{25,39}$/;
const STONE_LEGACY_RE = /^S[1-9A-HJ-NP-Za-km-z]{25,34}$/;
const STONE_BECH32_RE = /^stone1[0-9a-z]{20,}$/i;
const PLACEHOLDER_ADDR_RE =
  /^YOUR[_\s]*(STONE|ROD)[_\s]*(ADDRESS|WALLET)?$/i;

const MAX_RECONNECT_DELAY_MS = 30000;
const TARGET_SHARE_INTERVAL_SEC = 11;
const ANDROID_POOL_SUBMIT_INTERVAL_SEC = 30;
const PENDING_SHARE_FLUSH_CHECK_MS = 5000;
const NEOSCRYPT_XAYA = "neoscrypt-xaya";
const SHA256D = "sha256d";
const BROWSER_DIFF_MIN = {
  [NEOSCRYPT_XAYA]: 2.5e-10,
  yespower: 2.5e-10,
  [SHA256D]: 1e-8,
};
const BROWSER_DIFF_MAX = {
  [NEOSCRYPT_XAYA]: 1e-8,
  yespower: 1e-7,
  [SHA256D]: 1e-4,
};
const BROWSER_DIFF_SCALE = {
  [NEOSCRYPT_XAYA]: 2e-13,
  yespower: 4e-13,
  [SHA256D]: 1e-10,
};

const state = {
  ws: null,
  workers: [],
  running: false,
  reconnecting: false,
  reconnectTimer: null,
  reconnectAttempts: 0,
  userStopped: false,
  algo: NEOSCRYPT_XAYA,
  address: "",
  msgId: 1,
  extranonce1: "",
  pending: new Map(),
  job: null,
  targetHex: "",
  blockTargetHex: "",
  sharesAccepted: 0,
  sharesRejected: 0,
  blocksFound: 0,
  totalHashrate: 0,
  poolDifficultySet: false,
  exactShareTarget: false,
  recentShareKeys: new Set(),
  miningMode: "pool",
  lastDiffSuggest: 0,
  lastPoolShareSubmitAt: 0,
  localYesCount: 0,
  yesSinceHeartbeat: 0,
  mobileHeartbeatTimer: null,
  offlineMining: false,
  flushingPending: false,
};

let pendingShareFlushTimer = null;
let pendingShareFlushInterval = null;

const MOBILE_HEARTBEAT_MS = 90000;
let cachedReportDeviceId = null;

async function reportDeviceId() {
  if (cachedReportDeviceId) return cachedReportDeviceId;
  try {
    cachedReportDeviceId = await resolveDeviceId();
  } catch (_) {
    cachedReportDeviceId = fleetDeviceId() || "";
  }
  return cachedReportDeviceId || fleetDeviceId() || "";
}
let fleetStatsCache = null;

function isStandaloneApp() {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}

function minerKind() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("app") === "android") return "android";
  if (!isStandaloneApp()) return "browser";
  const ua = navigator.userAgent || "";
  if (/android/i.test(ua)) return "android";
  if (/iphone|ipad|ipod/i.test(ua)) return "ios";
  return "browser";
}

function resumeWorkersAfterBackground() {
  if (!state.running || !state.job || !state.targetHex) return;
  broadcastToWorkers({
    type: "job",
    job: state.job,
    targetHex: state.targetHex,
    running: true,
  });
  broadcastToWorkers({
    type: "start",
    job: state.job,
    targetHex: state.targetHex,
  });
}

function $(id) {
  return document.getElementById(id);
}

function apiUrl(path) {
  const prefix = document.body?.dataset?.urlPrefix || "";
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${prefix}${normalized}`;
}

function log(line, kind = "info") {
  const el = $("miner-log");
  if (!el) return;
  const row = document.createElement("div");
  row.className = `log-line log-${kind}`;
  row.textContent = `[${new Date().toLocaleTimeString()}] ${line}`;
  el.prepend(row);
  while (el.children.length > 80) {
    el.removeChild(el.lastChild);
  }
}

function currentRewardTarget() {
  const el = $("miner-reward");
  if (!el || currentAlgo() !== NEOSCRYPT_XAYA) return "stone";
  return el.value === "rod" ? "rod" : "stone";
}

function isRodMining() {
  return currentAlgo() === NEOSCRYPT_XAYA && currentRewardTarget() === "rod";
}

function isPlaceholderAddress(addr) {
  const s = (addr || "").trim();
  if (!s) return true;
  if (/^(x|solo)$/i.test(s)) return true;
  const compact = s.replace(/[\s_]+/g, "_");
  if (PLACEHOLDER_ADDR_RE.test(compact)) return true;
  if (/^your[_\s]*(stone|rod)/i.test(compact)) return true;
  return false;
}

function isValidStoneAddress(addr) {
  const s = (addr || "").trim();
  if (!s || isPlaceholderAddress(s)) return false;
  return STONE_LEGACY_RE.test(s) || STONE_BECH32_RE.test(s);
}

function validateMinerAddress(addr) {
  if (isRodMining()) {
    if (!addr || isPlaceholderAddress(addr)) {
      return "Enter a ROD core wallet address (not a placeholder)";
    }
    if (!ROD_ADDR_RE.test(addr)) {
      return "Enter a valid ROD core wallet address (X… or R…)";
    }
    return null;
  }
  if (!addr || isPlaceholderAddress(addr)) {
    return "Enter your STONE payout address (S… or stone1…)";
  }
  if (!isValidStoneAddress(addr)) {
    return "Enter a valid STONE address (legacy S… or bech32 stone1…)";
  }
  return null;
}

function sanitizeMinerAddressField() {
  const input = $("miner-address");
  if (!input) return;
  const value = input.value.trim();
  if (!value || isPlaceholderAddress(value)) {
    input.value = "";
  } else if (!isRodMining() && !isValidStoneAddress(value)) {
    input.value = "";
  } else if (isRodMining() && !ROD_ADDR_RE.test(value)) {
    input.value = "";
  }
}

function updateStartButtonState() {
  const btn = $("btn-start");
  if (!btn || state.running) return;
  const err = validateMinerAddress(($("miner-address")?.value || "").trim());
  const powerErr = androidPowerBlockReason();
  const blocked = Boolean(err || powerErr);
  btn.disabled = blocked;
  btn.title = powerErr || err || "";
}

async function androidStratumConnectOptions(extra = {}) {
  if (!isAndroidAppContext()) return extra;
  const opts = await resolveAndroidStratumOptions(
    state.miningMode || "pool",
    stratumPoolKey(),
  );
  return { ...opts, ...extra };
}

function stratumPoolKey() {
  if (isRodMining()) return "rod_neoscrypt";
  if (currentAlgo() === NEOSCRYPT_XAYA) return "neoscrypt";
  return currentAlgo();
}

function nextId() {
  const id = state.msgId;
  state.msgId += 1;
  return id;
}

function stratumUserAgent() {
  if (isAndroidAppContext()) return "bloodstone-android-miner";
  return "bloodstone-web-miner";
}

function minPoolShareSubmitMs() {
  if (state.miningMode !== "pool") return 0;
  const sec = isAndroidAppContext()
    ? ANDROID_POOL_SUBMIT_INTERVAL_SEC
    : TARGET_SHARE_INTERVAL_SEC;
  return Math.max(9000, sec * 1000);
}

function poolShareSubmitReady() {
  if (state.miningMode !== "pool") return true;
  const minGap = minPoolShareSubmitMs();
  const now = Date.now();
  return !state.lastPoolShareSubmitAt || now - state.lastPoolShareSubmitAt >= minGap;
}

function poolSharePacingSec() {
  return Math.max(1, Math.ceil(minPoolShareSubmitMs() / 1000));
}

function schedulePendingShareFlush() {
  if (!state.running || state.offlineMining) return;
  const minGap = minPoolShareSubmitMs();
  const last = state.lastPoolShareSubmitAt || 0;
  const waitMs = last ? Math.max(400, minGap - (Date.now() - last) + 250) : 400;
  if (pendingShareFlushTimer) clearTimeout(pendingShareFlushTimer);
  pendingShareFlushTimer = setTimeout(() => {
    pendingShareFlushTimer = null;
    void flushQueuedShares();
  }, waitMs);
}

function startPendingShareFlushLoop() {
  stopPendingShareFlushLoop();
  pendingShareFlushInterval = setInterval(() => {
    if (!state.running || state.offlineMining || !state.stratum?.isOpen?.()) return;
    if (pendingShareCount() > 0 && poolShareSubmitReady()) {
      void flushQueuedShares();
    }
  }, PENDING_SHARE_FLUSH_CHECK_MS);
}

function stopPendingShareFlushLoop() {
  if (pendingShareFlushTimer) {
    clearTimeout(pendingShareFlushTimer);
    pendingShareFlushTimer = null;
  }
  if (pendingShareFlushInterval) {
    clearInterval(pendingShareFlushInterval);
    pendingShareFlushInterval = null;
  }
}

function workerShareEmitMinMs() {
  return minPoolShareSubmitMs() || 60000;
}

function suggestDifficultyFromHashrate() {
  if (!(state.totalHashrate > 0)) return null;
  const algo = state.algo || NEOSCRYPT_XAYA;
  const scale = BROWSER_DIFF_SCALE[algo] || 2e-13;
  const lo = BROWSER_DIFF_MIN[algo] || 2.5e-10;
  const hi = BROWSER_DIFF_MAX[algo] || 1e-7;
  const raw = state.totalHashrate * TARGET_SHARE_INTERVAL_SEC * scale;
  return Math.max(lo, Math.min(hi, raw));
}

async function maybeSuggestDifficulty(force = false) {
  if (!state.running || state.miningMode !== "pool" || !state.stratum?.isOpen?.()) return;
  const now = Date.now();
  if (!force && now - state.lastDiffSuggest < 60000) return;
  const diff = suggestDifficultyFromHashrate();
  if (!(diff > 0)) return;
  try {
    await stratumSend("mining.suggest_difficulty", [diff]);
    state.lastDiffSuggest = now;
    log(`Phone difficulty adjusted (${diff.toExponential(2)})`, "success");
  } catch (err) {
    log(`Difficulty suggest failed: ${err.message}`, "warn");
  }
}

function registerStratumPending(id, method) {
  return new Promise((resolve, reject) => {
    state.pending.set(id, { resolve, reject, method });
    setTimeout(() => {
      if (state.pending.has(id)) {
        state.pending.delete(id);
        reject(new Error(`timeout waiting for ${method}`));
      }
    }, 30000);
  });
}

async function stratumSend(method, params = []) {
  const id = nextId();
  const pending = registerStratumPending(id, method);
  await state.stratum.send({ id, method, params });
  return pending;
}

async function stratumSendBatch(requests) {
  const entries = requests.map(({ method, params = [] }) => ({
    id: nextId(),
    method,
    params,
    pending: null,
  }));
  entries.forEach((entry) => {
    entry.pending = registerStratumPending(entry.id, entry.method);
  });
  for (const entry of entries) {
    await state.stratum.send({ id: entry.id, method: entry.method, params: entry.params });
  }
  const results = [];
  for (const entry of entries) {
    results.push(await entry.pending);
  }
  return results;
}

function persistMiningResume() {
  if (!state.running || state.userStopped) return;
  try {
    localStorage.setItem(
      MINING_RESUME_KEY,
      JSON.stringify({
        address: state.address,
        algo: state.algo,
        miningMode: state.miningMode,
        workerSuffix: state.workerSuffix,
        threads: $("miner-threads")?.value || "",
        ts: Date.now(),
      }),
    );
  } catch (_) {
    /* ignore */
  }
}

function clearMiningResume() {
  try {
    localStorage.removeItem(MINING_RESUME_KEY);
  } catch (_) {
    /* ignore */
  }
}

async function maybeResumeMining() {
  if (!isAndroidAppContext() || state.running) return false;
  const power = await refreshAndroidPowerStatus();
  if (!isAndroidPowerMiningAllowed(power)) {
    clearMiningResume();
    return false;
  }
  let saved = null;
  try {
    const raw = localStorage.getItem(MINING_RESUME_KEY);
    if (!raw) return false;
    saved = JSON.parse(raw);
  } catch (_) {
    clearMiningResume();
    return false;
  }
  if (!saved?.address || Date.now() - Number(saved.ts || 0) > MINING_RESUME_MAX_AGE_MS) {
    clearMiningResume();
    return false;
  }
  const addrEl = $("miner-address");
  if (addrEl && !addrEl.value.trim()) {
    addrEl.value = saved.address;
  }
  const workerEl = $("miner-worker");
  if (workerEl && !workerEl.value.trim() && saved.workerSuffix) {
    workerEl.value = saved.workerSuffix;
  }
  const algoEl = $("miner-algo");
  if (algoEl && saved.algo) {
    algoEl.value = saved.algo;
  }
  const modeEl = $("miner-mode");
  if (modeEl && saved.miningMode) {
    modeEl.value = saved.miningMode === "solo" ? "solo" : "pool";
  }
  const threadsEl = $("miner-threads");
  if (threadsEl && saved.threads) {
    threadsEl.value = saved.threads;
  }
  updateModeUi();
  updateRewardUi();
  updateStartButtonState();
  log("Server reconnected — resuming mining…", "warn");
  clearMiningResume();
  await startMining();
  return true;
}

function persistMiningSessionCache() {
  if (!state.job) return;
  const mesh = chainMeshMeta();
  saveJobCacheLocal({
    job: state.job,
    targetHex: state.targetHex,
    blockTargetHex: state.blockTargetHex,
    extranonce1: state.extranonce1,
    algo: state.algo,
    miningMode: state.miningMode,
    poolDifficultySet: state.poolDifficultySet,
    block_height: mesh?.block_height || 0,
    best_block_hash: mesh?.best_block_hash || "",
    chunks_held: mesh?.chunks_held || 0,
  });
}

function applyShareTargetHex(hex) {
  const target = targetFromHex(hex);
  state.targetHex = state.algo === SHA256D
    ? targetToDisplayHex(target)
    : target.toString(16).padStart(64, "0");
  state.poolDifficultySet = true;
  persistMiningSessionCache();
}

function targetHexFromDifficulty(stratumDiff) {
  if (state.algo === SHA256D) {
    return stratumDifficultyToDisplayTargetHex(Number(stratumDiff), state.algo);
  }
  const target = stratumDifficultyToTarget(Number(stratumDiff), state.algo);
  return target.toString(16).padStart(64, "0");
}

function parseJob(notifyParams) {
  if (state.algo === SHA256D) {
    return parseSha256dNotify(notifyParams, state.extranonce1);
  }
  const [jobId, , headerPrefix, , , , nbits, ntime] = notifyParams;
  return {
    jobId,
    headerPrefix,
    nbits,
    ntime,
    extranonce1: state.extranonce1,
    algo: state.algo,
  };
}

function buildSubmitParams(share) {
  if (state.algo === SHA256D) {
    return [
      state.address,
      share.jobId,
      share.extranonce2,
      share.ntime,
      share.nonce,
      share.version || "01000000",
    ];
  }
  return [
    state.address,
    share.jobId,
    share.extranonce2,
    share.ntime,
    share.nonce,
    share.hash,
  ];
}

function broadcastToWorkers(message) {
  state.workers.forEach((worker) => worker.postMessage(message));
}

async function submitShare(share) {
  if (!state.running) return;
  if (state.offlineMining) {
    const n = queuePendingShare({
      address: state.address,
      algo: state.algo,
      miningMode: state.miningMode,
      ...share,
    });
    state.sharesAccepted += 1;
    log(`Offline share queued (${share.hash.slice(0, 16)}…) — ${n} pending`, "success");
    updateStats();
    return;
  }
  if (!state.stratum?.isOpen?.()) return;
  if (!poolShareSubmitReady()) {
    const n = queuePendingShare({
      address: state.address,
      algo: state.algo,
      miningMode: state.miningMode,
      ...share,
    });
    log(
      `Share buffered (pool pacing ~${poolSharePacingSec()}s) — ${n} pending, auto-submit soon`,
      "warn",
    );
    schedulePendingShareFlush();
    return;
  }
  const shareKey = `${share.jobId}:${share.extranonce2}:${share.ntime}:${share.nonce}`;
  if (state.recentShareKeys.has(shareKey)) {
    return;
  }
  state.recentShareKeys.add(shareKey);
  if (state.recentShareKeys.size > 500) {
    state.recentShareKeys.clear();
    state.recentShareKeys.add(shareKey);
  }
  try {
    const result = await stratumSend("mining.submit", buildSubmitParams(share));
    if (result === true) {
      state.sharesAccepted += 1;
      if (state.miningMode === "pool") {
        state.lastPoolShareSubmitAt = Date.now();
      }
      if (state.miningMode === "solo") {
        log(`Solo solution accepted (${share.hash.slice(0, 16)}…)`, "success");
      } else {
        log(`Pool share accepted (${share.hash.slice(0, 16)}…)`, "success");
      }
      void import("./mesh-packet-relay.js")
        .then((m) =>
          m.relayMeshPacketOnShare(share, {
            worker: state.worker || "",
            model: navigator.userAgent.slice(0, 80),
          }),
        )
        .catch(() => {});
    } else {
      const pacedReject =
        state.miningMode === "pool"
        && state.lastPoolShareSubmitAt
        && Date.now() - state.lastPoolShareSubmitAt < minPoolShareSubmitMs() + 3000;
      if (pacedReject) {
        queuePendingShare({
          address: state.address,
          algo: state.algo,
          miningMode: state.miningMode,
          ...share,
        });
        schedulePendingShareFlush();
        log("Share buffered (pool pacing) — will auto-retry", "warn");
      } else {
        state.sharesRejected += 1;
        log(
          `Share rejected (job ${share.jobId.slice(-8)} — stale work or below pool difficulty)`,
          "warn",
        );
        void maybeSuggestDifficulty(true);
      }
    }
    updateStats();
  } catch (err) {
    state.sharesRejected += 1;
    log(`Submit failed: ${err.message}`, "error");
    updateStats();
  }
}

function handleStratumMessage(raw) {
  let msg;
  try {
    msg = JSON.parse(raw);
  } catch (_err) {
    return;
  }

  if (msg.id !== null && msg.id !== undefined && state.pending.has(msg.id)) {
    const pending = state.pending.get(msg.id);
    state.pending.delete(msg.id);
    if (msg.error) {
      pending.reject(new Error(JSON.stringify(msg.error)));
    } else {
      pending.resolve(msg.result);
    }
    return;
  }

  if (msg.method === "mining.set_share_target") {
    try {
      applyShareTargetHex(msg.params[0]);
      state.exactShareTarget = true;
    } catch (_err) {
      return;
    }
    state._jobWaiter?.();
    if (state.job && state.running && state.workers.length) {
      broadcastToWorkers({
        type: "job",
        job: state.job,
        targetHex: state.targetHex,
        running: true,
      });
    }
    return;
  }

  if (msg.method === "mining.set_difficulty") {
    const diff = Number(msg.params[0]);
    if (!state.exactShareTarget) {
      state.targetHex = targetHexFromDifficulty(diff);
      state.poolDifficultySet = true;
      persistMiningSessionCache();
    }
    if (state.miningMode === "solo") {
      log(`Solo block difficulty set (${diff})`);
    } else {
      log(`Pool share difficulty set (${diff})`);
    }
    state._jobWaiter?.();
    if (state.job && state.running && state.workers.length) {
      broadcastToWorkers({
        type: "job",
        job: state.job,
        targetHex: state.targetHex,
        running: true,
      });
    }
    return;
  }

  if (msg.method === "mining.set_block_target") {
    state.blockTargetHex = String(msg.params[0] || "").padStart(64, "0");
    const height = msg.params[1];
    log(`Network block target for height ${height} (much harder than pool shares)`);
    return;
  }

  if (msg.method === "mining.block_result") {
    const info = msg.params?.[0] || {};
    const height = info.height ?? "?";
    const hash = String(info.hash || "").slice(0, 16);
    if (info.accepted) {
      state.blocksFound += 1;
      log("YAY!!!", "success");
      log(`BLOCK CREDITED at height ${height} (${hash}…)`, "success");
    } else if (info.reason === "stale") {
      log(`Block candidate stale at height ${height} — new job issued`, "warn");
    } else {
      log(`Block candidate rejected at height ${height} (${hash}…)`, "warn");
    }
    updateStats();
    return;
  }

  if (msg.method === "mining.stop") {
    log("Pool stopped work — waiting for next job", "warn");
    state.job = null;
    broadcastToWorkers({ type: "stop" });
    return;
  }

  if (msg.method === "mining.notify") {
    state.job = parseJob(msg.params);
    if (state.algo === SHA256D) {
      log(`New SHA256d job ${state.job.jobId} @ ntime ${state.job.ntime}`);
    } else {
      log(`New job ${state.job.jobId} @ ntime ${state.job.ntime}`);
    }
    persistMiningSessionCache();
    state._jobWaiter?.();
    if (state.running && state.workers.length && state.poolDifficultySet && state.targetHex) {
      broadcastToWorkers({
        type: "job",
        job: state.job,
        targetHex: state.targetHex,
        running: true,
      });
    }
  }
}

function updatePoolPendingDisplay(text, muted = false) {
  const el = $("stat-pool-pending");
  if (!el) return;
  el.textContent = text;
  el.classList.toggle("muted", muted);
}

function saveStonePayoutAddress(address) {
  if (isRodMining()) return;
  const addr = (address || "").trim();
  if (!isValidStoneAddress(addr)) return;
  try {
    localStorage.setItem(STONE_ADDR_STORAGE_KEY, addr);
  } catch (_) {
    /* ignore */
  }
}

function sanitizeWorkerSuffix(raw) {
  const cleaned = String(raw || "")
    .trim()
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32);
  return cleaned;
}

function defaultWorkerSuffix() {
  const kind = minerKind();
  if (kind === "android" || kind === "ios") {
    const id = fleetDeviceId();
    if (id) return sanitizeWorkerSuffix(id.slice(0, 12)) || kind;
    return kind;
  }
  return "web";
}

function resolveWorkerSuffix() {
  const fromInput = sanitizeWorkerSuffix($("miner-worker")?.value || "");
  if (fromInput) return fromInput;
  try {
    const saved = sanitizeWorkerSuffix(localStorage.getItem(WORKER_SUFFIX_STORAGE_KEY) || "");
    if (saved) return saved;
  } catch (_) {
    /* ignore */
  }
  return defaultWorkerSuffix();
}

function saveWorkerSuffix(suffix) {
  const cleaned = sanitizeWorkerSuffix(suffix);
  if (!cleaned) return;
  try {
    localStorage.setItem(WORKER_SUFFIX_STORAGE_KEY, cleaned);
  } catch (_) {
    /* ignore */
  }
}

function buildStratumUser(address, workerSuffix) {
  const addr = (address || "").trim();
  const suffix = sanitizeWorkerSuffix(workerSuffix);
  if (!addr) return "";
  if (!suffix || suffix === addr) return addr;
  return `${addr}.${suffix}`;
}

function resolvePayoutAddress() {
  const fromInput = ($("miner-address")?.value || "").trim();
  if (fromInput && !isPlaceholderAddress(fromInput) && isValidStoneAddress(fromInput)) {
    return fromInput;
  }
  const fromState = (state.address || "").trim();
  if (fromState && isValidStoneAddress(fromState)) return fromState;
  const poolLookup = document.getElementById("pool-address-lookup")?.value?.trim();
  if (poolLookup && isValidStoneAddress(poolLookup)) return poolLookup;
  try {
    const saved = localStorage.getItem(STONE_ADDR_STORAGE_KEY);
    if (saved && isValidStoneAddress(saved)) return saved;
  } catch (_) {
    /* ignore */
  }
  return "";
}

function formatPoolPendingEstimate(data, algo) {
  const row = data.miner_next_block?.per_algo?.[algo] || {};
  const est = Number(row.estimated_stone || 0);
  const pct = Number(row.pct || 0);
  const height = data.round_heights?.[algo];
  const credited = Number(data.miner_balance?.pending_stone || 0);
  const parts = [];
  if (credited > 0) {
    parts.push(`${credited.toFixed(4)} STONE credited`);
  }
  if (height && (pct > 0 || est > 0)) {
    parts.push(`~${est.toFixed(4)} STONE this round (${pct.toFixed(2)}%)`);
  } else if (height && credited <= 0) {
    parts.push(`round ${height} · no shares yet`);
  }
  return parts;
}

async function refreshPoolPending() {
  if (currentMiningMode() === "solo") {
    updatePoolPendingDisplay("Solo mode — no pool round", true);
    return;
  }
  if (isRodMining()) {
    updatePoolPendingDisplay("ROD mainnet — blocks pay ROD (not STONE pool)", true);
    return;
  }
  const addr = resolvePayoutAddress();
  if (!addr) {
    updatePoolPendingDisplay("Set payout address for pool estimate", true);
    return;
  }
  if (refreshPoolPending._inFlight) return;
  refreshPoolPending._inFlight = true;
  const hadEstimate = refreshPoolPending._hasEstimate;
  if (!hadEstimate) {
    updatePoolPendingDisplay("Loading pool estimate…", true);
  }
  try {
    const res = await fetch(
      apiUrl(`/api/pool/miner-estimate?address=${encodeURIComponent(addr)}`),
    );
    if (!res.ok) {
      updatePoolPendingDisplay("Pool estimate unavailable — retrying…", true);
      return;
    }
    const data = await res.json();
    if (data.error) {
      updatePoolPendingDisplay(data.error, true);
      return;
    }
    if (data._loading) {
      const partial = formatPoolPendingEstimate(data, currentAlgo());
      if (partial.length) {
        updatePoolPendingDisplay(`${partial.join(" · ")} · updating…`, true);
      }
      window.setTimeout(refreshPoolPending, 3000);
      return;
    }
    const parts = formatPoolPendingEstimate(data, currentAlgo());
    if (!parts.length) {
      updatePoolPendingDisplay("No pool earnings for this address yet", true);
      refreshPoolPending._hasEstimate = false;
      return;
    }
    updatePoolPendingDisplay(parts.join(" · "), false);
    refreshPoolPending._hasEstimate = true;
  } catch (_) {
    if (!hadEstimate) {
      updatePoolPendingDisplay("Pool estimate unavailable — retrying…", true);
    }
  } finally {
    refreshPoolPending._inFlight = false;
  }
}

async function sendMobileContribution(extra = {}) {
  if (!state.running || state.miningMode !== "pool" || isRodMining()) return;
  const address = ($("miner-address")?.value || state.address || "").trim();
  if (!address) return;
  const yesCount = extra.yes_count ?? state.yesSinceHeartbeat;
  const connectedSec = extra.connected_sec ?? MOBILE_HEARTBEAT_MS / 1000;
  try {
    const worker = buildStratumUser(address, resolveWorkerSuffix());
    const deviceId = await reportDeviceId();
    const res = await fetch(apiUrl("/api/pool/mobile-contribution"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        address,
        worker,
        algo: state.algo,
        hashrate: state.totalHashrate,
        yes_count: yesCount,
        connected_sec: connectedSec,
        miner_kind: minerKind(),
        transport: transportKind(state.stratum),
        device_id: deviceId || undefined,
        device_model: fleetDeviceModel() || undefined,
        job_height: state.job?.jobId ? undefined : undefined,
      }),
    });
    if (res.ok) {
      state.yesSinceHeartbeat = Math.max(
        0,
        state.yesSinceHeartbeat - Number(yesCount || 0),
      );
    }
  } catch (_) {
    /* retry on next heartbeat */
  }
}

function startMobileHeartbeat() {
  stopMobileHeartbeat();
  if (state.miningMode !== "pool" || isRodMining()) return;
  state.mobileHeartbeatTimer = setInterval(() => {
    void sendMobileContribution();
  }, MOBILE_HEARTBEAT_MS);
}

function stopMobileHeartbeat() {
  if (state.mobileHeartbeatTimer) {
    clearInterval(state.mobileHeartbeatTimer);
    state.mobileHeartbeatTimer = null;
  }
}

async function refreshAsicSharePublic() {
  const panel = $("asic-share-public");
  if (!panel) return;
  try {
    const res = await fetch(apiUrl("/api/pool/dashboard"));
    if (!res.ok) return;
    const data = await res.json();
    const s = data?.asic_mobile_subsidy;
    if (!s || data.error) return;
    const totalEl = $("asic-share-total");
    const mobileEl = $("asic-share-mobile");
    if (totalEl) {
      totalEl.textContent = `${Number(s.total_shared_stone || 0).toFixed(4)} STONE shared`;
    }
    if (mobileEl) {
      mobileEl.textContent = `${Number(s.mobile_shared_stone || 0).toFixed(4)} STONE`;
    }
    panel.hidden = false;
  } catch (_) {
    /* keep last value */
  }
}

function updateStats() {
  $("stat-hashrate").textContent = formatHashrate(state.totalHashrate);
  $("stat-shares").textContent = `${state.sharesAccepted} / ${state.sharesRejected}`;
  const blocksEl = $("stat-blocks");
  if (blocksEl) blocksEl.textContent = String(state.blocksFound);
  $("stat-status").textContent = state.running ? "Mining" : "Stopped";
  $("stat-job").textContent = state.job
    ? `${state.job.jobId}${state.offlineMining ? " (cached)" : ""}`
    : "—";
  if (state.offlineMining && $("stat-status")) {
    $("stat-status").textContent = "Offline (local VPS)";
  }
  refreshPoolPending();
}

function clearReconnectTimer() {
  if (state.reconnectTimer) {
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
  }
}

function resetStratumSession() {
  state.pending.clear();
  state.msgId = 1;
  state.extranonce1 = "";
  state.job = null;
  state.targetHex = "";
  state.blockTargetHex = "";
  state.poolDifficultySet = false;
  state.exactShareTarget = false;
  state._jobWaiter = null;
  if (state.stratum) {
    state.stratum.onclose = null;
    state.stratum.onerror = null;
    state.stratum.onmessage = null;
    try {
      void state.stratum.close();
    } catch (_) {
      /* ignore */
    }
    state.stratum = null;
  }
}

function schedulePoolReconnect(reason) {
  if (!state.running || state.userStopped || state.reconnectTimer) {
    return;
  }
  const delay = Math.min(
    1000 * 2 ** state.reconnectAttempts,
    MAX_RECONNECT_DELAY_MS,
  );
  state.reconnectAttempts += 1;
  const seconds = Math.max(1, Math.round(delay / 1000));
  log(`${reason} — reconnecting in ${seconds}s…`, "warn");
  $("stat-status").textContent = "Reconnecting…";
  state.reconnectTimer = setTimeout(() => {
    state.reconnectTimer = null;
    reconnectPool().catch(() => {});
  }, delay);
}

async function startOfflineMiningSession() {
  const session = getCachedMiningSession();
  if (!session?.job || !session.targetHex) {
    throw new Error("No cached pool job — connect to VPS once to seed local node");
  }
  state.offlineMining = true;
  state.job = session.job;
  state.extranonce1 = session.extranonce1 || state.extranonce1;
  state.algo = session.algo || state.algo;
  state.targetHex = session.targetHex;
  state.blockTargetHex = session.blockTargetHex || "";
  state.poolDifficultySet = Boolean(session.poolDifficultySet ?? session.targetHex);
  state.exactShareTarget = true;
  const mesh = chainMeshMeta();
  log(
    `Local VPS node — mining offline on cached job ${state.job.jobId} (chain tip ~${mesh?.block_height || "?"})`,
    "success",
  );
  $("stat-status").textContent = "Offline (local VPS)";
}

async function flushQueuedShares() {
  if (state.flushingPending || !state.stratum?.isOpen?.()) return;
  state.flushingPending = true;
  try {
    const pending = await drainPendingShares();
    if (!pending.length) return;
    log(`Submitting ${pending.length} buffered share(s) to pool…`);
    let submitted = 0;
    for (const share of pending) {
      if (!poolShareSubmitReady()) {
        for (let i = submitted; i < pending.length; i += 1) {
          queuePendingShare(pending[i]);
        }
        schedulePendingShareFlush();
        break;
      }
      try {
        const result = await stratumSend("mining.submit", buildSubmitParams(share));
        if (result === true) {
          state.sharesAccepted += 1;
          submitted += 1;
          if (state.miningMode === "pool") {
            state.lastPoolShareSubmitAt = Date.now();
          }
        } else {
          queuePendingShare(share);
          schedulePendingShareFlush();
        }
      } catch (_) {
        queuePendingShare(share);
        schedulePendingShareFlush();
      }
    }
    updateStats();
  } finally {
    state.flushingPending = false;
  }
}

async function connectStratum(options = {}) {
  state.offlineMining = false;
  const androidOpts = await androidStratumConnectOptions();
  if (androidOpts.chainSyncing && androidOpts.forceVps && !options._syncLogged) {
    log(
      "Chain still downloading — mining via VPS pool until the local node finishes sync",
      "warn",
    );
    options = { ...options, _syncLogged: true };
  }
  state.stratum = await createStratumTransport(stratumPoolKey(), {
    ...androidOpts,
    ...options,
    miningMode: state.miningMode,
  });
  state.stratum.onmessage = (data) => handleStratumMessage(data);
  state.stratum.onerror = () => {
    /* connect() promise handles initial failure */
  };
  state.stratum.onclose = (detail) => {
    if (!state.running || state.userStopped) return;
    state.stratum = null;
    schedulePoolReconnect(`Pool connection closed${detail || ""}`);
  };
  try {
    await state.stratum.connect();
  } catch (err) {
    if (state.stratum?.kind === "websocket" && isAndroidAppContext()) {
      throw new Error(
        `Android app must use native stratum TCP, not WebSocket (${err.message}) — restart the app`,
      );
    }
    const androidOpts = await androidStratumConnectOptions(options);
    if (
      !options.forceVps
      && !androidOpts.noVpsFallback
      && canUseNativeStratum()
    ) {
      log(`LAN stratum failed (${err.message}) — trying VPS pool`, "warn");
      try {
        await state.stratum.close?.();
      } catch (_) {
        /* ignore */
      }
      return connectStratum({ forceVps: true });
    }
    if (androidOpts.localNodeOnly && androidOpts.noVpsFallback) {
      throw new Error(
        `Local node stratum unavailable (${err.message}) — plug in, wait for node startup, then retry`,
      );
    }
    throw err;
  }
  const via = state.stratum.kind === "native-tcp" ? "direct TCP" : "WebSocket bridge";
  let lanHint = "";
  if (state.stratum.lanSource === "local-node") {
    const host = state.stratum.lanDisplayHost || "local";
    const relay = state.miningMode === "pool" ? " · pool relay" : "";
    lanHint = ` (local node @ ${host}${relay})`;
  } else if (state.stratum.lanSource === "mdns") {
    lanHint = ` (mDNS LAN @ ${state.stratum.lanDisplayHost || "peer"})`;
  } else if (state.stratum.lanSource === "lan-peer") {
    lanHint = " (LAN peer)";
  } else if (options.forceVps) {
    lanHint = " (VPS pool)";
  }
  log(`Connected to ${stratumPoolKey()} stratum via ${via}${lanHint} (${state.miningMode} mode)`);
  if (canUseNativeStratum()) {
    log("Decentralized VPS pool node — direct stratum TCP, VPS WebSocket bridge bypassed", "success");
  }
  updateFleetPanel({
    identity: await loadFleetIdentity(),
    transport: transportKind(state.stratum),
    fleetStats: fleetStatsCache,
    mining: state.running,
    networkNodes: cachedNetworkNodes(),
  });
}

async function waitForPoolWork(timeoutMs = 15000) {
  if (isAndroidAppContext()) {
    const status = await getLocalNodeStatus();
    if (isNodeSyncing(status)) timeoutMs = Math.max(timeoutMs, 45000);
  }
  await new Promise((resolve, reject) => {
    const check = () => {
      if (state.job && state.poolDifficultySet && state.targetHex) {
        resolve();
      } else {
        state._jobWaiter = check;
      }
    };
    check();
    setTimeout(() => {
      if (!state.job) {
        reject(new Error("No work received from pool (missing job)"));
      } else if (!state.poolDifficultySet || !state.targetHex) {
        reject(new Error("No share difficulty from pool — try reconnecting"));
      } else {
        resolve();
      }
    }, timeoutMs);
  });
}

async function authorizePoolSession() {
  const stratumUser = buildStratumUser(state.address, resolveWorkerSuffix());
  const authPassword = state.miningMode === "solo" ? "solo" : "x";
  const poolRelayHandshake =
    state.miningMode === "pool" && state.stratum?.poolRelayHandshake === true;

  let sub;
  let authorized;
  if (poolRelayHandshake) {
    [sub, authorized] = await stratumSendBatch([
      { method: "mining.subscribe", params: [stratumUserAgent()] },
      { method: "mining.authorize", params: [stratumUser, authPassword] },
    ]);
  } else {
    sub = await stratumSend("mining.subscribe", [stratumUserAgent()]);
    authorized = await stratumSend("mining.authorize", [stratumUser, authPassword]);
  }
  state.extranonce1 = sub[1];

  if (!authorized) {
    throw new Error("Pool rejected authorize");
  }

  await waitForPoolWork();
  await maybeSuggestDifficulty(true);
  await flushQueuedShares();
  broadcastToWorkers({
    type: "job",
    job: state.job,
    targetHex: state.targetHex,
    running: true,
  });
  broadcastToWorkers({
    type: "start",
    job: state.job,
    targetHex: state.targetHex,
  });
}

async function reconnectPool() {
  if (!state.running || state.userStopped || state.reconnecting) {
    return;
  }
  if (androidPowerMiningRequired()) {
    const power = await refreshAndroidPowerStatus();
    if (!isAndroidPowerMiningAllowed(power)) {
      log("Battery too low for mining — plug in or raise charge above limit", "warn");
      stopMining(false);
      return;
    }
  }
  state.reconnecting = true;
  try {
    resetStratumSession();
    await connectStratum();
    await authorizePoolSession();
    state.reconnectAttempts = 0;
    updateStats();
    log(`Reconnected to pool on job ${state.job.jobId}`, "success");
  } catch (err) {
    if (androidPowerMiningRequired()) {
      log(`Local node reconnect failed: ${err.message}`, "error");
      schedulePoolReconnect("Local node offline");
      return;
    }
    if (canMineOffline() && state.job) {
      state.offlineMining = true;
      $("stat-status").textContent = "Offline (local VPS)";
      log("Pool offline — continuing on cached job via local VPS node", "warn");
      broadcastToWorkers({
        type: "job",
        job: state.job,
        targetHex: state.targetHex,
        running: true,
      });
      schedulePoolReconnect("Pool offline");
    } else {
      log(`Reconnect failed: ${err.message}`, "error");
      schedulePoolReconnect("Still offline");
    }
  } finally {
    state.reconnecting = false;
  }
}

function waitForWorkerReady(worker, workerId, timeoutMs = 120000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      cleanup();
      reject(new Error(`Worker ${workerId} timed out loading hash engine`));
    }, timeoutMs);

    const onMessage = (event) => {
      const msg = event.data;
      if (msg.type === "ready" && msg.workerId === workerId) {
        cleanup();
        resolve();
      } else if (msg.type === "error") {
        log(msg.message || `Worker ${msg.workerId} error`, "error");
        if (msg.workerId === workerId) {
          cleanup();
          reject(new Error(msg.message || `Worker ${workerId} failed`));
        }
      }
    };

    const onError = (event) => {
      cleanup();
      const detail = event?.message || event?.filename || "";
      reject(
        new Error(
          detail
            ? `Worker ${workerId} crashed loading hash engine (${detail})`
            : `Worker ${workerId} crashed — WASM failed to load; tap Check for updates`,
        ),
      );
    };

    function cleanup() {
      clearTimeout(timer);
      worker.removeEventListener("message", onMessage);
      worker.removeEventListener("error", onError);
    }

    worker.addEventListener("message", onMessage);
    worker.addEventListener("error", onError);
  });
}

function parseThreadCount(raw, algo) {
  const cores = navigator.hardwareConcurrency || 2;
  const fallback =
    algo === "yespower" || algo === SHA256D
      ? Math.max(1, Math.min(cores, 2))
      : Math.max(1, Math.min(cores, 8));
  const n = Number.parseInt(String(raw), 10);
  if (!Number.isFinite(n) || n < 1) {
    return fallback;
  }
  return Math.max(1, Math.min(MAX_MINER_THREADS, n));
}

function saveThreadPreference(count) {
  try {
    localStorage.setItem(THREADS_STORAGE_KEY, String(count));
  } catch (_) {
    /* ignore quota / private mode */
  }
}

function loadThreadPreference() {
  try {
    return localStorage.getItem(THREADS_STORAGE_KEY);
  } catch (_) {
    return null;
  }
}

async function spawnWorker(workerId, count) {
  const worker = new Worker(new URL("./web-miner-worker.js", import.meta.url), { type: "module" });
  worker.onmessage = (event) => {
      const msg = event.data;
      if (msg.type === "hashrate") {
        const rates = state.workers.map((w) => w._lastHps || 0);
        rates[msg.workerId] = msg.hps;
        state.workers.forEach((w, idx) => {
          if (rates[idx] !== undefined) w._lastHps = rates[idx];
        });
        state.totalHashrate = rates.reduce((a, b) => a + (b || 0), 0);
        noteMiningHashrate(state.totalHashrate);
        updateStats();
        void maybeSuggestDifficulty();
      } else if (msg.type === "share") {
        state.localYesCount += 1;
        log("YES! (submitting share to pool…)", "success");
        submitShare(msg);
      } else if (msg.type === "error") {
        log(msg.message || `Worker ${msg.workerId + 1} error`, "error");
        if (
          state.running &&
          state.job &&
          state.targetHex &&
          state.workers[msg.workerId]
        ) {
          state.workers[msg.workerId].postMessage({
            type: "start",
            job: state.job,
            targetHex: state.targetHex,
          });
        }
      }
    };
  worker._lastHps = 0;
  worker.postMessage({
    type: "init",
    workerId,
    threadCount: count,
    shareEmitMinMs: workerShareEmitMinMs(),
    algo: state.algo,
    staticPrefix: localAssetPrefix(),
    androidApp: isAndroidAppContext() ? "1" : "",
  });
  await waitForWorkerReady(worker, workerId);
  return worker;
}

async function setupWorkers(count) {
  state.workers.forEach((w) => w.terminate());
  state.workers = [];
  for (let i = 0; i < count; i += 1) {
    let worker = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        if (attempt > 0) {
          log(`Retrying worker ${i + 1} after WASM load failure…`, "warn");
          await new Promise((r) => setTimeout(r, 400));
        }
        worker = await spawnWorker(i, count);
        break;
      } catch (err) {
        if (attempt === 0) continue;
        throw err;
      }
    }
    state.workers[i] = worker;
    log(`Worker ${i + 1}/${count} ready (${state.algo})`);
  }
}

function rodPayoutInput() {
  return document.getElementById("rod-payout-wallet");
}

function syncRodPayoutFields(fromRodPanel = false) {
  const minerInput = $("miner-address");
  const rodInput = rodPayoutInput();
  if (!minerInput || !rodInput) return;
  if (fromRodPanel) {
    minerInput.value = rodInput.value.trim();
    return;
  }
  if (minerInput.value.trim() && !rodInput.value.trim()) {
    rodInput.value = minerInput.value.trim();
  }
}

function tryLoadRodAddress() {
  if (!isRodMining()) return;
  const minerInput = $("miner-address");
  const rodInput = rodPayoutInput();
  if (!minerInput) return;

  const apply = (value) => {
    const trimmed = (value || "").trim();
    if (!trimmed) return;
    minerInput.value = trimmed;
    if (rodInput) rodInput.value = trimmed;
  };

  if (minerInput.value.trim()) {
    syncRodPayoutFields();
    return;
  }

  const rodWallet = document.getElementById("rod-wallet-address");
  if (rodWallet?.value.trim()) {
    apply(rodWallet.value);
    return;
  }
  if (rodInput?.value.trim()) {
    apply(rodInput.value);
    return;
  }
  try {
    const saved = localStorage.getItem(ROD_ADDR_STORAGE_KEY);
    if (saved) apply(saved);
  } catch (_) {
    /* ignore */
  }
}

function updateRewardUi() {
  const rewardWrap = $("miner-reward-wrap");
  const rewardSelect = $("miner-reward");
  const addrInput = $("miner-address");
  const addrWrap = $("miner-address-wrap");
  const addrLabel = $("miner-address-label");
  const addrHint = $("miner-address-hint");
  const hint = $("miner-reward-hint");
  const rodPanel = document.getElementById("rod-payout-wallet-panel");
  const algo = currentAlgo();
  if (rewardWrap) rewardWrap.hidden = algo !== NEOSCRYPT_XAYA;
  if (rewardSelect && algo !== NEOSCRYPT_XAYA) rewardSelect.value = "stone";
  const rod = isRodMining();
  if (rodPanel) rodPanel.hidden = !rod;
  if (addrLabel) {
    addrLabel.textContent = rod ? "ROD wallet (stratum username)" : "STONE payout address";
  }
  if (addrInput) {
    addrInput.placeholder = rod ? "X… or R… (ROD core wallet)" : "SZ… or stone1…";
  }
  if (addrHint) {
    addrHint.textContent = rod
      ? "Same as the ROD payout wallet above — mined ROD is sent here on-chain."
      : "";
  }
  if (addrWrap) addrWrap.hidden = false;
  if (hint) {
    hint.textContent = rod
      ? "Standalone ROD neoscrypt — rewards go to your ROD wallet, not STONE pool rounds."
      : "";
  }
  if (rod) tryLoadRodAddress();
  updateModeUi();
  refreshPoolPending();
}

async function startMining() {
  const address = $("miner-address").value.trim();
  const addrErr = validateMinerAddress(address);
  if (addrErr) {
    log(addrErr, "error");
    return;
  }

  if (androidPowerMiningRequired()) {
    const power = await refreshAndroidPowerStatus();
    if (!isAndroidPowerMiningAllowed(power)) {
      log(androidPowerBlockReason(power), "error");
      updateStartButtonState();
      return;
    }
  }

  const algoEl = $("miner-algo");
  if (algoEl?.tagName === "SELECT") {
    const selected = algoEl.selectedOptions[0];
    if (selected?.disabled) {
      log(`${selected.textContent.trim()} is not available on this chain yet`, "error");
      return;
    }
  }

  clearReconnectTimer();
  state.userStopped = false;
  state.reconnectAttempts = 0;
  state.address = address;
  state.workerSuffix = resolveWorkerSuffix();
  state.algo = currentAlgo();
  state.miningMode = currentMiningMode();
  saveStonePayoutAddress(address);
  saveWorkerSuffix(state.workerSuffix);
  if (isRodMining()) {
    const rodInput = rodPayoutInput();
    if (rodInput) rodInput.value = address;
    try {
      localStorage.setItem(ROD_ADDR_STORAGE_KEY, address);
    } catch (_) {
      /* ignore */
    }
  }
  state.sharesAccepted = 0;
  state.sharesRejected = 0;
  state.blocksFound = 0;
  state.localYesCount = 0;
  state.yesSinceHeartbeat = 0;
  state.lastDiffSuggest = 0;
  stopMobileHeartbeat();
  state.targetHex = "";
  state.blockTargetHex = "";
  state.job = null;
  state.poolDifficultySet = false;
  state.exactShareTarget = false;
  state.recentShareKeys.clear();

  const algo = currentAlgo();
  const threads = parseThreadCount($("miner-threads").value, algo);
  saveThreadPreference(threads);

  $("btn-start").disabled = true;
  $("btn-stop").disabled = false;
  const modeEl = $("miner-mode");
  if (modeEl) modeEl.disabled = true;

  try {
    log(`Starting ${threads} worker thread(s)…`);
    await setupWorkers(threads);
    state.running = true;
    persistMiningResume();
    await loadFleetIdentity();
    await startFleetNode({ address: state.address, algo: state.algo });
    if (isAndroidAppContext()) {
      const nodeMode = getNodeModePreference();
      let nodeStatus = await getLocalNodeStatus();
      if (shouldHostLocalNode(nodeMode)) {
        nodeStatus = await startLocalNode({
          nodeMode,
          foreground: true,
          waitForStratumMs: shouldHostLocalNode(nodeMode) ? 6000 : 2000,
        });
        const reg = await ensureLanRegistration();
        if (reg?.ok) {
          log("LAN registered on pool for household miners", "success");
        }
      } else {
        await stopLocalNode({ foregroundOnly: true });
        nodeStatus = await getLocalNodeStatus();
        const peers = await listDiscoveredLanPeers({ fullOnly: true });
        updateLanPeersPanel(peers);
        if (!peers.length) {
          log("Searching Wi‑Fi for a LAN full node…", "warn");
        }
      }
      updateLocalNodePanel(nodeStatus);
      void refreshDeviceNetworkPanel();
      const stratumOpts = await resolveAndroidStratumOptions(
        state.miningMode,
        stratumPoolKey(),
      );
      if (stratumOpts.lanPeerMissing && isLanClientMode(nodeMode)) {
        throw new Error(
          "No LAN full node found on Wi‑Fi — run Full chain mode on one plugged-in phone, or switch node mode to Pruned/Full on this device",
        );
      }
      if (state.miningMode === "solo" && stratumOpts.chainSyncing) {
        throw new Error(
          "Solo mining needs a synced local node — wait for the chain download to finish or switch to Pool mode",
        );
      }
      if (stratumOpts.lanPeer) {
        log(
          `LAN full node ${stratumOpts.lanPeer.displayHost || stratumOpts.lanPeer.host}:${stratumOpts.lanPeer.port} (${stratumOpts.lanPeer.mode || "full"})`,
          "success",
        );
      } else if (stratumOpts.lanLocalPool) {
        log(
          stratumOpts.lanPeer
            ? `LAN pool coordinator ${stratumOpts.lanPeer.displayHost || stratumOpts.lanPeer.host} — no VPS`
            : "LAN pool coordinator on this phone — jobs, shares, payouts local",
          "success",
        );
      } else if (stratumOpts.forceVps) {
        if (stratumOpts.chainSyncing) {
          log(
            "Local node is downloading the chain — starting miners on VPS pool now",
            "warn",
          );
        } else if (isLanClientMode(nodeMode)) {
          log("No LAN full node found — using VPS pool", "warn");
        } else {
          log("Local node stratum not ready — using VPS pool", "warn");
        }
      } else {
        const ready = await waitForLocalNodeStratum(30000);
        if (ready) {
          log(
            `Local VPS node (${ready.mode}) — RPC ${ready.rpcUrl || ""} · stratum 127.0.0.1:${ready.stratumPort || 3437}`,
            "success",
          );
        } else if (nodeStatus?.running) {
          log("Local node still starting — will try VPS pool if needed", "warn");
        }
      }
    }
    await startBackgroundMining({
      isRunning: () => state.running,
      pingWorkers: () => state.workers.forEach((w) => w.postMessage({ type: "ping" })),
      onForeground: resumeWorkersAfterBackground,
      onBackground: () => {
        if (isMobileWebBrowser()) {
          log("Mining in background — tab stays active via keep-alive", "warn");
        }
      },
      onThrottled: resumeWorkersAfterBackground,
    });
    try {
      await connectStratum();
      await authorizePoolSession();
    } catch (poolErr) {
      if (androidPowerMiningRequired()) {
        const opts = await resolveAndroidStratumOptions(state.miningMode, stratumPoolKey());
        if (!opts.noVpsFallback && !state.stratum?.isOpen?.()) {
          log(`Pool connect failed (${poolErr.message}) — retrying via VPS`, "warn");
          try {
            await connectStratum({ forceVps: true });
            await authorizePoolSession();
          } catch (retryErr) {
            throw retryErr;
          }
        } else {
          throw poolErr;
        }
      }
      if (canMineOffline()) {
        log(`Pool unreachable (${poolErr.message}) — switching to local VPS node`, "warn");
        await startOfflineMiningSession();
        broadcastToWorkers({
          type: "job",
          job: state.job,
          targetHex: state.targetHex,
          running: true,
        });
        broadcastToWorkers({
          type: "start",
          job: state.job,
          targetHex: state.targetHex,
        });
      } else {
        throw poolErr;
      }
    }
    updateStats();
    const kind = minerKind();
    if (kind !== "browser") log(`Installed app mode (${kind}) — pool tracks this device separately`);
    log(`Authorized as ${buildStratumUser(state.address, state.workerSuffix)}`);
    const coin = isRodMining() ? "ROD" : "STONE";
    log(`Mining ${state.miningMode} (${coin}) on job ${state.job.jobId}`);
    try {
      sessionStorage.setItem("bloodstone-autostart-done", "1");
    } catch (_) {
      /* ignore */
    }
    startMobileHeartbeat();
    startPendingShareFlushLoop();
    void flushQueuedShares();
    void sendMobileContribution();
  } catch (err) {
    log(err.message, "error");
    try {
      sessionStorage.removeItem("bloodstone-autostart-done");
    } catch (_) {
      /* ignore */
    }
    const keepNode =
      isAndroidAppContext() && getNodeModePreference() === NODE_MODES.FULL;
    stopMining(false, { stopNode: !keepNode });
    if (keepNode) {
      log(
        "Full node still running — chain sync continues. Tap Start only when you want to mine.",
        "warn",
      );
    }
  }
}

function stopMining(userInitiated = true, options = {}) {
  const stopNode = options.stopNode !== false;
  state.running = false;
  state.userStopped = userInitiated;
  clearMiningResume();
  void stopBackgroundMining();
  void stopFleetNode();
  if (isAndroidAppContext() && stopNode && !isNodeOnlyActive()) {
    void stopLocalNode({ foregroundOnly: true });
  }
  stopMobileHeartbeat();
  stopPendingShareFlushLoop();
  updateFleetPanel({
    identity: fleetDeviceId() ? { deviceId: fleetDeviceId(), model: fleetDeviceModel() } : null,
    transport: transportKind(state.stratum),
    fleetStats: fleetStatsCache,
    mining: false,
    networkNodes: cachedNetworkNodes(),
  });
  clearReconnectTimer();
  state.reconnectAttempts = 0;
  broadcastToWorkers({ type: "stop" });
  resetStratumSession();
  $("btn-stop").disabled = true;
  const modeEl = $("miner-mode");
  if (modeEl) modeEl.disabled = false;
  updateModeUi();
  updateStats();
  updateStartButtonState();
  if (userInitiated) {
    log("Mining stopped");
  }
}

function currentAlgo() {
  const el = $("miner-algo");
  if (!el) return NEOSCRYPT_XAYA;
  return el.value || el.getAttribute("value") || NEOSCRYPT_XAYA;
}

function currentMiningMode() {
  const el = $("miner-mode");
  if (!el) return "pool";
  return el.value === "solo" ? "solo" : "pool";
}

function updateModeUi() {
  const mode = currentMiningMode();
  const rod = isRodMining();
  const sharesLabel = $("stat-shares-label");
  const hint = $("miner-mode-hint");
  if (sharesLabel) {
    sharesLabel.textContent =
      mode === "solo" ? "Accepted / rejected" : "Pool shares (ok / rej)";
  }
  if (hint) {
    if (rod) {
      hint.textContent =
        mode === "solo"
          ? "Solo ROD neoscrypt — full network block difficulty; blocks pay ROD to your wallet."
          : "ROD pool shares use easier browser difficulty; blocks found pay ROD to your wallet.";
    } else {
      hint.textContent =
        mode === "solo"
          ? "Solo uses full network block difficulty in the browser. Blocks go to your payout address."
          : "Pool shares count toward proportional block rewards. Browser and server miners split each block found by share weight.";
    }
  }
  const modeEl = $("miner-mode");
  if (modeEl && !state.running) {
    modeEl.disabled = false;
  }
}

function syncThreadDefault() {
  const algo = currentAlgo();
  const threadsInput = $("miner-threads");
  const hint = $("miner-threads-hint");
  if (!threadsInput) return;
  const cores = navigator.hardwareConcurrency || 2;
  threadsInput.min = "1";
  threadsInput.max = String(MAX_MINER_THREADS);
  threadsInput.readOnly = false;
  const saved = loadThreadPreference();
  const suggested =
    algo === "yespower" || algo === SHA256D
      ? Math.max(1, Math.min(cores, 2))
      : Math.max(1, Math.min(cores, 8));
  threadsInput.value = String(
    saved != null ? parseThreadCount(saved, algo) : suggested,
  );
  threadsInput.title = `Use 1–${MAX_MINER_THREADS} Web Worker threads (${cores} logical CPU cores detected)`;
  if (hint) {
    if (algo === SHA256D) {
      hint.textContent =
        `SHA256d is CPU-heavy — start with 1–2 threads. Uses phone full node :3429 when running, else VPS pool. Max ${MAX_MINER_THREADS}.`;
    } else if (algo === "yespower") {
      hint.textContent =
        `Yespower is CPU-heavy — start with 1–2 threads. Max ${MAX_MINER_THREADS}.`;
    } else {
      hint.textContent =
        `More threads raise hashrate until the CPU is saturated. Max ${MAX_MINER_THREADS}.`;
    }
  }
}

function setMiningMode(mode) {
  const el = $("miner-mode");
  if (!el || state.running) return;
  el.value = mode === "solo" ? "solo" : "pool";
  updateModeUi();
}

function initRewardFromUrl() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("reward") === "rod") {
    const el = $("miner-reward");
    if (el) el.value = "rod";
  }
}

function showAndroidBootError(err) {
  const msg = err?.message || String(err || "Unknown error");
  let el = document.getElementById("android-boot-error");
  if (!el) {
    el = document.createElement("div");
    el.id = "android-boot-error";
    el.className = "android-boot-error muted small";
    el.style.cssText =
      "margin:0.75rem 0;padding:0.65rem 0.85rem;border:1px solid #8b3a3a;background:#2a1212;border-radius:8px;color:#f8d7da;";
    document.querySelector(".wrap")?.prepend(el);
  }
  el.hidden = false;
  el.textContent = `Miner UI failed to start: ${msg}. Scroll down for controls or tap Check for updates.`;
  try {
    log(`Boot error: ${msg}`, "error");
  } catch (_) {
    /* ignore */
  }
}

async function bootMinerUi() {
  try {
  if (isAndroidAppContext()) {
    await waitForBloodstoneBridge(45000);
    await whenCapacitorReady();
    document.getElementById("android-boot-status")?.remove();
  }
  sanitizeMinerAddressField();
  const savedStone = resolvePayoutAddress();
  if (savedStone && $("miner-address") && !$("miner-address").value.trim()) {
    $("miner-address").value = savedStone;
  }
  const workerInput = $("miner-worker");
  if (workerInput && !workerInput.value.trim()) {
    try {
      const savedWorker = sanitizeWorkerSuffix(
        localStorage.getItem(WORKER_SUFFIX_STORAGE_KEY) || "",
      );
      workerInput.value = savedWorker || defaultWorkerSuffix();
    } catch (_) {
      workerInput.value = defaultWorkerSuffix();
    }
  }
  updateStartButtonState();
  if (isCapacitorAndroid() || isAndroidAppContext()) {
    const nodeMode = getNodeModePreference();
    startChainMeshPeer({ nodeMode });
    void initLocalNodeModeUi();
    void initNodeNetworkStats();
    let lastNodeSyncing = null;
    const onNodeStatus = (status) => {
      setFleetNodeStatus(status);
      refreshNodeNetworkStats(status);
      updateNodeOnlyControls(status, { mining: state.running });
      void refreshDeviceNetworkPanel();
    };
    initNodeOnlyControls({
      onLog: (msg, kind) => log(msg, kind),
      getMining: () => state.running,
      onStatus: onNodeStatus,
    });
    initNodeDiagnostics({ onLog: (msg, kind) => log(msg, kind) });
    initMeshChainRestoreUi({ onLog: (msg, kind) => log(msg, kind) });
    initLocalNodeStatusPolling((status) => {
      onNodeStatus(status);
      const syncing = isNodeSyncing(status);
      updateFleetPanel({
        identity: fleetDeviceId() ? { deviceId: fleetDeviceId(), model: fleetDeviceModel() } : null,
        transport: transportKind(state.stratum),
        fleetStats: fleetStatsCache,
        mining: state.running,
        networkNodes: cachedNetworkNodes(),
      });
      if (
        getNodeModePreference() === NODE_MODES.FULL
        && !localStratumAvailable(status)
        && !status?.batteryDormant
      ) {
        void ensureFullNodeForeground();
      }
      if (
        lastNodeSyncing === true
        && syncing === false
        && state.running
        && !state.userStopped
        && state.miningMode === "pool"
      ) {
        log("Full node sync complete — reconnecting via local stratum", "success");
        void reconnectPool();
      }
      lastNodeSyncing = syncing;
    });
    void initDeviceNetworkPanel();
    initMiningSetupInstructions();
    initLanPeerDiscovery();
    void discoverMdnsLanNodes();
    const bootNodePromise = isLanClientMode(nodeMode)
      ? listDiscoveredLanPeers({ fullOnly: true }).then(() => getLocalNodeStatus())
      : ensureFullNodeForeground().then((status) => {
        if (!status && shouldHostLocalNode(nodeMode)) {
          return startLocalNode({
            nodeMode,
            foreground: true,
            waitForStratumMs: 0,
          });
        }
        return status || getLocalNodeStatus();
      }).then((status) => {
        if (needsInitialChainSync(status)) {
          return ensureForegroundChainSync({
            onLog: (msg, kind) => log(msg, kind),
          });
        }
        return status;
      });
    void bootNodePromise.then((status) => {
      setFleetNodeStatus(status);
      updateLocalNodePanel(status);
      refreshNodeNetworkStats(status);
      void refreshDeviceNetworkPanel();
      updateFleetPanel({
        identity: fleetDeviceId() ? { deviceId: fleetDeviceId(), model: fleetDeviceModel() } : null,
        transport: canUseNativeStratum() ? "native-tcp" : "websocket",
        fleetStats: fleetStatsCache,
        mining: false,
        networkNodes: cachedNetworkNodes(),
      });
      if (isLanClientMode(nodeMode)) {
        log("LAN client mode — searching household Wi‑Fi for a full node host", "success");
        updateLanPeersPanel();
      } else if (needsInitialChainSync(status)) {
        log(
          "No chain on device — starting foreground bloodstoned for initial download…",
          "warn",
        );
      } else if (status?.batteryDormant || status?.syncScheduled) {
        log(
          `Battery sync enabled (${status.mode}) — node dormant, checks every ${status.syncIntervalMinutes || 15} min`,
          "success",
        );
      } else if (status?.running) {
        const walletHint = supportsOnDeviceWallet(status.mode) && status.bloodstonedAlive
          ? "on-device wallet available · "
          : "";
        log(
          `Local node (${status.mode}) — ${walletHint}LAN RPC ${status.rpcUrl || ""}`,
          "success",
        );
        if (shouldHostLocalNode(nodeMode)) {
          void ensureLanRegistration().then((reg) => {
            if (reg?.ok) log("LAN registered for household miners", "success");
          });
          import("./lan-device-reporter.js").then(({ startLanDeviceReporter }) => {
            startLanDeviceReporter({ onLog: (msg, kind) => log(msg, kind) });
          }).catch(() => {});
        }
      }
    });
    initLocalWalletPanel({
      onAddress(addr) {
        const input = $("miner-address");
        if (input && addr) {
          input.value = addr;
          saveStonePayoutAddress(addr);
          syncRodPayoutFields();
          refreshPoolPending();
          updateStartButtonState();
          log(`Using on-device wallet ${addr}`, "success");
        }
      },
    });
  }
  if (canUseNativeStratum()) {
    log("Android app: decentralized VPS pool node (native stratum TCP)", "success");
    void loadFleetIdentity().then((identity) => {
      updateFleetPanel({
        identity,
        transport: "native-tcp",
        fleetStats: fleetStatsCache,
        mining: false,
        networkNodes: cachedNetworkNodes(),
      });
    });
  }
  void Promise.all([refreshFleetStats(apiUrl), refreshNetworkNodes()]).then(([stats]) => {
    fleetStatsCache = stats;
    updateFleetPanel({
      identity: fleetDeviceId() ? { deviceId: fleetDeviceId(), model: fleetDeviceModel() } : null,
      transport: canUseNativeStratum() ? "native-tcp" : "websocket",
      fleetStats: stats,
      mining: state.running,
      networkNodes: cachedNetworkNodes(),
    });
  });
  startNetworkNodesPolling(30000);
  initRegisterLanButton();
  if (isCapacitorAndroid() || isAndroidAppContext()) {
    startLanRegistrationHeartbeat(30000);
  }
  if (isCapacitorAndroid() || isAndroidAppContext()) {
    try {
      const { initShareInternetPanel } = await import("./mesh-share-internet.js");
      initShareInternetPanel({
        resolveDeviceId,
        getLanIp: async () => {
          const status = await getLocalNodeStatus();
          return String(status?.lanIp || "").trim();
        },
        onLog: (msg, kind) => log(msg, kind),
      });
    } catch (shareErr) {
      console.warn("share-internet panel unavailable", shareErr);
    }
  }
  initRewardFromUrl();
  syncThreadDefault();
  updateRewardUi();
  $("miner-threads")?.addEventListener("change", () => {
    const threads = parseThreadCount($("miner-threads").value, currentAlgo());
    $("miner-threads").value = String(threads);
    saveThreadPreference(threads);
  });
  $("miner-mode")?.addEventListener("change", () => {
    updateModeUi();
    refreshPoolPending();
  });
  $("miner-address")?.addEventListener("change", () => {
    syncRodPayoutFields();
    saveStonePayoutAddress($("miner-address")?.value || "");
    refreshPoolPending();
    updateStartButtonState();
  });
  $("miner-address")?.addEventListener("input", () => {
    syncRodPayoutFields();
    saveStonePayoutAddress($("miner-address")?.value || "");
    refreshPoolPending();
    updateStartButtonState();
  });
  $("miner-worker")?.addEventListener("change", () => {
    saveWorkerSuffix($("miner-worker")?.value || "");
  });
  $("miner-worker")?.addEventListener("input", () => {
    saveWorkerSuffix($("miner-worker")?.value || "");
  });
  rodPayoutInput()?.addEventListener("input", () => syncRodPayoutFields(true));
  rodPayoutInput()?.addEventListener("change", () => syncRodPayoutFields(true));
  $("miner-reward")?.addEventListener("change", () => {
    updateRewardUi();
    sanitizeMinerAddressField();
    updateStartButtonState();
  });
  $("miner-algo")?.addEventListener("change", () => {
    syncThreadDefault();
    updateRewardUi();
    sanitizeMinerAddressField();
    updateStartButtonState();
  });
  $("btn-start")?.addEventListener("click", startMining);
  $("btn-stop")?.addEventListener("click", () => stopMining(true));
  document.querySelectorAll("[data-set-miner-mode]").forEach((link) => {
    link.addEventListener("click", (event) => {
      setMiningMode(link.getAttribute("data-set-miner-mode"));
      if (!window.location.hash) {
        event.preventDefault();
        document.getElementById("web-miner")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      }
    });
  });
  updateStats();
  refreshAsicSharePublic();
  const poolPollMs = isAndroidAppContext() ? 45000 : 15000;
  const asicPollMs = isAndroidAppContext() ? 60000 : 30000;
  setInterval(refreshPoolPending, poolPollMs);
  setInterval(refreshAsicSharePublic, asicPollMs);
  setInterval(() => {
    void Promise.all([refreshFleetStats(apiUrl), refreshNetworkNodes()]).then(([stats]) => {
      fleetStatsCache = stats;
      updateFleetPanel({
        identity: fleetDeviceId() ? { deviceId: fleetDeviceId(), model: fleetDeviceModel() } : null,
        transport: transportKind(state.stratum),
        fleetStats: stats,
        mining: state.running,
        networkNodes: cachedNetworkNodes(),
      });
    });
  }, 60000);
  if (window.location.hash === "#web-miner") {
    document.getElementById("web-miner")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  if (isAndroidAppContext()) {
    deferBatteryExemptionPrompt();
    onAndroidPowerChange((power) => {
      updateStartButtonState();
      if (state.running && !isAndroidPowerMiningAllowed(power)) {
        log("Battery too low for mining — plug in or raise charge above limit", "warn");
        stopMining(false);
      }
    });
    onThermalGuardAction(({ level, reason }) => {
      if (!state.running && level !== "shutdown") return;
      if (level === "shutdown") {
        log(`${reason} — shutting down local node`, "warn");
        stopMining(false, { stopNode: false });
        return;
      }
      if (level === "pause" && state.running) {
        log(`${reason} — pausing mining (local node keeps syncing)`, "warn");
        stopMining(false, { stopNode: false });
      }
    });
    await initAndroidPowerGuard();
    await initThermalGuard();
    setInterval(() => {
      void refreshThermalStatus();
    }, 30000);
    updateStartButtonState();
    void initAndroidAppUpdate();
    const resumed = await maybeResumeMining();
    const tryAutostart = async () => {
      if (state.running || state.userStopped) return;
      // On Android, mining is manual — full-chain mode hosts the node without auto-mining.
      if (isAndroidAppContext()) return;
      let autostartDone = false;
      try {
        autostartDone = sessionStorage.getItem("bloodstone-autostart-done") === "1";
      } catch (_) {
        /* ignore */
      }
      const address = resolvePayoutAddress();
      const power = cachedAndroidPowerStatus();
      const fullNode = getNodeModePreference() === NODE_MODES.FULL;
      if (!fullNode || isNodeOnlyActive()) return;
      if (!address) {
        log("Full node idle — set a STONE payout address, then tap Start", "warn");
        return;
      }
      if (!isAndroidPowerMiningAllowed(power)) {
        log(androidPowerBlockReason(power) || "Plug in to start mining", "warn");
        return;
      }
      if (autostartDone) return;
      log("Full node ready — starting mining…", "success");
      await startMining();
    };
    if (!resumed) {
      await tryAutostart();
    }
    setInterval(() => {
      void tryAutostart();
    }, 90000);
  }
  } catch (bootErr) {
    showAndroidBootError(bootErr);
    throw bootErr;
  }
}

function signalMinerBootReady() {
  window.__bloodstoneMinerBootReady = true;
  window.dispatchEvent(new CustomEvent("bloodstone-miner-boot-ready"));
}

function exposeMinerCoreGlobals() {
  window.__bloodstoneStartMining = function bloodstoneStartMining() {
    return startMining();
  };
  window.__bloodstoneStopMining = function bloodstoneStopMining(options) {
    return stopMining(true, options || {});
  };
  window.__bloodstoneJustMine = async function bloodstoneJustMine() {
    const { setJustMineActive } = await import("./safeguard-bypass.js");
    setJustMineActive(true);
    return startMining();
  };
  if (!window.__bloodstoneMinerCoreReady) {
    window.__bloodstoneMinerCoreReady = true;
    window.dispatchEvent(new CustomEvent("bloodstone-miner-core-ready"));
  }
}

exposeMinerCoreGlobals();

document.addEventListener("DOMContentLoaded", () => {
  if (isAndroidAppContext()) {
    initAndroidUpdateOptions();
  } else {
    startChainMeshPeer();
  }
  void bootMinerUi()
    .then(() => {
      signalMinerBootReady();
    })
    .catch((err) => showAndroidBootError(err));
});

export { setMiningMode };
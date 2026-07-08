/**
 * In-app diagnostics for Android local node / chain download issues.
 */

import {
  hasNativeCapacitorBridge,
  isAndroidAppContext,
  isBundledMinerOrigin,
  whenCapacitorReady,
} from "./capacitor-ready.js";
import { isCapacitorAndroid } from "./device-fleet.js";
import {
  getChainDownloadSnapshot,
  getLastStatusPollError,
  getLocalNodeStatus,
  getNodeStorageInfo,
  localNodePlugin,
  readNodeModeFromUi,
} from "./local-node.js";

const CORE_PLUGINS = [
  "BloodstoneLocalNode",
  "BloodstoneDevicePool",
  "BloodstoneStratum",
  "BloodstoneChainMesh",
];

let lastReport = null;
let lastReportAt = 0;
let autoRunTimer = null;
let startingSince = 0;

function normalizePayload(raw) {
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

async function probeNativeCall(pluginName, method, args = {}) {
  const cap = window.Capacitor;
  if (!cap) return { ok: false, error: "Capacitor missing" };
  const raw = cap.Plugins?.[pluginName];
  if (raw && typeof raw[method] === "function") {
    try {
      const data = normalizePayload(await raw[method](args));
      return { ok: true, via: "Plugins", data };
    } catch (err) {
      return { ok: false, via: "Plugins", error: String(err?.message || err) };
    }
  }
  if (typeof cap.nativePromise === "function") {
    try {
      const data = normalizePayload(
        await cap.nativePromise(pluginName, method, args),
      );
      return { ok: true, via: "nativePromise", data };
    } catch (err) {
      return { ok: false, via: "nativePromise", error: String(err?.message || err) };
    }
  }
  return { ok: false, error: "no bridge" };
}

function readUiVersions() {
  const body = document.body?.dataset || {};
  let storedWeb = "";
  try {
    storedWeb = localStorage.getItem("bloodstone-web-bundle-version") || "";
  } catch (_) {
    /* ignore */
  }
  return {
    bundledApp: body.appVersion || body.webAppVersion || "",
    bundledWeb: body.webUiVersion || body.webBundleVersion || "",
    storedWeb,
    pageUrl: window.location.href,
    origin: isBundledMinerOrigin() ? "bundled" : "portal/remote",
  };
}

function buildRecommendations(report) {
  const tips = [];
  const { bridge, versions, status, storage, snapshot } = report;

  if (!isBundledMinerOrigin() && isAndroidAppContext()) {
    tips.push({
      level: "error",
      text: "You are not on the bundled miner (localhost). Tap “Open bundled miner” or use offline-mine.html inside the APK.",
    });
  }
  const nativeStamp =
    document.body?.dataset?.nativeApkVersion
    || document.body?.getAttribute?.("data-native-apk-version")
    || "";
  if (!bridge.capacitor && nativeStamp) {
    tips.unshift({
      level: "error",
      text:
        `In-app WebView on the live portal (APK ${nativeStamp}) — Capacitor only works on localhost. `
        + "Tap Open bundled miner or wait for auto-redirect to localhost/offline-mine.html.",
    });
  } else if (!bridge.capacitor) {
    tips.push({
      level: "error",
      text: "Capacitor bridge not loaded — open the Bloodstone app icon, not Chrome or an external browser.",
    });
  } else if (!bridge.nativePromise && !bridge.plugins.BloodstoneLocalNode) {
    tips.push({
      level: "error",
      text: "Install APK 1.3.44+ from Downloads, then Check for updates (UI 1.3.69-web+).",
    });
  }
  if (report.isPlaceholderUi) {
    tips.unshift({
      level: "error",
      text: `UI stuck on placeholder Starting (~2%) — native getLocalNodeStatus failed: ${report.statusPollError || report.statusProbe?.error || "plugin missing"}. Use bundled miner (localhost/offline-mine.html), not the portal page.`,
    });
  }
  if (versions.apk && compareVer(versions.apk, "1.3.43") < 0) {
    tips.push({
      level: "error",
      text: `APK ${versions.apk} is too old for local node — install 1.3.44+.`,
    });
  }
  if (status?.startError) {
    tips.push({ level: "error", text: `Native start error: ${status.startError}` });
  }
  if (status?.chainBootstrapping) {
    tips.push({
      level: "warn",
      text: `Chain bootstrap in progress (${status.chainBootstrapPhase || "?"}, ${status.chainBootstrapPct ?? "?"}%) — wait before bloodstoned sync begins.`,
    });
  }
  if (status?.nodeStarting && snapshot?.phase === "starting") {
    const secs = report.stuckSeconds;
    if (secs >= 30) {
      tips.push({
        level: "warn",
        text: `Stuck on Starting for ${secs}s — if bloodstonedAlive stays false, tap Stop then Start; keep app in front on Wi‑Fi, notifications allowed.`,
      });
    }
  }
  if (status?.bloodstonedAlive === false && status?.running) {
    const restarts = Number(status?.bloodstonedRestartAttempts) || 0;
    const reason = String(
      status?.bloodstonedFailureReason || status?.startError || "",
    ).trim();
    let text = "bloodstoned is not running";
    if (reason) text += ` — ${reason}`;
    if (restarts > 0) text += ` (auto-restart ${restarts}/8)`;
    text += ". Tap Stop node, wait 5 seconds, then Start again; keep app open on Wi‑Fi, battery saver off.";
    tips.push({ level: "error", text });
  }
  if (storage && storage.freeBytes < 96 * 1024 * 1024) {
    tips.push({
      level: "error",
      text: `Low storage (${formatBytes(storage.freeBytes)} free) — need at least 96 MB.`,
    });
  }
  if (status?.running && status?.bloodstonedAlive && snapshot?.phase === "loading") {
    tips.push({
      level: "ok",
      text: "bloodstoned is up — initial chain load can take 2–10 min on a phone before download % moves.",
    });
  }
  if (status?.bloodstonedAlive === undefined && !status?.running && !status?.nodeStarting) {
    tips.unshift({
      level: "warn",
      text: "bloodstonedAlive=undefined means bloodstoned has not started in the foreground yet — not a crash. Tap Start full node, allow notifications, keep app open on Wi‑Fi.",
    });
  } else if (status?.bloodstonedAlive === false && !status?.running) {
    tips.unshift({
      level: "warn",
      text: "bloodstoned is not running. Tap Start full node, allow notifications, disable battery saver, then retry.",
    });
  }
  if (
    !status?.running
    && !status?.nodeStarting
    && (status?.syncScheduled || status?.batteryDormant || snapshot?.phase === "scheduled")
    && (Number(status?.chainBytes) || 0) < 512 * 1024
    && (Number(status?.blockHeight) || 0) === 0
  ) {
    tips.unshift({
      level: "warn",
      text: "Node is in battery-save mode — bloodstoned is not running yet (0 blocks on disk). Pick Full chain in the dropdown, tap Start full node, allow notifications, and keep the app open on Wi‑Fi.",
    });
  }
  if (!tips.length) {
    tips.push({
      level: "ok",
      text: "No obvious fault — if still stuck, copy this report and share APK/UI versions.",
    });
  }
  return tips;
}

function compareVer(a, b) {
  const pa = String(a || "0").split(".").map((x) => parseInt(x, 10) || 0);
  const pb = String(b || "0").split(".").map((x) => parseInt(x, 10) || 0);
  const len = Math.max(pa.length, pb.length);
  for (let i = 0; i < len; i += 1) {
    const x = pa[i] || 0;
    const y = pb[i] || 0;
    if (x > y) return 1;
    if (x < y) return -1;
  }
  return 0;
}

function formatBytes(n) {
  const v = Number(n) || 0;
  if (v >= 1024 * 1024 * 1024) return `${(v / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (v >= 1024 * 1024) return `${(v / (1024 * 1024)).toFixed(0)} MB`;
  if (v >= 1024) return `${(v / 1024).toFixed(0)} KB`;
  return `${v} B`;
}

export async function collectNodeDiagnostics() {
  await whenCapacitorReady(8000);
  const cap = window.Capacitor;
  const bridge = {
    capacitor: Boolean(cap),
    platform: cap?.getPlatform?.() || "none",
    nativePromise: typeof cap?.nativePromise === "function",
    plugins: {},
  };
  for (const name of CORE_PLUGINS) {
    bridge.plugins[name] = Boolean(cap?.Plugins?.[name]);
  }
  bridge.hasAdapter = Boolean(localNodePlugin()?.getLocalNodeStatus);

  const versions = readUiVersions();
  const apkProbe = await probeNativeCall("BloodstoneDevicePool", "getAppVersion");
  if (apkProbe.ok && apkProbe.data) {
    versions.apk = apkProbe.data.versionName || "";
    versions.apkCode = apkProbe.data.versionCode;
  }
  const webProbe = await probeNativeCall("BloodstoneDevicePool", "getWebBundleInfo");
  if (webProbe.ok && webProbe.data) {
    versions.activeWebBundle = webProbe.data.version || "";
    versions.webBundlePath = webProbe.data.path || "";
  }

  const statusProbe = await probeNativeCall("BloodstoneLocalNode", "getLocalNodeStatus");
  const status = statusProbe.ok
    ? statusProbe.data
    : normalizePayload(await getLocalNodeStatus());
  const storageProbe = await probeNativeCall("BloodstoneLocalNode", "getNodeStorageInfo");
  const storage = storageProbe.ok ? storageProbe.data : await getNodeStorageInfo();

  const snapshot = getChainDownloadSnapshot(status || {});
  const mode = readNodeModeFromUi();
  const stuckSeconds =
    snapshot.phase === "starting" && startingSince > 0
      ? Math.round((Date.now() - startingSince) / 1000)
      : 0;
  const statusPollError = getLastStatusPollError();
  const uiPhase = document.getElementById("local-node-sync-phase")?.textContent?.trim() || "";
  const uiPct = document.getElementById("local-node-sync-pct")?.textContent?.trim() || "";
  const isPlaceholderUi =
    !statusProbe.ok
    && (snapshot.phase === "starting" || /starting/i.test(uiPhase))
    && (snapshot.percent <= 0.05 || uiPct === "2%");

  const report = {
    at: new Date().toISOString(),
    mode,
    bridge,
    versions,
    statusProbe: {
      ok: statusProbe.ok,
      via: statusProbe.via || "",
      error: statusProbe.error || "",
    },
    statusPollError,
    uiPhase,
    uiPct,
    isPlaceholderUi,
    status: status || null,
    storage: storage || null,
    snapshot,
    stuckSeconds,
    isCapacitorAndroid: isCapacitorAndroid(),
    isAndroidAppContext: isAndroidAppContext(),
    isBundledMinerOrigin: isBundledMinerOrigin(),
    hasNativeCapacitorBridge: hasNativeCapacitorBridge(),
  };
  report.recommendations = buildRecommendations(report);
  lastReport = report;
  lastReportAt = Date.now();
  return report;
}

export function formatDiagnosticsReport(report) {
  const r = report || lastReport;
  if (!r) return "No diagnostics run yet.";
  const lines = [];
  lines.push(`=== Bloodstone node diagnostics ${r.at} ===`);
  lines.push(`URL: ${r.versions.pageUrl}`);
  lines.push(`Origin: ${r.versions.origin} · mode: ${r.mode}`);
  lines.push(
    `APK: ${r.versions.apk || "?"} (code ${r.versions.apkCode ?? "?"}) · `
    + `UI bundled: ${r.versions.bundledWeb || "?"} · stored: ${r.versions.storedWeb || "?"} · `
    + `active bundle: ${r.versions.activeWebBundle || "?"}`,
  );
  lines.push(
    `Bridge: platform=${r.bridge.platform} nativePromise=${r.bridge.nativePromise ? "yes" : "no"} `
    + `adapter=${r.bridge.hasAdapter ? "yes" : "no"}`,
  );
  lines.push(
    `Plugins: ${CORE_PLUGINS.map((p) => `${p}=${r.bridge.plugins[p] ? "Y" : "n"}`).join(" ")}`,
  );
  if (r.statusProbe) {
    lines.push(
      `getLocalNodeStatus: ${r.statusProbe.ok ? "OK" : "FAIL"} `
      + `${r.statusProbe.via || ""} ${r.statusProbe.error || ""}`.trim(),
    );
  }
  const s = r.status || {};
  lines.push(
    `Node: running=${s.running} nodeStarting=${s.nodeStarting} bloodstonedAlive=${s.bloodstonedAlive} `
    + `mode=${s.mode} startError=${s.startError || "—"} `
    + `restarts=${s.bloodstonedRestartAttempts ?? 0}`,
  );
  if (s.bloodstonedFailureReason) {
    lines.push(`bloodstonedFailureReason: ${s.bloodstonedFailureReason}`);
  }
  if (s.chainBootstrapping) {
    lines.push(
      `Bootstrap: phase=${s.chainBootstrapPhase || "—"} pct=${s.chainBootstrapPct ?? "—"}`,
    );
  }
  if (r.isPlaceholderUi) {
    lines.push(
      `UI placeholder: YES (phase=${r.uiPhase || "—"} pct=${r.uiPct || "—"}) `
      + `pollError=${r.statusPollError || r.statusProbe?.error || "—"}`,
    );
  }
  lines.push(
    `Sync: phase=${r.snapshot?.phase} pct=${r.snapshot?.percent ?? "—"} `
    + `height=${r.snapshot?.local ?? 0}/${r.snapshot?.network ?? 0} `
    + `disk=${formatBytes(r.snapshot?.chainBytes)} stuck=${r.stuckSeconds}s`,
  );
  if (r.storage) {
    lines.push(
      `Storage: free=${formatBytes(r.storage.freeBytes)} `
      + `canRunFull=${r.storage.canRunFullNode} recommended=${r.storage.recommendedMode}`,
    );
  }
  lines.push("--- Recommendations ---");
  for (const tip of r.recommendations || []) {
    lines.push(`[${tip.level}] ${tip.text}`);
  }
  return lines.join("\n");
}

function setDiagSummary(text, level = "") {
  const el = document.getElementById("node-diag-summary");
  if (!el) return;
  el.textContent = text || "";
  el.classList.remove("diag-ok", "diag-warn", "diag-error");
  if (level === "ok") el.classList.add("diag-ok");
  else if (level === "warn") el.classList.add("diag-warn");
  else if (level === "error") el.classList.add("diag-error");
}

function setDiagBody(text) {
  const el = document.getElementById("node-diag-body");
  if (!el) return;
  el.textContent = text || "";
}

async function copyDiagnosticsReport() {
  const text = formatDiagnosticsReport();
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_) {
    /* fall through */
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch (_) {
    ok = false;
  }
  document.body.removeChild(ta);
  return ok;
}

export async function runNodeDiagnostics({ onLog, silent = false } = {}) {
  const btn = document.getElementById("btn-node-diagnostics");
  if (btn) btn.disabled = true;
  try {
    if (!silent) onLog?.("Running node diagnostics…", "warn");
    const report = await collectNodeDiagnostics();
    const text = formatDiagnosticsReport(report);
    setDiagBody(text);
    const top = report.recommendations?.[0];
    setDiagSummary(top?.text || "Diagnostics complete", top?.level || "ok");
    const wrap = document.getElementById("node-diagnostics-wrap");
    if (wrap) wrap.hidden = false;
    if (!silent) {
      onLog?.("Diagnostics ready — see Node diagnostics panel below", "warn");
      for (const tip of report.recommendations || []) {
        onLog?.(tip.text, tip.level === "error" ? "error" : tip.level === "warn" ? "warn" : "success");
      }
    }
    return report;
  } catch (err) {
    const msg = String(err?.message || err);
    setDiagSummary(`Diagnostics failed: ${msg}`, "error");
    onLog?.(`Diagnostics failed: ${msg}`, "error");
    return null;
  } finally {
    if (btn) btn.disabled = false;
  }
}

export function trackNodePhaseForDiagnostics(status) {
  const snap = getChainDownloadSnapshot(status || {});
  if (snap.phase === "starting") {
    if (!startingSince) startingSince = Date.now();
  } else {
    startingSince = 0;
  }
}

export function initNodeDiagnostics({ onLog } = {}) {
  if (!isAndroidAppContext() && !isCapacitorAndroid()) return;

  const wrap = document.getElementById("node-diagnostics-wrap");
  const runBtn = document.getElementById("btn-node-diagnostics");
  const copyBtn = document.getElementById("btn-node-diag-copy");
  if (!wrap || !runBtn) return;
  if (runBtn.dataset.diagHooked === "1") return;
  runBtn.dataset.diagHooked = "1";

  const logFn = onLog || (() => {});

  runBtn.addEventListener("click", (event) => {
    event.preventDefault();
    if (typeof window.__bloodstoneRunNodeDiagnostics === "function") {
      void window.__bloodstoneRunNodeDiagnostics();
      return;
    }
    void runNodeDiagnostics({ onLog: logFn });
  });
  if (copyBtn && copyBtn.dataset.diagHooked !== "1") {
    copyBtn.dataset.diagHooked = "1";
    copyBtn.addEventListener("click", async (event) => {
      event.preventDefault();
      const ok = await copyDiagnosticsReport();
      logFn?.(
        ok ? "Diagnostic report copied" : "Copy failed — select text in panel manually",
        ok ? "success" : "warn",
      );
    });
  }

  if (autoRunTimer) clearInterval(autoRunTimer);
  autoRunTimer = setInterval(() => {
    if (!startingSince) return;
    const stuck = Date.now() - startingSince;
    if (stuck < 35000) return;
    if (lastReportAt && Date.now() - lastReportAt < 30000) return;
    void runNodeDiagnostics({ onLog, silent: true });
  }, 10000);

  void runNodeDiagnostics({ onLog, silent: true });
}
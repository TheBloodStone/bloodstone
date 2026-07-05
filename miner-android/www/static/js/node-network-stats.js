/** Full-node network traffic + work summary (Android Capacitor). */

import { displaySyncPercent, estimateSyncProgress, getLocalNodeStatus } from "./local-node.js";
import { isCapacitorAndroid } from "./device-fleet.js";

const HISTORY_KEY = "bloodstone-node-traffic-history";
const MAX_SAMPLES = 72;
const POLL_MS = 5000;

let pollTimer = null;
let history = loadHistory();

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.slice(-MAX_SAMPLES) : [];
  } catch (_) {
    return [];
  }
}

function saveHistory() {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-MAX_SAMPLES)));
  } catch (_) {
    /* ignore */
  }
}

function formatBytes(bytes) {
  const n = Number(bytes || 0);
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${n} B`;
}

function formatUptime(sec) {
  const s = Math.max(0, Number(sec || 0));
  if (s >= 86400) return `${(s / 86400).toFixed(1)} d`;
  if (s >= 3600) return `${(s / 3600).toFixed(1)} h`;
  if (s >= 60) return `${Math.round(s / 60)} min`;
  return `${s} s`;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function drawLineChart(canvas, series, colors, labels) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const pad = { t: 12, r: 8, b: 22, l: 42 };
  ctx.clearRect(0, 0, w, h);
  if (!series.length || !series[0].length) {
    ctx.fillStyle = "#8b95a8";
    ctx.font = "12px system-ui,sans-serif";
    ctx.fillText("Collecting samples…", pad.l, h / 2);
    return;
  }
  const len = series[0].length;
  const all = series.flat();
  const max = Math.max(1, ...all);
  const plotW = w - pad.l - pad.r;
  const plotH = h - pad.t - pad.b;
  ctx.strokeStyle = "#252a36";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t);
  ctx.lineTo(pad.l, h - pad.b);
  ctx.lineTo(w - pad.r, h - pad.b);
  ctx.stroke();
  series.forEach((values, idx) => {
    ctx.strokeStyle = colors[idx];
    ctx.lineWidth = 2;
    ctx.beginPath();
    values.forEach((v, i) => {
      const x = pad.l + (i / Math.max(1, len - 1)) * plotW;
      const y = h - pad.b - (v / max) * plotH;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });
  ctx.fillStyle = "#8b95a8";
  ctx.font = "10px system-ui,sans-serif";
  ctx.fillText(labels[0] || "", pad.l, h - 6);
  ctx.textAlign = "right";
  ctx.fillText(formatBytes(max), pad.l - 4, pad.t + 10);
  ctx.textAlign = "left";
}

function drawWorkChart(canvas, work) {
  if (!canvas || !work) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const pad = { t: 12, r: 8, b: 28, l: 8 };
  ctx.clearRect(0, 0, w, h);
  const items = [
    { label: "Blocks synced", value: Number(work.blocksSynced || 0) },
    { label: "RPC served", value: Number(work.rpcRequestsServed || 0) },
    { label: "Stratum peers", value: Number(work.stratumConnections || 0) },
    { label: "Sync runs", value: Number(work.syncSessions || 0) },
  ];
  const max = Math.max(1, ...items.map((i) => i.value));
  const barW = (w - pad.l - pad.r) / items.length - 8;
  items.forEach((item, idx) => {
    const x = pad.l + idx * (barW + 8) + 4;
    const barH = ((h - pad.t - pad.b - 16) * item.value) / max;
    const y = h - pad.b - barH;
    ctx.fillStyle = "#5b8cff";
    ctx.fillRect(x, y, barW, barH);
    ctx.fillStyle = "#8b95a8";
    ctx.font = "9px system-ui,sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(item.label, x + barW / 2, h - 8);
    ctx.fillStyle = "#e8ecf4";
    ctx.font = "10px system-ui,sans-serif";
    ctx.fillText(String(item.value), x + barW / 2, y - 4);
  });
  ctx.textAlign = "left";
}

function pushSample(work) {
  if (!work) return;
  history.push({
    t: Date.now(),
    rx: Number(work.totalRxBytes || work.appUidRxBytes || 0),
    tx: Number(work.totalTxBytes || work.appUidTxBytes || 0),
    sessionRx: Number(work.sessionRxBytes || 0),
    sessionTx: Number(work.sessionTxBytes || 0),
    blocks: Number(work.blocksSynced || 0),
    rpc: Number(work.rpcRequestsServed || 0),
  });
  saveHistory();
}

function updatePanel(status) {
  const panel = document.getElementById("node-network-panel");
  if (!panel) return;
  const work = status?.networkWork;
  const progress = estimateSyncProgress(status);
  const syncing =
    progress == null
      ? Boolean(status?.running && status?.bloodstonedAlive !== false)
      : progress < 0.999;
  const show =
    isCapacitorAndroid() &&
    (status?.running || status?.syncScheduled || status?.batteryDormant || syncing);
  panel.hidden = !show;
  if (!show) return;
  if (!work) {
    drawLineChart(
      document.getElementById("nn-traffic-chart"),
      [[]],
      ["#6eb5ff", "#d4a017"],
      ["Total RX (blue) · TX (gold)"]
    );
    drawWorkChart(document.getElementById("nn-work-chart"), {
      blocksSynced: 0,
      rpcRequestsServed: 0,
      stratumConnections: 0,
      syncSessions: 0,
    });
    setText(
      "nn-mode-line",
      (() => {
        const pct = displaySyncPercent(status);
        return `${status?.mode || "node"} · syncing${pct != null ? ` ${pct}%` : ""}`;
      })()
    );
    return;
  }

  pushSample(work);

  const totalRx = Number(work.totalRxBytes || work.appUidRxBytes || 0);
  const totalTx = Number(work.totalTxBytes || work.appUidTxBytes || 0);
  setText("nn-total-rx", formatBytes(totalRx));
  setText("nn-total-tx", formatBytes(totalTx));
  setText("nn-session-rx", formatBytes(work.sessionRxBytes));
  setText("nn-session-tx", formatBytes(work.sessionTxBytes));
  setText("nn-lan-rx", formatBytes(work.lanRxBytes));
  setText("nn-lan-tx", formatBytes(work.lanTxBytes));
  setText("nn-upstream-rx", formatBytes(work.upstreamRxBytes));
  setText("nn-upstream-tx", formatBytes(work.upstreamTxBytes));
  setText("nn-blocks-synced", String(work.blocksSynced || 0));
  setText("nn-rpc-served", String(work.rpcRequestsServed || 0));
  setText("nn-stratum-peers", String(work.stratumConnections || 0));
  setText("nn-sync-sessions", String(work.syncSessions || 0));
  setText("nn-uptime", formatUptime(work.nodeUptimeSec));
  setText(
    "nn-mode-line",
    `${work.nodeMode || status.mode || "node"} · height ${status.blockHeight || "—"}` +
      (status.networkBlockHeight ? ` / network ${status.networkBlockHeight}` : "")
  );

  const rxSeries = history.map((s) => s.rx);
  const txSeries = history.map((s) => s.tx);
  drawLineChart(
    document.getElementById("nn-traffic-chart"),
    [rxSeries, txSeries],
    ["#6eb5ff", "#d4a017"],
    ["Total RX (blue) · TX (gold)"]
  );
  drawWorkChart(document.getElementById("nn-work-chart"), work);
}

async function pollOnce() {
  const status = await getLocalNodeStatus();
  updatePanel(status);
  return status;
}

export async function initNodeNetworkStats() {
  if (!isCapacitorAndroid()) return;
  const panel = document.getElementById("node-network-panel");
  if (!panel) return;
  await pollOnce();
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => {
    void pollOnce();
  }, POLL_MS);
}

export function refreshNodeNetworkStats(status) {
  updatePanel(status);
}
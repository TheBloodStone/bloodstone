/** Live LAN node sync lag — mining dashboard + admin. */

import { apiUrl } from "./miner-paths.js";

let lastPayload = null;
let pollTimer = null;
let visibilityHooked = false;

const VISIBLE_POLL_MS = 5000;
const HIDDEN_POLL_MS = 20000;

function formatAge(sec) {
  const n = Number(sec) || 0;
  if (n < 60) return `${n}s ago`;
  if (n < 3600) return `${Math.floor(n / 60)}m ago`;
  if (n < 86400) return `${Math.floor(n / 3600)}h ago`;
  return `${Math.floor(n / 86400)}d ago`;
}

function statusBadge(status) {
  const s = String(status || "").toLowerCase();
  const labels = {
    caught_up: "Up to date",
    syncing: "Syncing",
    behind: "Behind",
    stale: "Stale",
    stuck: "Starting",
    headers_ahead: "Tip lag",
  };
  return labels[s] || s || "—";
}

function statusClass(status) {
  const s = String(status || "").toLowerCase();
  if (s === "caught_up") return "badge-up";
  if (s === "syncing" || s === "headers_ahead") return "badge-warn";
  return "badge-down";
}

function renderSummary(data, prefix = "lan-lag") {
  if (!data?.ok) return;
  const tipEl = document.getElementById(`${prefix}-tip`);
  const activeEl = document.getElementById(`${prefix}-active`);
  const maxEl = document.getElementById(`${prefix}-max-behind`);
  const updatedEl = document.getElementById(`${prefix}-updated`);
  if (tipEl) tipEl.textContent = String(data.network_tip ?? "—");
  if (activeEl) {
    activeEl.textContent = `${data.active_count ?? 0} / ${data.node_count ?? 0}`;
  }
  if (maxEl) maxEl.textContent = String(data.max_blocks_behind ?? "—");
  if (updatedEl) {
    const ts = Number(data.updated_at) || 0;
    updatedEl.textContent = ts ? new Date(ts * 1000).toLocaleTimeString() : "—";
  }
}

function renderTable(data, tableId = "lan-lag-table") {
  const tbody = document.querySelector(`#${tableId} tbody`);
  if (!tbody) return;
  const nodes = Array.isArray(data?.nodes) ? data.nodes : [];
  if (!nodes.length) {
    tbody.innerHTML =
      '<tr><td colspan="8" class="muted small">No LAN nodes registered in the lookback window.</td></tr>';
    return;
  }
  tbody.innerHTML = nodes
    .map((n) => {
      const behind = Number(n.blocks_behind) || 0;
      const syncPct = Math.round((Number(n.sync_progress) || 0) * 100);
      return `<tr data-status="${n.status || ""}">
        <td class="mono small">${n.device_id || "—"}</td>
        <td class="mono small">${n.lan_ip || "—"}</td>
        <td>${n.mode || "—"}</td>
        <td class="mono small">${n.block_height ?? 0}</td>
        <td class="mono small">${behind > 0 ? behind : "0"}</td>
        <td class="mono small">${syncPct}%</td>
        <td><span class="badge ${statusClass(n.status)}">${statusBadge(n.status)}</span></td>
        <td class="muted small">${n.active ? formatAge(n.age_sec) : `stale · ${formatAge(n.age_sec)}`}</td>
      </tr>`;
    })
    .join("");
}

export function updateLanNodesLagPanel(data = lastPayload, options = {}) {
  if (!data) return;
  lastPayload = data;
  const prefix = options.summaryPrefix || "lan-lag";
  const tableId = options.tableId || "lan-lag-table";
  renderSummary(data, prefix);
  renderTable(data, tableId);
}

export async function refreshLanNodesLag(options = {}) {
  const path = options.admin ? "/api/admin/lan-nodes" : "/api/network/lan-nodes";
  try {
    const res = await fetch(apiUrl(path), { credentials: options.admin ? "same-origin" : "omit" });
    if (!res.ok) return null;
    const data = await res.json();
    if (!data?.ok) return null;
    updateLanNodesLagPanel(data, options);
    return data;
  } catch (_) {
    return null;
  }
}

function currentLagPollMs(intervalMs) {
  if (typeof document !== "undefined" && document.hidden) {
    return Math.max(intervalMs, HIDDEN_POLL_MS);
  }
  return Math.min(intervalMs, VISIBLE_POLL_MS);
}

function scheduleLagPoll(intervalMs, options) {
  if (pollTimer) window.clearInterval(pollTimer);
  const run = () => void refreshLanNodesLag(options);
  run();
  pollTimer = window.setInterval(run, currentLagPollMs(intervalMs));
  if (!visibilityHooked && typeof document !== "undefined") {
    visibilityHooked = true;
    document.addEventListener("visibilitychange", () => {
      scheduleLagPoll(intervalMs, options);
    });
  }
}

export function startLanNodesLagPolling(intervalMs = 5000, options = {}) {
  scheduleLagPoll(intervalMs, options);
  return () => {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  };
}

export function cachedLanNodesLag() {
  return lastPayload;
}
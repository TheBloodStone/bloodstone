/**
 * Admin queue for user mesh uploads awaiting approval.
 */

import { apiUrl } from "./miner-paths.js";
import { refreshMeshAssetLibrary } from "./mesh-asset-library.js";

function formatBytes(n) {
  const v = Number(n) || 0;
  if (v >= 1024 * 1024) return `${(v / (1024 * 1024)).toFixed(2)} MiB`;
  if (v >= 1024) return `${(v / 1024).toFixed(1)} KiB`;
  return `${v} B`;
}

function formatDate(ts) {
  const n = Number(ts) || 0;
  if (!n) return "—";
  try {
    return new Date(n * 1000).toLocaleString();
  } catch (_) {
    return String(n);
  }
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function setStatus(text, kind = "") {
  const el = document.getElementById("mesh-pending-status");
  if (!el) return;
  el.textContent = text;
  el.className = `muted small mesh-upload-status${kind ? ` ${kind}` : ""}`;
}

async function approveSubmission(id) {
  if (!window.confirm(`Approve submission #${id} and publish to chain mesh?`)) return;
  setStatus(`Approving #${id}…`);
  const res = await fetch(apiUrl(`/api/chain-mesh/pending-submissions/${id}/approve`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    setStatus(data.error || `Approve failed (${res.status})`, "error");
    return;
  }
  const anchor = data.publish?.anchor?.txid
    ? ` · anchored ${String(data.publish.anchor.txid).slice(0, 12)}…`
    : "";
  setStatus(`Published ${data.publish?.asset_key || ""}${anchor}`, "ok");
  void refreshPendingSubmissions();
  void refreshMeshAssetLibrary(100);
}

async function rejectSubmission(id) {
  const reason = window.prompt("Rejection reason (optional):", "") || "";
  setStatus(`Rejecting #${id}…`);
  const res = await fetch(apiUrl(`/api/chain-mesh/pending-submissions/${id}/reject`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ reason }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    setStatus(data.error || `Reject failed (${res.status})`, "error");
    return;
  }
  setStatus(`Rejected submission #${id}.`, "ok");
  void refreshPendingSubmissions();
}

function renderPendingRows(items) {
  const tbody = document.querySelector("#mesh-pending-submissions tbody");
  if (!tbody) return;
  if (!items?.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="muted">No pending user uploads.</td></tr>';
    return;
  }
  tbody.innerHTML = items
    .map((row) => {
      const note = row.submitter_note ? escapeHtml(row.submitter_note) : "—";
      const addr = row.submitter_address ? escapeHtml(row.submitter_address) : "—";
      return (
        `<tr data-submission-id="${row.id}">` +
        `<td class="mono small">#${row.id}</td>` +
        `<td title="${escapeHtml(row.asset_key)}">${escapeHtml(row.display_name || row.asset_key)}</td>` +
        `<td class="mono small">${escapeHtml(row.asset_key)}</td>` +
        `<td>${formatBytes(row.file_size)}</td>` +
        `<td>${row.chunk_count ?? "—"}</td>` +
        `<td class="mono small">${addr}</td>` +
        `<td class="small">${note}</td>` +
        `<td class="mesh-asset-actions">` +
        `<button type="button" class="btn btn-small" data-pending-action="approve" data-id="${row.id}">Approve</button> ` +
        `<button type="button" class="btn btn-ghost btn-small" data-pending-action="reject" data-id="${row.id}">Reject</button>` +
        `</td>` +
        `</tr>`
      );
    })
    .join("");

  tbody.querySelectorAll("[data-pending-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.getAttribute("data-id"));
      const action = btn.getAttribute("data-pending-action");
      if (!id) return;
      if (action === "approve") void approveSubmission(id);
      if (action === "reject") void rejectSubmission(id);
    });
  });
}

export async function refreshPendingSubmissions(limit = 50) {
  try {
    const res = await fetch(apiUrl(`/api/chain-mesh/pending-submissions?limit=${limit}`), {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!res.ok) {
      if (res.status === 403) {
        renderPendingRows([]);
        setStatus("Admin login required to review submissions.", "error");
      }
      return null;
    }
    const data = await res.json();
    renderPendingRows(data.submissions || []);
    const countEl = document.getElementById("mesh-pending-count");
    if (countEl) countEl.textContent = String((data.submissions || []).length);
    return data.submissions || [];
  } catch (err) {
    setStatus(err.message || String(err), "error");
    return null;
  }
}

export function initMeshAssetPending(options = {}) {
  void refreshPendingSubmissions(options.limit || 50);
  if (!options.pollMs) return;
  window.setInterval(() => {
    void refreshPendingSubmissions(options.limit || 50);
  }, options.pollMs);
}
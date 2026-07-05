/**
 * Mesh file search — server-side query, download only selected assets' chunks.
 */

import { apiUrl } from "./miner-paths.js";
import { downloadAsset } from "./mesh-asset-library.js";

const PAGE_SIZE = 25;
const DEBOUNCE_MS = 320;

function formatBytes(n) {
  const v = Number(n) || 0;
  if (v >= 1024 * 1024) return `${(v / (1024 * 1024)).toFixed(2)} MiB`;
  if (v >= 1024) return `${(v / 1024).toFixed(1)} KiB`;
  return `${v} B`;
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function readParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    q: params.get("q") || "",
    prefix: params.get("prefix") || "",
    mime: params.get("mime") || "",
    offset: Math.max(0, Number(params.get("offset") || 0)),
  };
}

function writeParams({ q, prefix, mime, offset }) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (prefix) params.set("prefix", prefix);
  if (mime) params.set("mime", mime);
  if (offset > 0) params.set("offset", String(offset));
  const qs = params.toString();
  const url = `${window.location.pathname}${qs ? `?${qs}` : ""}`;
  window.history.replaceState(null, "", url);
}

function selectedRows() {
  return [...document.querySelectorAll("#mesh-search-results tbody tr[data-asset-key]")].filter(
    (row) => row.querySelector('input[type="checkbox"]')?.checked,
  );
}

function updateSelectionStats() {
  const rows = selectedRows();
  const statsEl = document.getElementById("mesh-search-selection-stats");
  const dlBtn = document.getElementById("mesh-search-download-selected");
  let chunks = 0;
  let bytes = 0;
  for (const row of rows) {
    chunks += Number(row.dataset.chunkCount) || 0;
    bytes += Number(row.dataset.fileSize) || 0;
  }
  if (statsEl) {
    statsEl.textContent = rows.length
      ? `${rows.length} file(s) · ${chunks} chunk(s) · ${formatBytes(bytes)} to download`
      : "";
  }
  if (dlBtn) dlBtn.disabled = rows.length === 0;
}

function renderResults(data) {
  const tbody = document.querySelector("#mesh-search-results tbody");
  const summary = document.getElementById("mesh-search-summary");
  const meta = document.getElementById("search-meta");
  const actions = document.getElementById("mesh-search-actions");
  const pager = document.getElementById("mesh-search-pager");
  const pageInfo = document.getElementById("mesh-search-page-info");
  const prevBtn = document.getElementById("mesh-search-prev");
  const nextBtn = document.getElementById("mesh-search-next");

  if (!tbody) return;

  const results = data.results || [];
  if (!results.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="muted">No matching files on the mesh.</td></tr>';
  } else {
    tbody.innerHTML = results
      .map((row) => {
        const key = row.asset_key || "";
        return (
          `<tr data-asset-key="${escapeHtml(key)}"` +
          ` data-chunk-count="${Number(row.chunk_count) || 0}"` +
          ` data-file-size="${Number(row.file_size) || 0}">` +
          `<td><input type="checkbox" class="mesh-search-check" aria-label="Select ${escapeHtml(key)}"></td>` +
          `<td class="col-name">${escapeHtml(row.display_name || "—")}</td>` +
          `<td class="mono col-key">${escapeHtml(key)}</td>` +
          `<td>${formatBytes(row.file_size)}</td>` +
          `<td>${row.chunk_count ?? "—"}</td>` +
          `<td>` +
          `<button type="button" class="btn-dl" data-mesh-search-dl="${escapeHtml(key)}">Download</button>` +
          `</td></tr>`
        );
      })
      .join("");
  }

  tbody.querySelectorAll(".mesh-search-check").forEach((cb) => {
    cb.addEventListener("change", updateSelectionStats);
  });
  tbody.querySelectorAll("[data-mesh-search-dl]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.getAttribute("data-mesh-search-dl");
      if (!key) return;
      const statusEl =
    document.getElementById("mesh-search-status") || document.getElementById("search-status");
      void downloadAsset(key, statusEl);
    });
  });

  const q = data.query || "";
  const summaryHtml = q
    ? `<strong>${data.total_matches ?? results.length}</strong> match(es) for <span class="mono">${escapeHtml(q)}</span>` +
      (data.prefix ? ` in <span class="mono">${escapeHtml(data.prefix)}</span>` : "") +
      ` · ${results.length} on page · <strong>${data.selected_chunks ?? 0}</strong> chunks · <strong>${formatBytes(data.selected_bytes)}</strong> if all downloaded`
    : `${results.length} recent mesh file(s) — type to search`;

  if (summary) summary.innerHTML = summaryHtml;
  if (meta) meta.textContent = summaryHtml.replace(/<[^>]+>/g, "");

  if (actions) actions.hidden = results.length === 0;
  if (pager) pager.hidden = (data.total_matches || 0) <= PAGE_SIZE;

  const offset = Number(data.offset) || 0;
  const total = Number(data.total_matches) || results.length;
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (pageInfo) pageInfo.textContent = `Page ${page} of ${pages}`;
  if (prevBtn) prevBtn.disabled = offset <= 0;
  if (nextBtn) nextBtn.disabled = offset + PAGE_SIZE >= total;

  updateSelectionStats();
}

async function runSearch({ q, prefix, mime, offset }, statusEl) {
  if (statusEl) statusEl.textContent = q ? `Searching for “${q}”…` : "Loading catalog…";
  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(offset || 0),
  });
  if (q) params.set("q", q);
  if (prefix) params.set("prefix", prefix);
  if (mime) params.set("mime", mime);

  const res = await fetch(apiUrl(`/api/chain-mesh/search?${params}`), { cache: "no-store" });
  if (!res.ok) throw new Error(`search failed (${res.status})`);
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "search failed");
  renderResults(data);
  if (statusEl) statusEl.textContent = "";
  return data;
}

async function downloadSelected(statusEl) {
  const rows = selectedRows();
  if (!rows.length) return;
  let done = 0;
  for (const row of rows) {
    const key = row.getAttribute("data-asset-key");
    if (!key) continue;
    if (statusEl) {
      statusEl.textContent = `Downloading ${done + 1}/${rows.length}: ${key}…`;
    }
    await downloadAsset(key, null);
    done += 1;
  }
  if (statusEl) {
    statusEl.textContent = `Downloaded ${done} file(s) — only their mesh chunks were fetched.`;
  }
}

export function initMeshSearch() {
  const form = document.getElementById("mesh-search-form");
  const queryInput = document.getElementById("mesh-search-query");
  const prefixSelect = document.getElementById("mesh-search-prefix");
  const mimeInput = document.getElementById("mesh-search-mime");
  const statusEl =
    document.getElementById("mesh-search-status") || document.getElementById("search-status");
  const selectAll = document.getElementById("mesh-search-select-all");
  const dlSelected = document.getElementById("mesh-search-download-selected");
  const prevBtn = document.getElementById("mesh-search-prev");
  const nextBtn = document.getElementById("mesh-search-next");

  let state = readParams();
  if (queryInput) queryInput.value = state.q;
  if (prefixSelect) prefixSelect.value = state.prefix.replace(/\/$/, "");
  if (mimeInput) mimeInput.value = state.mime;

  let debounceTimer = null;

  const exec = () => {
    state = {
      q: (queryInput?.value || "").trim(),
      prefix: prefixSelect?.value || "",
      mime: (mimeInput?.value || "").trim(),
      offset: state.offset || 0,
    };
    writeParams(state);
    void runSearch(state, statusEl).catch((err) => {
      if (statusEl) statusEl.textContent = err.message || String(err);
    });
  };

  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    state.offset = 0;
    exec();
  });

  queryInput?.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      state.offset = 0;
      exec();
    }, DEBOUNCE_MS);
  });

  prefixSelect?.addEventListener("change", () => {
    state.offset = 0;
    exec();
  });

  mimeInput?.addEventListener("change", () => {
    state.offset = 0;
    exec();
  });

  selectAll?.addEventListener("change", () => {
    const checked = selectAll.checked;
    document.querySelectorAll(".mesh-search-check").forEach((cb) => {
      cb.checked = checked;
    });
    updateSelectionStats();
  });

  dlSelected?.addEventListener("click", () => {
    void downloadSelected(statusEl);
  });

  prevBtn?.addEventListener("click", () => {
    state.offset = Math.max(0, (state.offset || 0) - PAGE_SIZE);
    exec();
  });

  nextBtn?.addEventListener("click", () => {
    state.offset = (state.offset || 0) + PAGE_SIZE;
    exec();
  });

  exec();
}
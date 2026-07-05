/**
 * Admin document generators — run white paper builders from the service admin UI.
 */

import { apiUrl } from "./miner-paths.js";

function formatBytes(n) {
  const v = Number(n) || 0;
  if (v >= 1024 * 1024) return `${(v / (1024 * 1024)).toFixed(1)} MiB`;
  if (v >= 1024) return `${(v / 1024).toFixed(1)} KiB`;
  return v ? `${v} B` : "—";
}

function formatTime(ts) {
  const n = Number(ts) || 0;
  if (!n) return "—";
  return new Date(n * 1000).toLocaleString();
}

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function optionsFromForm(form) {
  return {
    copy_downloads: !!form.querySelector('[name="copy_downloads"]')?.checked,
    publish_mesh: !!form.querySelector('[name="publish_mesh"]')?.checked,
    sync_worker: !!form.querySelector('[name="sync_worker"]')?.checked,
  };
}

async function runGenerator(genId, options, statusEl) {
  if (statusEl) statusEl.textContent = "Running…";
  const res = await fetch(apiUrl(`/admin/api/generators/${encodeURIComponent(genId)}/run`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(options),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    const err = data.error || `run failed (${res.status})`;
    if (statusEl) statusEl.textContent = err;
    throw new Error(err);
  }
  const parts = ["Done"];
  if (data.output?.size) parts.push(formatBytes(data.output.size));
  if (data.duration_sec) parts.push(`${data.duration_sec}s`);
  if (data.post?.mesh?.anchor_txid) {
    parts.push(`anchored ${String(data.post.mesh.anchor_txid).slice(0, 12)}…`);
  }
  if (statusEl) statusEl.textContent = parts.join(" · ");
  return data;
}

function renderGeneratorRow(item) {
  const out = item.output || {};
  const dl = item.downloads || {};
  const last = item.last_run || {};
  const lastLabel = last.ok
    ? `Last OK ${formatTime(last.finished_at || last.started_at)}`
    : last.error
      ? `Last failed: ${last.error}`
      : "Never run";
  const scriptOk = item.script_exists ? "" : ' <span class="mesh-upload-status error">script missing</span>';
  const dlLink = item.downloads_url
    ? `<a href="${escapeHtml(item.downloads_url)}" target="_blank" rel="noopener">/downloads/</a>`
    : "";

  return (
    `<article class="admin-gen-card" data-gen-id="${escapeHtml(item.id)}">` +
    `<div class="admin-gen-head">` +
    `<h3>${escapeHtml(item.title)}</h3>` +
    `<span class="muted small admin-gen-badge">${escapeHtml(item.category)} · ${escapeHtml(item.runtime)}</span>` +
    `</div>` +
    `<p class="muted small">${escapeHtml(item.description)}${scriptOk}</p>` +
    `<dl class="admin-gen-meta muted small">` +
    `<div><dt>Output</dt><dd>${out.exists ? `${escapeHtml(out.path?.split("/").pop() || "")} (${formatBytes(out.size)})` : "—"}</dd></div>` +
    `<div><dt>Downloads</dt><dd>${dl.exists ? formatBytes(dl.size) : "—"} ${dlLink}</dd></div>` +
    `<div><dt>Mesh key</dt><dd class="mono">${escapeHtml(item.mesh_key || "—")}</dd></div>` +
    `<div><dt>Status</dt><dd>${escapeHtml(lastLabel)}</dd></div>` +
    `</dl>` +
    `<form class="admin-gen-run-form stack-form">` +
    `<input type="hidden" name="gen_id" value="${escapeHtml(item.id)}">` +
    `<label class="mesh-upload-check"><input type="checkbox" name="copy_downloads" checked> Copy to /downloads/</label>` +
    `<label class="mesh-upload-check"><input type="checkbox" name="publish_mesh"> Publish to chain mesh + BSM1 anchor</label>` +
    `<label class="mesh-upload-check"><input type="checkbox" name="sync_worker" checked> Sync to downloads worker</label>` +
    `<div class="btn-row">` +
    `<button type="submit" class="btn btn-small">Run generator</button>` +
    `</div>` +
    `<p class="muted small mesh-upload-status admin-gen-status"></p>` +
    `</form>` +
    `</article>`
  );
}

function renderUtilityRow(item) {
  const last = item.last_run || {};
  const lastLabel = last.ok
    ? `Last OK ${formatTime(last.finished_at || last.started_at)}`
    : last.error
      ? `Last failed: ${last.error}`
      : "Never run";
  return (
    `<article class="admin-gen-card" data-gen-id="${escapeHtml(item.id)}">` +
    `<div class="admin-gen-head">` +
    `<h3>${escapeHtml(item.title)}</h3>` +
    `<span class="muted small admin-gen-badge">utility · ${escapeHtml(item.runtime)}</span>` +
    `</div>` +
    `<p class="muted small">${escapeHtml(item.description)}</p>` +
    `<p class="muted small mono">${escapeHtml(item.script)}</p>` +
    `<p class="muted small">${escapeHtml(lastLabel)}</p>` +
    `<form class="admin-gen-run-form stack-form">` +
    `<input type="hidden" name="gen_id" value="${escapeHtml(item.id)}">` +
    `<div class="btn-row"><button type="submit" class="btn btn-small btn-ghost">Run</button></div>` +
    `<p class="muted small mesh-upload-status admin-gen-status"></p>` +
    `</form>` +
    `</article>`
  );
}

export async function refreshAdminGenerators() {
  const list = document.getElementById("admin-generators-list");
  const utils = document.getElementById("admin-generators-utils");
  const globalStatus = document.getElementById("admin-generators-global-status");
  if (!list) return;

  if (globalStatus) globalStatus.textContent = "Loading catalog…";
  const res = await fetch(apiUrl("/admin/api/generators"), { credentials: "same-origin" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    if (globalStatus) globalStatus.textContent = data.error || "Failed to load generators";
    return;
  }

  list.innerHTML = (data.generators || []).map(renderGeneratorRow).join("") || '<p class="muted">No generators.</p>';
  if (utils) {
    utils.innerHTML = (data.utilities || []).map(renderUtilityRow).join("") || "";
  }
  if (globalStatus) globalStatus.textContent = `${(data.generators || []).length} generators · ${(data.utilities || []).length} utilities`;

  document.querySelectorAll(".admin-gen-run-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const genId = form.querySelector('[name="gen_id"]')?.value;
      if (!genId) return;
      const statusEl = form.querySelector(".admin-gen-status");
      const btn = form.querySelector('button[type="submit"]');
      if (btn) btn.disabled = true;
      try {
        await runGenerator(genId, optionsFromForm(form), statusEl);
        await refreshAdminGenerators();
      } catch (err) {
        if (statusEl) statusEl.textContent = err.message || String(err);
      } finally {
        if (btn) btn.disabled = false;
      }
    });
  });
}

export function initAdminGenerators() {
  const refreshBtn = document.getElementById("admin-generators-refresh");
  refreshBtn?.addEventListener("click", () => {
    void refreshAdminGenerators();
  });
  void refreshAdminGenerators();
}
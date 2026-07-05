/**
 * Chain mesh asset library — browse, view, edit metadata, download, replace files.
 */

import { apiUrl } from "./miner-paths.js";
import { fetchMeshAssetManifest, reconstructMeshAssetFromKey } from "./mesh-asset-reconstruct.js";
import { publishMeshAssetFromFile, resolveMeshPublishToken } from "./mesh-asset-publish.js";

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

let meshAdminMode = false;
let cachedPublishToken = "";

function meshAdminEnabled() {
  return meshAdminMode || document.body?.dataset?.meshAdmin === "1";
}

async function publishToken() {
  if (cachedPublishToken) return cachedPublishToken;
  const form = document.getElementById("mesh-asset-upload-form");
  const preset = form?.dataset?.publishToken || "";
  if (preset) {
    cachedPublishToken = preset;
    return preset;
  }
  if (!meshAdminEnabled()) return "";
  cachedPublishToken = await resolveMeshPublishToken();
  return cachedPublishToken;
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function triggerDownload(bytes, filename, mime) {
  const blob = new Blob([bytes], { type: mime || "application/octet-stream" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "mesh-download";
  a.click();
  URL.revokeObjectURL(url);
}

function ensureModal() {
  let modal = document.getElementById("mesh-asset-modal");
  if (modal) return modal;

  modal = document.createElement("div");
  modal.id = "mesh-asset-modal";
  modal.className = "mesh-asset-modal";
  modal.hidden = true;
  modal.innerHTML = `
    <div class="mesh-asset-modal-backdrop" data-mesh-modal-close></div>
    <div class="mesh-asset-modal-card" role="dialog" aria-labelledby="mesh-asset-modal-title">
      <header class="mesh-asset-modal-head">
        <h3 id="mesh-asset-modal-title">Mesh asset</h3>
        <button type="button" class="btn btn-ghost btn-small" data-mesh-modal-close aria-label="Close">✕</button>
      </header>
      <div class="mesh-asset-modal-body" id="mesh-asset-modal-body"></div>
      <footer class="mesh-asset-modal-foot" id="mesh-asset-modal-foot"></footer>
    </div>
  `;
  document.body.appendChild(modal);

  modal.querySelectorAll("[data-mesh-modal-close]").forEach((el) => {
    el.addEventListener("click", () => closeModal());
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) closeModal();
  });
  return modal;
}

function closeModal() {
  const modal = document.getElementById("mesh-asset-modal");
  if (modal) modal.hidden = true;
}

function openModal(title, bodyHtml, footHtml = "") {
  const modal = ensureModal();
  const titleEl = document.getElementById("mesh-asset-modal-title");
  const bodyEl = document.getElementById("mesh-asset-modal-body");
  const footEl = document.getElementById("mesh-asset-modal-foot");
  if (titleEl) titleEl.textContent = title || "Mesh asset";
  if (bodyEl) bodyEl.innerHTML = bodyHtml;
  if (footEl) footEl.innerHTML = footHtml;
  modal.hidden = false;
}

function downloadUrl(assetKey) {
  return apiUrl(`/api/chain-mesh/asset/${encodeURI(assetKey)}/download`);
}

export async function downloadAsset(assetKey, statusEl) {
  if (statusEl) statusEl.textContent = `Downloading ${assetKey}…`;
  try {
    const manifest = await fetchMeshAssetManifest(assetKey);
    const filename = (manifest.display_name || assetKey.split("/").pop() || "download").replace(
      /[^\w.\-+]+/g,
      "_",
    );
    const res = await fetch(downloadUrl(assetKey));
    if (!res.ok) {
      const bytes = await reconstructMeshAssetFromKey(assetKey);
      triggerDownload(bytes, filename, manifest.mime_type);
      if (statusEl) {
        statusEl.textContent = `Verified and saved ${filename} (${formatBytes(bytes.length)}).`;
      }
      return;
    }
    const blob = await res.blob();
    triggerDownload(blob, filename, manifest.mime_type || blob.type);
    if (statusEl) {
      statusEl.textContent = `Downloaded ${filename} (${formatBytes(blob.size)}).`;
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = err.message || String(err);
  }
}

async function viewAsset(assetKey) {
  openModal("Loading…", '<p class="muted small">Fetching manifest…</p>');
  try {
    const [manifest, previewRes, versionsRes] = await Promise.all([
      fetchMeshAssetManifest(assetKey),
      fetch(apiUrl(`/api/chain-mesh/asset/${encodeURI(assetKey)}/preview`)),
      fetch(apiUrl(`/api/chain-mesh/asset/${encodeURI(assetKey)}/versions?limit=10`)),
    ]);
    const preview = previewRes.ok ? await previewRes.json() : { preview_kind: "none" };
    const versions = versionsRes.ok ? await versionsRes.json() : { versions: [] };

    let previewHtml = '<p class="muted small">No inline preview for this file type — use Download.</p>';
    if (preview.preview_kind === "text" && preview.text != null) {
      previewHtml = `<pre class="mesh-asset-preview-text">${escapeHtml(preview.text)}</pre>`;
    } else if (preview.preview_kind === "image" && preview.data_b64) {
      const mime = preview.mime_type || "image/png";
      previewHtml = `<img class="mesh-asset-preview-image" alt="" src="data:${mime};base64,${preview.data_b64}">`;
    } else if (preview.note) {
      previewHtml = `<p class="muted small">${escapeHtml(preview.note)}</p>`;
    }

    const versionRows = (versions.versions || [])
      .map(
        (row) =>
          `<tr${row.is_current ? ' class="mesh-asset-current-row"' : ""}>` +
          `<td>${escapeHtml(row.version || "—")}</td>` +
          `<td>${formatBytes(row.file_size)}</td>` +
          `<td class="mono small">${escapeHtml(String(row.file_sha256 || "").slice(0, 12))}…</td>` +
          `<td>${formatDate(row.created_at)}</td>` +
          `</tr>`,
      )
      .join("");

    const body = `
      <dl class="meta-dl compact mesh-asset-meta-dl">
        <dt>Asset key</dt><dd class="mono small">${escapeHtml(manifest.asset_key)}</dd>
        <dt>Display name</dt><dd>${escapeHtml(manifest.display_name)}</dd>
        <dt>Version</dt><dd>${escapeHtml(manifest.version || "—")}</dd>
        <dt>MIME</dt><dd class="mono small">${escapeHtml(manifest.mime_type || "—")}</dd>
        <dt>Size</dt><dd>${formatBytes(manifest.file_size)}</dd>
        <dt>SHA-256</dt><dd class="mono small">${escapeHtml(manifest.file_sha256)}</dd>
        <dt>Merkle root</dt><dd class="mono small">${escapeHtml(manifest.merkle_root)}</dd>
        <dt>Chunks</dt><dd>${manifest.chunk_count ?? manifest.chunks?.length ?? "—"}</dd>
        <dt>On-chain anchor</dt><dd class="mono small">${manifest.anchor_txid ? `${escapeHtml(String(manifest.anchor_txid).slice(0, 20))}… @ ${manifest.anchor_height || "?"}` : "—"}</dd>
        <dt>Published</dt><dd>${formatDate(manifest.created_at)}</dd>
      </dl>
      <h4 class="mesh-asset-section-title">Preview</h4>
      ${previewHtml}
      ${
        versionRows
          ? `<h4 class="mesh-asset-section-title">Revision history</h4>
             <div class="table-wrap">
               <table class="mesh-asset-versions-table">
                 <thead><tr><th>Version</th><th>Size</th><th>SHA-256</th><th>Published</th></tr></thead>
                 <tbody>${versionRows}</tbody>
               </table>
             </div>`
          : ""
      }
    `;

    const adminActions = meshAdminEnabled()
      ? `<button type="button" class="btn btn-ghost btn-small" data-mesh-action="edit" data-asset-key="${escapeHtml(assetKey)}">Edit</button>
         <button type="button" class="btn btn-ghost btn-small" data-mesh-action="replace" data-asset-key="${escapeHtml(assetKey)}">Replace file</button>`
      : "";
    const foot = `
      <a class="btn btn-small" href="${downloadUrl(assetKey)}" download>Download</a>
      ${adminActions}
    `;
    openModal(manifest.display_name || manifest.asset_key, body, foot);
    wireModalActions();
  } catch (err) {
    openModal("Error", `<p class="mesh-upload-status error">${escapeHtml(err.message || err)}</p>`);
  }
}

function editAsset(assetKey, manifest = null) {
  const load = manifest
    ? Promise.resolve(manifest)
    : fetchMeshAssetManifest(assetKey);
  void load.then(async (data) => {
    const token = await publishToken();
    const body = `
      <p class="muted small">Update catalog labels. File bytes stay the same until you <strong>Replace file</strong> with a new upload.</p>
      <form id="mesh-asset-edit-form" class="mesh-asset-edit-form">
        <label class="mesh-upload-field">
          <span class="muted small">Display name</span>
          <input type="text" id="mesh-edit-name" value="${escapeHtml(data.display_name || "")}">
        </label>
        <label class="mesh-upload-field mesh-upload-field-inline">
          <span class="muted small">Version label</span>
          <input type="text" id="mesh-edit-version" class="mono" value="${escapeHtml(data.version || "")}">
        </label>
        <p class="muted small mono">Key: ${escapeHtml(data.asset_key)}</p>
        <p class="muted small mesh-upload-status" id="mesh-edit-status"></p>
      </form>
    `;
    const foot = `<button type="submit" form="mesh-asset-edit-form" class="btn btn-small">Save metadata</button>`;
    openModal(`Edit — ${data.display_name || data.asset_key}`, body, foot);

    const form = document.getElementById("mesh-asset-edit-form");
    const statusEl = document.getElementById("mesh-edit-status");
    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (statusEl) statusEl.textContent = "Saving…";
      try {
        const headers = { "Content-Type": "application/json" };
        if (token) headers["X-Chain-Mesh-Publish-Token"] = token;
        const res = await fetch(apiUrl(`/api/chain-mesh/asset/${encodeURI(assetKey)}`), {
          method: "PATCH",
          headers,
          body: JSON.stringify({
            display_name: document.getElementById("mesh-edit-name")?.value?.trim(),
            version: document.getElementById("mesh-edit-version")?.value?.trim(),
            publish_token: token || undefined,
          }),
        });
        const out = await res.json().catch(() => ({}));
        if (!res.ok || !out.ok) throw new Error(out.error || `save failed (${res.status})`);
        if (statusEl) statusEl.textContent = "Saved.";
        void refreshMeshAssetLibrary();
        window.setTimeout(() => viewAsset(assetKey), 400);
      } catch (err) {
        if (statusEl) statusEl.textContent = err.message || String(err);
      }
    });
  });
}

function replaceAsset(assetKey) {
  const input = document.createElement("input");
  input.type = "file";
  input.hidden = true;
  document.body.appendChild(input);
  input.addEventListener(
    "change",
    async () => {
      const file = input.files?.[0];
      input.remove();
      if (!file) return;
      openModal(
        "Replacing file…",
        `<p class="muted small">Uploading new content for <span class="mono">${escapeHtml(assetKey)}</span>. This publishes a new revision on the same key.</p>
         <p class="muted small" id="mesh-replace-status">Preparing…</p>`,
      );
      const statusEl = document.getElementById("mesh-replace-status");
      try {
        const token = await publishToken();
        if (!token) throw new Error("Admin login required to replace mesh files.");
        await publishMeshAssetFromFile(file, {
          assetKey,
          displayName: file.name,
          version: "",
          onProgress: (done, total, phase) => {
            if (!statusEl) return;
            statusEl.textContent =
              phase === "registering asset"
                ? "Registering manifest + anchor…"
                : `Uploading chunks ${done} / ${total}`;
          },
          publishToken: token,
        });
        if (statusEl) statusEl.textContent = "Replacement published.";
        void refreshMeshAssetLibrary();
        window.setTimeout(() => viewAsset(assetKey), 600);
      } catch (err) {
        if (statusEl) statusEl.textContent = err.message || String(err);
      }
    },
    { once: true },
  );
  input.click();
}

function wireModalActions() {
  const foot = document.getElementById("mesh-asset-modal-foot");
  if (!foot) return;
  foot.querySelectorAll("[data-mesh-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.getAttribute("data-mesh-action");
      const key = btn.getAttribute("data-asset-key");
      if (!key) return;
      if (action === "edit") editAsset(key);
      if (action === "replace") replaceAsset(key);
    });
  });
}

export function renderMeshAssetCatalog(items, tbodySelector = "#nd-asset-catalog tbody") {
  const tbody = document.querySelector(tbodySelector);
  if (!tbody) return;
  const admin = meshAdminEnabled();
  if (!items?.length) {
    tbody.innerHTML = admin
      ? '<tr><td colspan="7" class="muted">No published mesh assets yet. Upload a file above.</td></tr>'
      : '<tr><td colspan="7" class="muted">No published mesh assets yet.</td></tr>';
    return;
  }
  tbody.innerHTML = items
    .map((row) => {
      const key = row.asset_key || row.key || "";
      const name = row.display_name || key;
      const anchor = row.anchor_txid
        ? `${String(row.anchor_txid).slice(0, 12)}…`
        : "—";
      return (
        `<tr data-asset-key="${escapeHtml(key)}">` +
        `<td class="mono small" title="${escapeHtml(key)}">${escapeHtml(name)}</td>` +
        `<td class="mono small">${escapeHtml(key.split("/").slice(-1)[0] || key)}</td>` +
        `<td>${escapeHtml(row.version || "—")}</td>` +
        `<td>${formatBytes(row.file_size)}</td>` +
        `<td>${row.chunk_count ?? "—"}</td>` +
        `<td class="mono small">${anchor}</td>` +
        `<td class="mesh-asset-actions">` +
        `<button type="button" class="btn btn-ghost btn-small" data-mesh-lib="view" data-asset-key="${escapeHtml(key)}">View</button> ` +
        (admin
          ? `<button type="button" class="btn btn-ghost btn-small" data-mesh-lib="edit" data-asset-key="${escapeHtml(key)}">Edit</button> `
          : "") +
        `<button type="button" class="btn btn-ghost btn-small" data-mesh-lib="download" data-asset-key="${escapeHtml(key)}">Download</button>` +
        `</td>` +
        `</tr>`
      );
    })
    .join("");

  tbody.querySelectorAll("[data-mesh-lib]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.getAttribute("data-mesh-lib");
      const key = btn.getAttribute("data-asset-key");
      if (!key) return;
      const statusEl = document.getElementById("nd-receive-status") ||
        document.getElementById("mesh-library-status");
      if (action === "view") void viewAsset(key);
      if (action === "edit") editAsset(key);
      if (action === "download") void downloadAsset(key, statusEl);
    });
  });
}

let refreshHook = null;

function catalogSelectors() {
  return ["#nd-asset-catalog tbody", "#mesh-asset-library tbody"].filter((sel) =>
    document.querySelector(sel),
  );
}

export async function refreshMeshAssetLibrary(limit = 100) {
  try {
    const res = await fetch(apiUrl(`/api/chain-mesh/assets?limit=${limit}`));
    if (!res.ok) return null;
    const data = await res.json();
    const items = data.assets || data.items || [];
    const countEl = document.getElementById("nd-asset-count") ||
      document.getElementById("mesh-library-count");
    if (countEl) countEl.textContent = String(items.length);
    const selectors = catalogSelectors();
    if (!selectors.length) {
      renderMeshAssetCatalog(items);
    } else {
      selectors.forEach((sel) => renderMeshAssetCatalog(items, sel));
    }
    refreshHook?.(items);
    return items;
  } catch (_) {
    catalogSelectors().forEach((sel) => {
      const tbody = document.querySelector(sel);
      if (tbody) {
        tbody.innerHTML = '<tr><td colspan="7" class="muted">Could not load catalog.</td></tr>';
      }
    });
    return null;
  }
}

export function initMeshAssetLibrary(options = {}) {
  meshAdminMode = Boolean(options.admin);
  refreshHook = options.onRefresh || null;
  ensureModal();

  document.querySelectorAll("#mesh-library-search").forEach((searchInput) => {
    searchInput.addEventListener("input", () => {
      const q = searchInput.value.trim().toLowerCase();
      document
        .querySelectorAll(
          "#mesh-asset-library tbody tr[data-asset-key], #nd-asset-catalog tbody tr[data-asset-key]",
        )
        .forEach((row) => {
          const key = (row.getAttribute("data-asset-key") || "").toLowerCase();
          const text = row.textContent?.toLowerCase() || "";
          row.hidden = Boolean(q) && !key.includes(q) && !text.includes(q);
        });
    });
  });

  void refreshMeshAssetLibrary(options.limit || 100);
  if (!options.pollMs) return;
  window.setInterval(() => {
    void refreshMeshAssetLibrary(options.limit || 100);
  }, options.pollMs);
}
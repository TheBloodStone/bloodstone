/**
 * Network Data Portal — live mesh stats + asset library.
 */

import { apiUrl } from "./miner-paths.js";
import { initMeshAssetLibrary, refreshMeshAssetLibrary } from "./mesh-asset-library.js";
import {
  fetchWritableMeshKeys,
  initMeshAssetUserSubmit,
  refreshWritableKeyDatalist,
  resolveMeshPublishToken,
} from "./mesh-asset-publish.js";
import { reconstructMeshAssetFromKey } from "./mesh-asset-reconstruct.js";
import { sendMeshToKey, sendMeshTransfer } from "./mesh-transfer.js";

function formatBytes(n) {
  const v = Number(n) || 0;
  if (v >= 1024 * 1024) return `${(v / (1024 * 1024)).toFixed(2)} MiB`;
  if (v >= 1024) return `${(v / 1024).toFixed(1)} KiB`;
  return `${v} B`;
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

async function refreshPortalStats() {
  try {
    const [nodesRes, statusRes] = await Promise.all([
      fetch(apiUrl("/api/network/nodes")),
      fetch(apiUrl("/api/chain-mesh/status")),
    ]);

    if (nodesRes.ok) {
      const nodes = await nodesRes.json();
      const totalEl = document.getElementById("nd-network-total");
      const peersEl = document.getElementById("nd-mesh-peers");
      if (totalEl) totalEl.textContent = String(nodes.total_connected ?? "—");
      if (peersEl) peersEl.textContent = String(nodes.mesh_storage_peers ?? "—");
    }

    if (statusRes.ok) {
      const status = await statusRes.json();
      const coordEl = document.getElementById("nd-coordinator-chunks");
      if (coordEl) {
        coordEl.textContent = String(status.coordinator_chunks ?? status.coverage?.have ?? "—");
      }
    }

    await refreshMeshAssetLibrary(100);
  } catch (_) {
    /* library module shows its own error row */
  }
}

function renderWritableKeysList(keys) {
  const listEl = document.getElementById("mesh-writable-keys-list-ui");
  const countEl = document.getElementById("mesh-writable-keys-count");
  if (countEl) countEl.textContent = String(keys.length);
  if (!listEl) return;
  if (!keys.length) {
    listEl.innerHTML = "<li class=\"muted\">No published mesh keys yet.</li>";
    return;
  }
  listEl.innerHTML = keys
    .slice(0, 80)
    .map((row) => {
      const key = row.asset_key || "";
      const badge = row.admin_only ? "downloads" : "assets";
      return (
        `<li><button type="button" class="btn btn-ghost btn-small nd-key-pick" data-asset-key="${key.replace(/"/g, "&quot;")}">` +
        `<span class="mono">${key}</span> — ${row.display_name || key} (${formatBytes(row.file_size)})` +
        ` <span class="muted">[${badge}]</span></button></li>`
      );
    })
    .join("");
  listEl.querySelectorAll(".nd-key-pick").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.getAttribute("data-asset-key") || "";
      const sendKey = document.getElementById("mesh-send-key");
      const submitKey = document.getElementById("mesh-asset-submit-key");
      const receiveKey = document.getElementById("nd-receive-key");
      if (sendKey) sendKey.value = key;
      if (submitKey && key.startsWith("assets/")) submitKey.value = key;
      if (receiveKey) receiveKey.value = key;
    });
  });
}

async function loadWritableKeys() {
  const keys = await refreshWritableKeyDatalist("mesh-writable-keys-list");
  renderWritableKeysList(keys);
  return keys;
}

function initMeshSendForm() {
  const form = document.getElementById("mesh-send-to-key-form");
  if (!form) return;

  const fileInput = document.getElementById("mesh-send-file");
  const keyInput = document.getElementById("mesh-send-key");
  const recipientInput = document.getElementById("mesh-send-recipient");
  const senderInput = document.getElementById("mesh-send-sender");
  const submitBtn = document.getElementById("mesh-send-btn");
  const statusEl = document.getElementById("mesh-send-status");
  const progressEl = document.getElementById("mesh-send-progress");

  const setStatus = (text, kind = "") => {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.className = `muted small mesh-upload-status${kind ? ` ${kind}` : ""}`;
  };

  fileInput?.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (!file || keyInput?.value) return;
    keyInput.value = `assets/${file.name.replace(/[^\w.\-+]+/g, "-")}`;
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = fileInput?.files?.[0];
    const assetKey = keyInput?.value?.trim() || "";
    const recipient = recipientInput?.value?.trim() || "";
    const sender = senderInput?.value?.trim() || "";
    if (!file || !assetKey) {
      setStatus("Choose a file and mesh asset key.", "error");
      return;
    }

    const keys = await fetchWritableMeshKeys().catch(() => ({ keys: [] }));
    const existing = (keys.keys || []).find((k) => k.asset_key === assetKey);
    if (existing) {
      const ok = window.confirm(
        `Replace mesh file at ${assetKey}?\nCurrent: ${existing.display_name || existing.asset_key}`,
      );
      if (!ok) return;
    }

    submitBtn.disabled = true;
    setStatus("Preparing…");
    if (progressEl) progressEl.textContent = "";

    try {
      if (recipient && sender) {
        if (progressEl) progressEl.textContent = "BSM2 transfer + mesh update…";
        const result = await sendMeshTransfer(file, {
          sender,
          recipient,
          assetKey,
          displayName: file.name,
          onProgress: (_done, _total, phase) => {
            if (progressEl) progressEl.textContent = phase || "working…";
          },
        });
        const tid = result.transfer_id ? ` · transfer ${result.transfer_id.slice(0, 12)}…` : "";
        setStatus(`Sent to ${recipient} at key ${assetKey}${tid}`, "ok");
      } else {
        const publishToken = await resolveMeshPublishToken();
        if (assetKey.startsWith("downloads/") && !publishToken) {
          throw new Error("Admin login required to update downloads/ mesh keys.");
        }
        if (progressEl) progressEl.textContent = publishToken ? "Publishing…" : "Submitting for review…";
        const result = await sendMeshToKey(file, {
          assetKey,
          displayName: file.name,
          publishToken,
          submitForReview: !publishToken,
          onProgress: (done, total, phase) => {
            if (progressEl) {
              progressEl.textContent =
                phase === "submitting for review"
                  ? "Submitting for admin review…"
                  : phase === "registering asset"
                    ? "Registering on mesh…"
                    : `Uploading chunks ${done} / ${total}`;
            }
          },
        });
        if (result.pending) {
          setStatus(`Submitted ${result.asset_key} for admin review (#${result.submission_id}).`, "ok");
        } else {
          setStatus(`Updated mesh key ${result.asset_key} (${result.chunk_count} chunks).`, "ok");
        }
      }
      form.reset();
      if (keyInput) keyInput.value = "";
      if (progressEl) progressEl.textContent = "";
      void loadWritableKeys();
      void refreshMeshAssetLibrary(100);
    } catch (err) {
      setStatus(err.message || String(err), "error");
    } finally {
      submitBtn.disabled = false;
    }
  });
}

async function receiveAsset(assetKey) {
  const statusEl = document.getElementById("nd-receive-status");
  const keyInput = document.getElementById("nd-receive-key");
  if (keyInput) keyInput.value = assetKey;
  if (statusEl) statusEl.textContent = `Fetching ${assetKey}…`;

  try {
    const bytes = await reconstructMeshAssetFromKey(assetKey, {
      onProgress: ({ downloaded, total }) => {
        if (statusEl) {
          statusEl.textContent = `Downloading ${assetKey}… ${formatBytes(downloaded)} / ${formatBytes(total)}`;
        }
      },
    });
    const manifestRes = await fetch(apiUrl(`/api/chain-mesh/asset/${encodeURI(assetKey)}`));
    const manifest = manifestRes.ok ? await manifestRes.json() : {};
    const filename = (manifest.display_name || assetKey.split("/").pop() || "download").replace(
      /[^\w.\-+]+/g,
      "_",
    );
    triggerDownload(bytes, filename, manifest.mime_type);
    if (statusEl) {
      statusEl.textContent = `Verified and saved ${filename} (${formatBytes(bytes.length)}).`;
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = err.message || String(err);
  }
}

export function initNetworkDataPortal() {
  const receiveBtn = document.getElementById("nd-receive-btn");
  const receiveKey = document.getElementById("nd-receive-key");

  receiveBtn?.addEventListener("click", () => {
    const key = (receiveKey?.value || "").trim();
    if (!key) return;
    void receiveAsset(key);
  });

  receiveKey?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      receiveBtn?.click();
    }
  });

  initMeshAssetUserSubmit();
  initMeshSendForm();
  initMeshAssetLibrary({ limit: 100 });
  void loadWritableKeys();
  void refreshPortalStats();
  window.setInterval(() => {
    void refreshPortalStats();
  }, 60000);
}
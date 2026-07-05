/**
 * Network Data Portal — live mesh stats + asset library.
 */

import { apiUrl } from "./miner-paths.js";
import { initMeshAssetLibrary, refreshMeshAssetLibrary } from "./mesh-asset-library.js";
import { initMeshAssetUserSubmit } from "./mesh-asset-publish.js";
import { reconstructMeshAssetFromKey } from "./mesh-asset-reconstruct.js";

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
  initMeshAssetLibrary({ limit: 100 });
  void refreshPortalStats();
  window.setInterval(() => {
    void refreshPortalStats();
  }, 60000);
}
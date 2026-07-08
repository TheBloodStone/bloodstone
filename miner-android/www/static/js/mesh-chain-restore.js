/**
 * Restore bloodstoned block files from locally cached mesh chunks (overlay or replace).
 */

import { readNodeModeFromUi, activateNodeWithoutMining, stopLocalNode } from "./local-node.js";
import { isCapacitorAndroid } from "./device-fleet.js";
import { isAndroidAppContext, whenCapacitorReady } from "./capacitor-ready.js";

const OVERLAY_MODE_KEY = "bloodstone-mesh-chain-overlay-mode";

function formatBytes(n) {
  const v = Number(n) || 0;
  if (v >= 1024 * 1024) return `${(v / (1024 * 1024)).toFixed(2)} MiB`;
  if (v >= 1024) return `${(v / 1024).toFixed(1)} KiB`;
  return `${v} B`;
}

function localNodePlugin() {
  const cap = window.Capacitor;
  if (!cap) return null;
  const raw = cap.Plugins?.BloodstoneLocalNode;
  const hasNative = typeof cap.nativePromise === "function";
  if (!raw && !hasNative) return null;
  const call = (method, args = {}) => {
    if (raw && typeof raw[method] === "function") {
      return raw[method](args);
    }
    if (hasNative) {
      return cap.nativePromise("BloodstoneLocalNode", method, args);
    }
    throw new Error(`BloodstoneLocalNode.${method} unavailable`);
  };
  return { applyMeshChunksToDatadir: (opts) => call("applyMeshChunksToDatadir", opts) };
}

export function getMeshChainOverlayMode() {
  try {
    const raw = localStorage.getItem(OVERLAY_MODE_KEY);
    return raw === "replace" ? "replace" : "overlay";
  } catch (_) {
    return "overlay";
  }
}

export function setMeshChainOverlayMode(mode) {
  const value = mode === "replace" ? "replace" : "overlay";
  try {
    localStorage.setItem(OVERLAY_MODE_KEY, value);
  } catch (_) {
    /* ignore */
  }
  return value;
}

export async function restoreChainFromLocalMesh({ onLog, overlayMode } = {}) {
  if (!isCapacitorAndroid() && !isAndroidAppContext()) {
    throw new Error("Mesh chain restore requires the Bloodstone Android app.");
  }
  await whenCapacitorReady();
  const plugin = localNodePlugin();
  if (!plugin?.applyMeshChunksToDatadir) {
    throw new Error("Install APK 1.3.47+ for mesh chain restore.");
  }
  const mode = readNodeModeFromUi();
  const overlay = overlayMode || getMeshChainOverlayMode();
  onLog?.(
    overlay === "replace"
      ? "Stopping node and replacing block files from local mesh chunks…"
      : "Stopping node and overlaying block files from local mesh chunks…",
    "warn",
  );
  await stopLocalNode({ foregroundOnly: false });
  const result = await plugin.applyMeshChunksToDatadir({
    nodeMode: mode,
    overlayMode: overlay,
  });
  const chunks = Number(result?.chunksApplied) || 0;
  const bytes = Number(result?.bytesWritten) || 0;
  const files = Number(result?.filesTouched) || 0;
  if (chunks <= 0) {
    throw new Error("No mesh chunks were written — sync Time Capsule or import a mesh backup first.");
  }
  onLog?.(
    `Mesh restore wrote ${chunks} chunk(s) into ${files} file(s) (${formatBytes(bytes)})${
      result?.reindexRequired ? " — bloodstoned will reindex on next start" : ""
    }`,
    "success",
  );
  await activateNodeWithoutMining({ onLog });
  return result;
}

export function initMeshChainRestoreUi({ onLog } = {}) {
  const overlaySelect = document.getElementById("mesh-chain-overlay-mode");
  const restoreBtn = document.getElementById("mesh-chain-restore-btn");
  const statusEl = document.getElementById("mesh-chain-restore-status");
  if (overlaySelect) {
    overlaySelect.value = getMeshChainOverlayMode();
    overlaySelect.addEventListener("change", () => {
      setMeshChainOverlayMode(overlaySelect.value);
      if (statusEl) {
        statusEl.textContent =
          overlaySelect.value === "replace"
            ? "Replace mode clears existing blocks/ before writing mesh data."
            : "Overlay mode writes mesh chunks on top of existing block files.";
      }
    });
  }
  restoreBtn?.addEventListener("click", () => {
    if (statusEl) statusEl.textContent = "Applying local mesh chunks to chain datadir…";
    restoreBtn.disabled = true;
    void restoreChainFromLocalMesh({
      onLog: (msg, kind) => {
        onLog?.(msg, kind);
        if (statusEl) statusEl.textContent = msg;
      },
      overlayMode: overlaySelect?.value || getMeshChainOverlayMode(),
    })
      .then((result) => {
        if (statusEl) {
          statusEl.textContent = `Done — ${result.chunksApplied} chunk(s) applied. Keep app open while bloodstoned loads.`;
        }
      })
      .catch((err) => {
        const msg = err?.message || String(err);
        onLog?.(msg, "error");
        if (statusEl) statusEl.textContent = msg;
      })
      .finally(() => {
        restoreBtn.disabled = false;
      });
  });
}
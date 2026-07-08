/**
 * Pin complete mesh assets on this device — all chunks + manifest kept for backup and LAN sharing.
 */

import { apiUrl } from "./miner-paths.js";
import {
  downloadMeshChunk,
  importLocalMeshChunks,
  resolveDeviceId,
  exportLocalMeshChunks,
} from "./chain-mesh.js";
import { fetchMeshAssetManifest } from "./mesh-asset-reconstruct.js";

const PIN_REGISTRY_KEY = "bloodstone-mesh-pinned-assets-v1";
const PIN_FILE_DB = "bloodstone-mesh-pinned-files";
const PIN_FILE_STORE = "files";
const MAX_PINNED_FILE_BYTES = 48 * 1024 * 1024;

function loadRegistry() {
  try {
    const raw = localStorage.getItem(PIN_REGISTRY_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) {
    return [];
  }
}

function saveRegistry(entries) {
  localStorage.setItem(PIN_REGISTRY_KEY, JSON.stringify(entries));
}

export function listPinnedAssets() {
  return loadRegistry();
}

export function isAssetPinned(assetKey) {
  const key = String(assetKey || "").replace(/^\/+/, "");
  return loadRegistry().some((row) => row.asset_key === key);
}

export function getPinnedAsset(assetKey) {
  const key = String(assetKey || "").replace(/^\/+/, "");
  return loadRegistry().find((row) => row.asset_key === key) || null;
}

export function getPinnedChunkHashes() {
  const hashes = new Set();
  for (const row of loadRegistry()) {
    for (const hash of row.chunk_hashes || []) {
      hashes.add(String(hash).trim().toLowerCase());
    }
  }
  return hashes;
}

function upsertPinnedRecord(record) {
  const key = String(record.asset_key || "").replace(/^\/+/, "");
  const entries = loadRegistry().filter((row) => row.asset_key !== key);
  entries.unshift({
    ...record,
    asset_key: key,
    pinned_at: record.pinned_at || Date.now(),
  });
  saveRegistry(entries);
  return entries[0];
}

function removePinnedRecord(assetKey) {
  const key = String(assetKey || "").replace(/^\/+/, "");
  saveRegistry(loadRegistry().filter((row) => row.asset_key !== key));
}

let pinFileDbPromise = null;

function openPinFileDb() {
  if (pinFileDbPromise) return pinFileDbPromise;
  if (!("indexedDB" in window)) return Promise.resolve(null);
  pinFileDbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(PIN_FILE_DB, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(PIN_FILE_STORE)) {
        db.createObjectStore(PIN_FILE_STORE, { keyPath: "asset_key" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return pinFileDbPromise;
}

async function storePinnedFileBytes(assetKey, bytes, meta = {}) {
  if (!bytes?.length || bytes.length > MAX_PINNED_FILE_BYTES) return false;
  const db = await openPinFileDb();
  if (!db) return false;
  return new Promise((resolve, reject) => {
    const tx = db.transaction(PIN_FILE_STORE, "readwrite");
    tx.objectStore(PIN_FILE_STORE).put({
      asset_key: assetKey,
      bytes,
      file_size: bytes.length,
      file_sha256: meta.file_sha256 || "",
      saved_at: Date.now(),
    });
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => reject(tx.error);
  });
}

async function removePinnedFileBytes(assetKey) {
  const db = await openPinFileDb();
  if (!db) return false;
  return new Promise((resolve) => {
    const tx = db.transaction(PIN_FILE_STORE, "readwrite");
    tx.objectStore(PIN_FILE_STORE).delete(assetKey);
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => resolve(false);
  });
}

export async function getPinnedFileBytes(assetKey) {
  const db = await openPinFileDb();
  if (!db) return null;
  const key = String(assetKey || "").replace(/^\/+/, "");
  return new Promise((resolve) => {
    const tx = db.transaction(PIN_FILE_STORE, "readonly");
    const req = tx.objectStore(PIN_FILE_STORE).get(key);
    req.onsuccess = () => {
      const row = req.result;
      resolve(row?.bytes?.length ? row.bytes : null);
    };
    req.onerror = () => resolve(null);
  });
}

async function announcePinnedChunks(chunkHashes) {
  if (!chunkHashes?.length) return;
  const deviceId = await resolveDeviceId();
  try {
    const res = await fetch(apiUrl("/api/chain-mesh/peer"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_id: deviceId,
        peer_kind: window.Capacitor?.getPlatform?.() === "android" ? "android" : "browser",
        chunk_hashes: chunkHashes,
        capacity_bytes: chunkHashes.length * 256 * 1024,
        pin_reason: "asset_archive",
      }),
    });
    void res;
  } catch (_) {
    /* offline */
  }
}

async function storeChunkRecords(chunks, manifest, onProgress) {
  const assetKey = String(manifest.asset_key || "").replace(/^\/+/, "");
  const sourcePrefix = `pinned/${assetKey}`;
  let stored = 0;
  for (const chunk of chunks) {
    const hash = String(chunk.chunk_hash || chunk.hash || "").trim().toLowerCase();
    const bytes = chunk.data;
    if (!hash || !bytes?.length) {
      const downloaded = await downloadMeshChunk(hash);
      if (!downloaded?.length) {
        throw new Error(`missing chunk ${hash}`);
      }
      await importLocalMeshChunks({
        chunk_hash: hash,
        source_file: `${sourcePrefix}#${chunk.file_offset ?? 0}`,
        file_offset: Number(chunk.file_offset) || 0,
        size: Number(chunk.size) || downloaded.length,
        data: downloaded,
      });
    } else {
      await importLocalMeshChunks({
        chunk_hash: hash,
        source_file: `${sourcePrefix}#${chunk.file_offset ?? 0}`,
        file_offset: Number(chunk.file_offset) || 0,
        size: Number(chunk.size) || bytes.length,
        data: bytes,
      });
    }
    stored += 1;
    onProgress?.({
      phase: "chunks",
      stored,
      total: chunks.length,
      chunkHash: hash,
    });
  }
  return chunks.map((c) => String(c.chunk_hash || c.hash).trim().toLowerCase());
}

/**
 * Pin a published asset: download every chunk, keep on device, announce to mesh.
 */
export async function pinMeshAsset(assetKey, options = {}) {
  const key = String(assetKey || "").replace(/^\/+/, "");
  if (!key) throw new Error("asset key required");
  const manifest = options.manifest || (await fetchMeshAssetManifest(key));
  const chunks = [...(manifest.chunks || [])].sort(
    (a, b) => Number(a.file_offset) - Number(b.file_offset),
  );
  if (!chunks.length) throw new Error("asset has no chunks");

  options.onProgress?.({ phase: "start", total: chunks.length, assetKey: key });
  const chunkHashes = await storeChunkRecords(chunks, manifest, options.onProgress);

  let hasFullFile = false;
  if (options.storeFullFile !== false) {
    try {
      const { reconstructMeshAsset } = await import("./mesh-asset-reconstruct.js");
      const fileBytes = await reconstructMeshAsset(manifest, {
        onProgress: (p) =>
          options.onProgress?.({ phase: "verify", downloaded: p.downloaded, total: p.total }),
      });
      hasFullFile = await storePinnedFileBytes(key, fileBytes, manifest);
      options.onProgress?.({ phase: "file", bytes: fileBytes.length, stored: hasFullFile });
    } catch (_) {
      hasFullFile = false;
    }
  }

  const record = upsertPinnedRecord({
    asset_key: key,
    display_name: manifest.display_name || key,
    file_size: Number(manifest.file_size) || 0,
    file_sha256: manifest.file_sha256 || "",
    merkle_root: manifest.merkle_root || "",
    mime_type: manifest.mime_type || "",
    chunk_hashes: chunkHashes,
    chunk_count: chunkHashes.length,
    has_full_file: hasFullFile,
    share_enabled: options.shareEnabled !== false,
    pinned_at: Date.now(),
  });

  if (record.share_enabled) {
    await announcePinnedChunks(chunkHashes);
  }
  void refreshMeshAssetPinUi();
  return record;
}

/**
 * Pin right after local chunking (publish/submit) — bytes already in memory.
 */
export async function pinMeshAssetFromChunks(manifest, chunksWithData, options = {}) {
  const key = String(manifest.asset_key || "").replace(/^\/+/, "");
  const chunkHashes = await storeChunkRecords(chunksWithData, manifest, options.onProgress);
  let hasFullFile = false;
  if (options.storeFullFile !== false && manifest.file_size <= MAX_PINNED_FILE_BYTES) {
    try {
      const parts = [...chunksWithData].sort(
        (a, b) => Number(a.file_offset) - Number(b.file_offset),
      );
      const total = parts.reduce((sum, row) => sum + (row.data?.length || 0), 0);
      const out = new Uint8Array(total);
      let pos = 0;
      for (const row of parts) {
        out.set(row.data, pos);
        pos += row.data.length;
      }
      hasFullFile = await storePinnedFileBytes(key, out, manifest);
    } catch (_) {
      hasFullFile = false;
    }
  }
  const record = upsertPinnedRecord({
    asset_key: key,
    display_name: manifest.display_name || key,
    file_size: Number(manifest.file_size) || 0,
    file_sha256: manifest.file_sha256 || "",
    merkle_root: manifest.merkle_root || "",
    mime_type: manifest.mime_type || "",
    chunk_hashes: chunkHashes,
    chunk_count: chunkHashes.length,
    has_full_file: hasFullFile,
    share_enabled: options.shareEnabled !== false,
    pinned_at: Date.now(),
  });
  if (record.share_enabled) {
    await announcePinnedChunks(chunkHashes);
  }
  void refreshMeshAssetPinUi();
  return record;
}

export async function unpinMeshAsset(assetKey) {
  const key = String(assetKey || "").replace(/^\/+/, "");
  const record = getPinnedAsset(key);
  if (!record) return { removed: false };

  const { removeLocalMeshChunk } = await import("./chain-mesh.js");
  for (const hash of record.chunk_hashes || []) {
    const h = String(hash).trim().toLowerCase();
    const stillNeeded = loadRegistry().some(
      (row) =>
        row.asset_key !== key &&
        (row.chunk_hashes || []).some((x) => String(x).trim().toLowerCase() === h),
    );
    if (!stillNeeded) {
      await removeLocalMeshChunk(h);
    }
  }
  await removePinnedFileBytes(key);
  removePinnedRecord(key);
  void refreshMeshAssetPinUi();
  return { removed: true, asset_key: key };
}

export async function refreshPinnedAssetSharing() {
  const hashes = [...getPinnedChunkHashes()];
  if (hashes.length) await announcePinnedChunks(hashes);
  return hashes.length;
}

export async function pinnedStorageSummary() {
  const pinned = loadRegistry();
  const localChunks = await exportLocalMeshChunks();
  const localHashes = new Set(
    localChunks.map((row) => String(row.chunk_hash).trim().toLowerCase()),
  );
  let bytesHeld = 0;
  for (const row of pinned) {
    for (const hash of row.chunk_hashes || []) {
      const local = localChunks.find(
        (c) => String(c.chunk_hash).trim().toLowerCase() === String(hash).trim().toLowerCase(),
      );
      if (local?.data?.length) bytesHeld += local.data.length;
    }
  }
  return {
    pinned_count: pinned.length,
    chunk_hashes: getPinnedChunkHashes().size,
    bytes_held: bytesHeld,
    chunks_on_disk: localHashes.size,
    assets: pinned,
  };
}

let pinUiRefresh = null;

export function refreshMeshAssetPinUi() {
  return pinUiRefresh?.();
}

export function initMeshAssetPinUi(root = document) {
  const listEl = root.getElementById("mesh-pinned-assets-list");
  const statusEl = root.getElementById("mesh-pinned-status");
  if (!listEl) return;

  async function render() {
    const summary = await pinnedStorageSummary();
    if (statusEl) {
      statusEl.textContent =
        summary.pinned_count > 0
          ? `${summary.pinned_count} file(s) pinned · ${(summary.bytes_held / (1024 * 1024)).toFixed(1)} MiB chunks on device`
          : "No files pinned on this device yet.";
    }
    if (!summary.assets.length) {
      listEl.innerHTML = '<li class="muted">Pin files from the catalog with “Keep on device”.</li>';
      return;
    }
    listEl.innerHTML = summary.assets
      .map((row) => {
        const name = row.display_name || row.asset_key;
        const chunks = row.chunk_count || row.chunk_hashes?.length || 0;
        return (
          `<li class="mesh-pinned-row">` +
          `<span><strong>${name}</strong> <span class="muted small mono">${row.asset_key}</span></span>` +
          `<span class="muted small">${chunks} chunks · sharing ${row.share_enabled !== false ? "on" : "off"}</span>` +
          `<button type="button" class="btn btn-ghost btn-small" data-mesh-unpin="${row.asset_key}">Remove</button>` +
          `</li>`
        );
      })
      .join("");

    listEl.querySelectorAll("[data-mesh-unpin]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const key = btn.getAttribute("data-mesh-unpin");
        if (!key) return;
        btn.disabled = true;
        await unpinMeshAsset(key);
        await render();
      });
    });
  }

  pinUiRefresh = render;
  void render();
  return { refresh: render };
}
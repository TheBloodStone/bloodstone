/**
 * Export / import local mesh chunk backups and download full Time Capsule archives.
 */

import { apiUrl } from "./miner-paths.js";
import {
  chainMeshMeta,
  downloadMeshChunk,
  resolveDeviceId,
  syncChainMesh,
} from "./chain-mesh.js";

const BACKUP_FORMAT = "bloodstone-mesh-backup-v1";

function formatBytes(n) {
  const v = Number(n) || 0;
  if (v >= 1024 * 1024) return `${(v / (1024 * 1024)).toFixed(2)} MiB`;
  if (v >= 1024) return `${(v / 1024).toFixed(1)} KiB`;
  return `${v} B`;
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function bytesToB64(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function b64ToBytes(b64) {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function fetchLocalChunks() {
  const { exportLocalMeshChunks } = await import("./chain-mesh.js");
  return exportLocalMeshChunks();
}

export async function exportLocalMeshBackup() {
  const deviceId = await resolveDeviceId();
  const meta = chainMeshMeta();
  const chunks = await fetchLocalChunks();
  if (!chunks.length) {
    throw new Error("No mesh chunks stored on this device yet — sync Time Capsule first.");
  }

  let manifest = null;
  try {
    const res = await fetch(apiUrl("/api/chain-mesh/manifest"), { cache: "no-store" });
    if (res.ok) {
      const data = await res.json();
      if (data.ok) manifest = data;
    }
  } catch (_) {
    /* optional */
  }

  const payload = {
    format: BACKUP_FORMAT,
    kind: "local_device",
    exported_at: Math.floor(Date.now() / 1000),
    device_id: deviceId,
    meta,
    manifest: manifest
      ? {
          best_block_hash: manifest.best_block_hash,
          block_height: manifest.block_height,
          chunk_count: manifest.chunk_count,
          total_bytes: manifest.total_bytes,
          chunks: (manifest.chunks || []).filter((c) =>
            chunks.some((lc) => lc.chunk_hash === c.chunk_hash),
          ),
        }
      : {
          chunks: chunks.map((c) => ({
            chunk_hash: c.chunk_hash,
            source_file: c.source_file,
            file_offset: c.file_offset,
            size: c.size,
          })),
        },
    chunks: chunks.map((c) => ({
      chunk_hash: c.chunk_hash,
      source_file: c.source_file,
      file_offset: c.file_offset,
      size: c.size,
      data_b64: bytesToB64(c.data),
    })),
  };

  const json = JSON.stringify(payload);
  const blob = new Blob([json], { type: "application/json" });
  const height = manifest?.block_height || meta?.block_height || 0;
  const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  triggerDownload(blob, `bloodstone-mesh-local-${height}-${stamp}.json`);
  return { chunks: chunks.length, bytes: json.length };
}

export async function importLocalMeshBackup(file) {
  const text = await file.text();
  const data = JSON.parse(text);
  if (data.format !== BACKUP_FORMAT) {
    throw new Error(`Unsupported backup format: ${data.format || "unknown"}`);
  }

  const { importLocalMeshChunks } = await import("./chain-mesh.js");
  const chunks = data.chunks || [];
  let restored = 0;
  for (const item of chunks) {
    const h = String(item.chunk_hash || "").trim().toLowerCase();
    const raw = item.data_b64 || item.data;
    if (!h || !raw) continue;
    const bytes = b64ToBytes(raw);
    await importLocalMeshChunks({
      chunk_hash: h,
      source_file: item.source_file || "",
      file_offset: Number(item.file_offset) || 0,
      size: Number(item.size) || bytes.length,
      data: bytes,
    });
    restored += 1;
  }

  if (!restored) throw new Error("Backup file contained no restorable chunks.");

  try {
    const res = await fetch(apiUrl("/api/chain-mesh/backup/import"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: text,
    });
    const upload = await res.json();
    await syncChainMesh();
    return { restored_local: restored, coordinator: upload };
  } catch (_) {
    await syncChainMesh();
    return { restored_local: restored, coordinator: null };
  }
}

export async function importMeshBackupFile(file) {
  if (file.name.endsWith(".zip")) {
    const form = new FormData();
    form.append("backup_file", file);
    const res = await fetch(apiUrl("/api/chain-mesh/backup/import"), {
      method: "POST",
      body: form,
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "import failed");
    await syncChainMesh();
    return data;
  }
  return importLocalMeshBackup(file);
}

export async function downloadCapsuleBackup(statusEl) {
  if (statusEl) statusEl.textContent = "Fetching backup manifest…";
  const manRes = await fetch(apiUrl("/api/chain-mesh/backup/manifest"), { cache: "no-store" });
  const man = manRes.ok ? await manRes.json() : {};
  if (!man.ok) throw new Error(man.error || "no capsule archive published");

  if (statusEl) {
    statusEl.textContent = `Downloading Time Capsule (${man.chunk_count} chunks, ${formatBytes(man.total_bytes)})…`;
  }

  const res = await fetch(apiUrl("/api/chain-mesh/backup/download"), { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `download failed (${res.status})`);
  }
  const blob = await res.blob();
  const disp = res.headers.get("Content-Disposition") || "";
  const match = /filename="?([^";]+)"?/.exec(disp);
  const filename = match?.[1] || `bloodstone-time-capsule-${man.block_height}.zip`;
  triggerDownload(blob, filename);
  if (statusEl) {
    statusEl.textContent = `Saved ${filename} (${formatBytes(blob.size)}) — manifest + ${man.chunk_count} chunk files.`;
  }
  return { filename, bytes: blob.size, chunk_count: man.chunk_count };
}

export function initMeshBackupUi() {
  const exportBtn = document.getElementById("mesh-backup-export-btn");
  const importInput = document.getElementById("mesh-backup-import-file");
  const capsuleBtn = document.getElementById("mesh-backup-capsule-btn");
  const statusEl = document.getElementById("mesh-backup-status");

  exportBtn?.addEventListener("click", () => {
    if (statusEl) statusEl.textContent = "Exporting local mesh chunks…";
    void exportLocalMeshBackup()
      .then((r) => {
        if (statusEl) {
          statusEl.textContent = `Exported ${r.chunks} chunk(s) (${formatBytes(r.bytes)} JSON).`;
        }
      })
      .catch((err) => {
        if (statusEl) statusEl.textContent = err.message || String(err);
      });
  });

  importInput?.addEventListener("change", () => {
    const file = importInput.files?.[0];
    if (!file) return;
    if (statusEl) statusEl.textContent = `Importing ${file.name}…`;
    void importMeshBackupFile(file)
      .then((r) => {
        if (statusEl) {
          const coord = r.coordinator || r;
          statusEl.textContent = `Restored ${r.restored_local || coord.stored_chunks || 0} chunk(s)${
            coord.stored_chunks != null ? ` · coordinator stored ${coord.stored_chunks}` : ""
          }.`;
        }
        importInput.value = "";
      })
      .catch((err) => {
        if (statusEl) statusEl.textContent = err.message || String(err);
        importInput.value = "";
      });
  });

  capsuleBtn?.addEventListener("click", () => {
    void downloadCapsuleBackup(statusEl).catch((err) => {
      if (statusEl) statusEl.textContent = err.message || String(err);
    });
  });
}
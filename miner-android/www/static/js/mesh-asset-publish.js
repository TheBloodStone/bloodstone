/**
 * Browser-side chain mesh asset publishing: chunk file, upload, register manifest.
 */

import { apiUrl } from "./miner-paths.js";
import { resolveDeviceId } from "./chain-mesh.js";
import {
  bytesToB64,
  merkleRootFromChunkHashes,
  sha256HexBytes,
} from "./mesh-asset-reconstruct.js";

const CHUNK_SIZE = 256 * 1024;
// Keep each JSON POST under ~1 MiB on strict proxies (256 KiB chunk ≈ 350 KiB base64).
const UPLOAD_BATCH_MAX = 2;
const MAX_PUBLISH_BYTES = 64 * 1024 * 1024;

function safeBasename(name) {
  const base = String(name || "file")
    .split(/[/\\]/)
    .pop()
    .replace(/[^\w.\-+]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return base || "file";
}

function defaultAssetKey(filename) {
  return `assets/${safeBasename(filename)}`;
}

export async function fileSha256(file) {
  const buf = await file.arrayBuffer();
  return sha256HexBytes(new Uint8Array(buf));
}

async function chunkFileBytes(file) {
  const fileSize = file.size;
  if (fileSize <= 0) throw new Error("empty file");
  if (fileSize > MAX_PUBLISH_BYTES) {
    throw new Error(`file too large (max ${Math.round(MAX_PUBLISH_BYTES / (1024 * 1024))} MiB)`);
  }

  const chunks = [];
  let offset = 0;
  while (offset < fileSize) {
    const slice = file.slice(offset, offset + CHUNK_SIZE);
    const bytes = new Uint8Array(await slice.arrayBuffer());
    const chunkHash = await sha256HexBytes(bytes);
    chunks.push({
      chunk_hash: chunkHash,
      file_offset: offset,
      size: bytes.length,
      data: bytes,
    });
    offset += bytes.length;
  }
  return chunks;
}

/** Chunk a file for mesh upload; returns manifest fields used by transfers and publish flows. */
export async function chunkFile(file, options = {}) {
  const chunks = await chunkFileBytes(file);
  const chunkHashes = chunks.map((c) => c.chunk_hash);
  const merkle_root = await merkleRootFromChunkHashes(chunkHashes);
  const file_sha256 = await fileSha256(file);
  return {
    chunks: chunks.map(({ chunk_hash, file_offset, size, data }) => ({
      chunk_hash,
      hash: chunk_hash,
      file_offset,
      size,
      data,
      data_b64: bytesToB64(data),
    })),
    merkle_root,
    file_sha256,
    file_size: file.size,
    asset_key: (options.assetKey || defaultAssetKey(file?.name || "file")).replace(/^\/+/, ""),
  };
}

async function uploadChunkBatch(records, deviceId, publishToken = "", uploadPath = "/api/chain-mesh/publish-upload") {
  const batch = records.slice(0, UPLOAD_BATCH_MAX).map((r) => ({
    chunk_hash: r.chunk_hash,
    data_b64: bytesToB64(r.data),
  }));
  const headers = { "Content-Type": "application/json" };
  if (publishToken) headers["X-Chain-Mesh-Publish-Token"] = publishToken;
  const res = await fetch(apiUrl(uploadPath), {
    method: "POST",
    headers,
    credentials: "same-origin",
    body: JSON.stringify({
      device_id: deviceId,
      peer_kind: "browser",
      model: navigator.userAgent.slice(0, 120),
      capacity_bytes: records.length * CHUNK_SIZE,
      chunks: batch,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `chunk upload failed (${res.status})`);
  }
  return batch.length;
}

async function uploadAllChunks(chunks, deviceId, onProgress, publishToken = "", uploadPath = "/api/chain-mesh/publish-upload") {
  const pending = [...chunks];
  let uploaded = 0;
  while (pending.length) {
    const n = await uploadChunkBatch(pending, deviceId, publishToken, uploadPath);
    pending.splice(0, n);
    uploaded += n;
    if (onProgress) onProgress(uploaded, chunks.length);
  }
}

async function buildMeshManifestFromFile(file, options = {}) {
  const assetKey = (options.assetKey || defaultAssetKey(file.name)).replace(/^\/+/, "");
  const packed = await chunkFile(file, { assetKey });
  const chunks = packed.chunks;
  const merkleRoot = packed.merkle_root;
  const fileSha256 = packed.file_sha256;
  return {
    assetKey,
    fileSha256,
    chunks,
    manifest: {
      asset_key: assetKey,
      display_name: options.displayName || file.name,
      version: options.version || "",
      mime_type: options.mimeType || file.type || "application/octet-stream",
      file_size: file.size,
      file_sha256: fileSha256,
      merkle_root: merkleRoot,
      anchor: options.anchor !== false,
      chunks: chunks.map(({ chunk_hash, file_offset, size }) => ({
        chunk_hash,
        file_offset,
        size,
      })),
      submitter_address: options.submitterAddress || "",
      device_id: options.deviceId || "",
      note: options.note || "",
    },
  };
}

export async function publishMeshAssetFromFile(file, options = {}) {
  const publishToken = options.publishToken || "";
  const onProgress = options.onProgress;
  const built = await buildMeshManifestFromFile(file, options);
  const manifest = built.manifest;
  const deviceId = await resolveDeviceId();
  if (onProgress) onProgress(0, built.chunks.length, "uploading chunks");
  await uploadAllChunks(
    built.chunks,
    deviceId,
    (done, total) => {
      if (onProgress) onProgress(done, total, "uploading chunks");
    },
    publishToken,
    options.uploadPath || "/api/chain-mesh/publish-upload",
  );

  if (publishToken) manifest.publish_token = publishToken;

  if (onProgress) onProgress(manifest.chunks.length, manifest.chunks.length, "registering asset");
  const headers = { "Content-Type": "application/json" };
  if (publishToken) headers["X-Chain-Mesh-Publish-Token"] = publishToken;

  const res = await fetch(apiUrl("/api/chain-mesh/publish-asset"), {
    method: "POST",
    headers,
    credentials: "same-origin",
    body: JSON.stringify(manifest),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    throw new Error(data.error || `publish failed (${res.status})`);
  }
  return data;
}

export async function submitMeshAssetFromFile(file, options = {}) {
  const onProgress = options.onProgress;
  const built = await buildMeshManifestFromFile(file, options);
  const manifest = built.manifest;
  const deviceId = options.deviceId || (await resolveDeviceId());
  if (onProgress) onProgress(0, built.chunks.length, "uploading chunks");
  await uploadAllChunks(
    built.chunks,
    deviceId,
    (done, total) => {
      if (onProgress) onProgress(done, total, "uploading chunks");
    },
    "",
    "/api/chain-mesh/upload",
  );
  manifest.device_id = deviceId;

  if (onProgress) onProgress(manifest.chunks.length, manifest.chunks.length, "submitting for review");
  const res = await fetch(apiUrl("/api/chain-mesh/submit-asset"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(manifest),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    throw new Error(data.error || `submit failed (${res.status})`);
  }
  return data;
}

export async function fetchWritableMeshKeys({ limit = 200, prefix = "" } = {}) {
  const q = new URLSearchParams({ limit: String(limit) });
  if (prefix) q.set("prefix", prefix);
  const res = await fetch(apiUrl(`/api/chain-mesh/writable-keys?${q}`), { cache: "no-store" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `writable keys failed (${res.status})`);
  }
  return res.json();
}

function formatKeyOptionLabel(row) {
  const name = row.display_name || row.asset_key || "";
  const size = Number(row.file_size) || 0;
  const sizeLabel =
    size >= 1024 * 1024
      ? `${(size / (1024 * 1024)).toFixed(1)} MiB`
      : size >= 1024
        ? `${(size / 1024).toFixed(1)} KiB`
        : `${size} B`;
  const ver = row.version ? ` · v${row.version}` : "";
  return `${name}${ver} · ${sizeLabel}`;
}

/** Populate datalist elements with mesh keys that can be overwritten. */
export async function refreshWritableKeyDatalist(
  datalistId = "mesh-writable-keys-list",
  { limit = 200, prefix = "" } = {},
) {
  const datalist = document.getElementById(datalistId);
  if (!datalist) return [];
  try {
    const data = await fetchWritableMeshKeys({ limit, prefix });
    const keys = data.keys || [];
    datalist.innerHTML = keys
      .map((row) => {
        const key = String(row.asset_key || "").replace(/"/g, "&quot;");
        const label = formatKeyOptionLabel(row).replace(/"/g, "&quot;");
        return `<option value="${key}">${label}</option>`;
      })
      .join("");
    return keys;
  } catch (_) {
    return [];
  }
}

export async function resolveMeshPublishToken(root = document) {
  const form = root.getElementById("mesh-asset-upload-form");
  const preset = form?.dataset?.publishToken || "";
  if (preset) return preset;
  try {
    const res = await fetch(apiUrl("/admin/mesh-publish-token"), {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!res.ok) return "";
    const data = await res.json().catch(() => ({}));
    return String(data.publish_token || "").trim();
  } catch (_) {
    return "";
  }
}

export function initMeshAssetUserSubmit(root = document) {
  const form = root.getElementById("mesh-asset-submit-form");
  if (!form) return;

  const fileInput = root.getElementById("mesh-asset-submit-file");
  const keyInput = root.getElementById("mesh-asset-submit-key");
  const nameInput = root.getElementById("mesh-asset-submit-name");
  const versionInput = root.getElementById("mesh-asset-submit-version");
  const addressInput = root.getElementById("mesh-asset-submit-address");
  const noteInput = root.getElementById("mesh-asset-submit-note");
  const anchorInput = root.getElementById("mesh-asset-submit-anchor");
  const submitBtn = root.getElementById("mesh-asset-submit-btn");
  const statusEl = root.getElementById("mesh-asset-submit-status");
  const progressEl = root.getElementById("mesh-asset-submit-progress");

  const setStatus = (text, kind = "") => {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.className = `muted small mesh-upload-status${kind ? ` ${kind}` : ""}`;
  };

  void refreshWritableKeyDatalist("mesh-writable-keys-list", { prefix: "assets/" });

  fileInput?.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    if (!keyInput?.value) keyInput.value = defaultAssetKey(file.name);
    if (!nameInput?.value) nameInput.value = file.name;
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = fileInput?.files?.[0];
    if (!file) {
      setStatus("Choose a file first.", "error");
      return;
    }

    const chosenKey = keyInput?.value?.trim() || "";
    if (chosenKey) {
      const keys = await fetchWritableMeshKeys({ prefix: "assets/" }).catch(() => ({ keys: [] }));
      const existing = (keys.keys || []).find((k) => k.asset_key === chosenKey);
      if (existing) {
        const ok = window.confirm(
          `Replace existing mesh file at ${chosenKey}?\nCurrent: ${existing.display_name || existing.asset_key} (${existing.version || "no version label"}).`,
        );
        if (!ok) return;
      }
    }

    submitBtn.disabled = true;
    setStatus("Preparing…");
    if (progressEl) progressEl.textContent = "";

    try {
      const result = await submitMeshAssetFromFile(file, {
        assetKey: keyInput?.value?.trim(),
        displayName: nameInput?.value?.trim(),
        version: versionInput?.value?.trim(),
        anchor: anchorInput ? anchorInput.checked : true,
        submitterAddress: addressInput?.value?.trim(),
        note: noteInput?.value?.trim(),
        onProgress: (done, total, phase) => {
          if (progressEl) {
            progressEl.textContent =
              phase === "submitting for review"
                ? "Submitting for admin review…"
                : `Uploading chunks ${done} / ${total}`;
          }
        },
      });
      setStatus(
        `Submitted ${result.asset_key} for admin review (submission #${result.submission_id}).`,
        "ok",
      );
      form.reset();
      if (keyInput) keyInput.value = "";
      if (nameInput) nameInput.value = "";
      if (versionInput) versionInput.value = "";
      if (noteInput) noteInput.value = "";
      if (progressEl) progressEl.textContent = "";
    } catch (err) {
      setStatus(err.message || String(err), "error");
    } finally {
      submitBtn.disabled = false;
    }
  });
}

export function initMeshAssetUpload(root = document) {
  const form = root.getElementById("mesh-asset-upload-form");
  if (!form) return;

  const fileInput = root.getElementById("mesh-asset-file");
  const keyInput = root.getElementById("mesh-asset-key");
  const nameInput = root.getElementById("mesh-asset-name");
  const versionInput = root.getElementById("mesh-asset-version");
  const anchorInput = root.getElementById("mesh-asset-anchor");
  const submitBtn = root.getElementById("mesh-asset-upload-btn");
  const statusEl = root.getElementById("mesh-asset-upload-status");
  const progressEl = root.getElementById("mesh-asset-upload-progress");
  let publishToken = form.dataset.publishToken || "";

  const setStatus = (text, kind = "") => {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.className = `muted small mesh-upload-status${kind ? ` ${kind}` : ""}`;
  };

  fileInput?.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    if (!keyInput?.value) keyInput.value = defaultAssetKey(file.name);
    if (!nameInput?.value) nameInput.value = file.name;
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = fileInput?.files?.[0];
    if (!file) {
      setStatus("Choose a file first.", "error");
      return;
    }

    submitBtn.disabled = true;
    setStatus("Preparing…");
    if (progressEl) progressEl.textContent = "";

    try {
      if (!publishToken) {
        publishToken = await resolveMeshPublishToken(root);
      }
      if (!publishToken) {
        throw new Error("Admin login required to publish files to the blockchain mesh.");
      }
      const result = await publishMeshAssetFromFile(file, {
        assetKey: keyInput?.value?.trim(),
        displayName: nameInput?.value?.trim(),
        version: versionInput?.value?.trim(),
        anchor: anchorInput ? anchorInput.checked : true,
        publishToken,
        onProgress: (done, total, phase) => {
          if (progressEl) {
            progressEl.textContent =
              phase === "registering asset"
                ? "Registering manifest + BSM1 anchor…"
                : `Uploading chunks ${done} / ${total}`;
          }
        },
      });
      const anchorNote = result.anchor?.txid
        ? ` · anchored ${result.anchor.txid.slice(0, 12)}…`
        : result.anchor?.error
          ? ` · anchor pending (${result.anchor.error})`
          : "";
      setStatus(
        `Published ${result.asset_key} (${result.chunk_count} chunks)${anchorNote}`,
        "ok",
      );
      form.reset();
      if (keyInput) keyInput.value = "";
      if (nameInput) nameInput.value = "";
      if (versionInput) versionInput.value = "";
      if (progressEl) progressEl.textContent = "";
    } catch (err) {
      setStatus(err.message || String(err), "error");
    } finally {
      submitBtn.disabled = false;
    }
  });
}
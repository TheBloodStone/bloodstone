/**
 * BSM2 mesh transfer client — send/receive files via chain mesh + mining attestation.
 */

import { apiUrl } from "./miner-paths.js";
import {
  chunkFile,
  fileSha256,
  fetchWritableMeshKeys,
  publishMeshAssetFromFile,
  refreshWritableKeyDatalist,
} from "./mesh-asset-publish.js";

const TRANSFER_PROTOCOL = "bsm2-transfer-v1";

export async function fetchTransferProtocol() {
  const res = await fetch(apiUrl("/api/chain-mesh/transfer/protocol"));
  return res.json();
}

export { fetchWritableMeshKeys, refreshWritableKeyDatalist };

export async function uploadTransferChunks(chunks, deviceId = "") {
  const res = await fetch(apiUrl("/api/chain-mesh/upload"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      device_id: deviceId,
      peer_kind: "transfer-sender",
      chunks: chunks.map((c) => ({
        chunk_hash: c.chunk_hash || c.hash,
        data_b64: c.data_b64,
      })),
    }),
  });
  return res.json();
}

/**
 * Send a file to a recipient STONE address.
 * 1. Chunk + upload to mesh
 * 2. Register BSM2 transfer + optional on-chain anchor
 */
export async function sendMeshTransfer(file, {
  sender,
  recipient,
  displayName = "",
  assetKey = "",
  version = "",
  anchor = true,
  deviceId = "",
  onProgress = null,
} = {}) {
  if (!sender || !recipient) {
    throw new Error("sender and recipient STONE addresses required");
  }
  const name = displayName || file?.name || "payload";
  if (onProgress) onProgress(0, 1, "chunking");
  const { chunks, merkle_root: root, file_sha256: fhash, file_size: fsize } =
    await chunkFile(file, { assetKey: assetKey || `transfers/pending/${name}` });
  if (onProgress) onProgress(0, 1, "uploading chunks");
  const up = await uploadTransferChunks(chunks, deviceId);
  if (!up?.ok) {
    throw new Error(up?.error || "chunk upload failed");
  }
  if (onProgress) onProgress(1, 1, "registering transfer");
  const body = {
    protocol: TRANSFER_PROTOCOL,
    sender,
    recipient,
    display_name: name,
    mime_type: file?.type || "application/octet-stream",
    file_size: fsize,
    file_sha256: fhash,
    merkle_root: root,
    chunks: chunks.map((c) => ({
      chunk_hash: c.chunk_hash || c.hash,
      file_offset: c.file_offset,
      size: c.size,
    })),
    anchor,
  };
  if (assetKey) {
    body.asset_key = assetKey;
    if (version) body.version = version;
  }
  const res = await fetch(apiUrl("/api/chain-mesh/transfer"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!data?.ok) {
    throw new Error(data?.error || "transfer registration failed");
  }
  return data;
}

/**
 * Overwrite an existing mesh asset key (admin publish token) or queue user submission.
 */
export async function sendMeshToKey(file, {
  assetKey,
  displayName = "",
  version = "",
  anchor = true,
  publishToken = "",
  submitForReview = false,
  submitterAddress = "",
  note = "",
  onProgress = null,
} = {}) {
  const key = String(assetKey || "").trim();
  if (!key) throw new Error("asset_key required");

  if (submitForReview || !publishToken) {
    const { submitMeshAssetFromFile } = await import("./mesh-asset-publish.js");
    return submitMeshAssetFromFile(file, {
      assetKey: key,
      displayName: displayName || file?.name,
      version,
      anchor,
      submitterAddress,
      note,
      onProgress,
    });
  }

  return publishMeshAssetFromFile(file, {
    assetKey: key,
    displayName: displayName || file?.name,
    version,
    anchor,
    publishToken,
    onProgress,
  });
}

export async function getMeshTransfer(transferId) {
  const res = await fetch(apiUrl(`/api/chain-mesh/transfer/${transferId}`));
  return res.json();
}

export async function listTransferInbox(recipient, status = "") {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await fetch(apiUrl(`/api/chain-mesh/transfer/inbox/${encodeURIComponent(recipient)}${q}`));
  return res.json();
}

export async function claimMeshTransfer(transferId, recipient) {
  const res = await fetch(apiUrl(`/api/chain-mesh/transfer/${transferId}/claim`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recipient }),
  });
  return res.json();
}

/**
 * Miner attestation — call after a share is accepted to credit hash-power relay.
 */
export async function attestTransferChunk({
  transferId,
  chunkHash,
  deviceId,
  worker = "",
  jobId,
  nonceHex,
  model = "",
} = {}) {
  const res = await fetch(apiUrl("/api/chain-mesh/transfer/attest"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      transfer_id: transferId,
      chunk_hash: chunkHash,
      device_id: deviceId,
      worker,
      job_id: jobId,
      nonce_hex: nonceHex,
      model,
      peer_kind: "android-miner",
    }),
  });
  return res.json();
}

export { fileSha256, TRANSFER_PROTOCOL };
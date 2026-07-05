/**
 * Reconstruct mesh-published assets from chunk manifests (BSM1 / chain mesh).
 */

import { apiUrl } from "./miner-paths.js";
import { downloadMeshChunk } from "./chain-mesh.js";

function hexToBytes(hex) {
  const h = String(hex || "")
    .trim()
    .toLowerCase();
  if (h.length % 2 !== 0) throw new Error("invalid hex length");
  const out = new Uint8Array(h.length / 2);
  for (let i = 0; i < out.length; i += 1) {
    out[i] = parseInt(h.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

async function sha256DigestBytes(bytes) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
}

function bytesToHex(bytes) {
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function merkleRootFromChunkHashes(chunkHashes) {
  if (!chunkHashes?.length) throw new Error("empty chunk list");
  let layer = chunkHashes.map(hexToBytes);
  while (layer.length > 1) {
    if (layer.length % 2 === 1) layer.push(layer[layer.length - 1]);
    const nxt = [];
    for (let i = 0; i < layer.length; i += 2) {
      const left = layer[i];
      const right = layer[i + 1];
      const combined = new Uint8Array(left.length + right.length);
      combined.set(left, 0);
      combined.set(right, left.length);
      nxt.push(await sha256DigestBytes(combined));
    }
    layer = nxt;
  }
  return bytesToHex(layer[0]);
}

export async function sha256HexBytes(bytes) {
  return bytesToHex(await sha256DigestBytes(bytes));
}

export function bytesToB64(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

export async function fetchMeshAssetManifest(assetKey) {
  const key = String(assetKey || "").replace(/^\/+/, "");
  if (!key) throw new Error("asset key required");
  const res = await fetch(apiUrl(`/api/chain-mesh/asset/${encodeURI(key)}`), {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`mesh asset manifest failed (${res.status})`);
  const data = await res.json();
  if (!data?.ok || !data.chunks?.length) {
    throw new Error(data?.error || "mesh asset manifest incomplete");
  }
  return data;
}

async function downloadAssetChunk(chunk, onProgress) {
  const hash = String(chunk.chunk_hash || "").trim().toLowerCase();
  const expectedSize = Number(chunk.size) || 0;
  const bytes = await downloadMeshChunk(hash);
  if (!bytes || bytes.length !== expectedSize) {
    throw new Error(`missing or invalid chunk ${hash}`);
  }
  onProgress?.(bytes.length);
  return { hash, bytes, offset: Number(chunk.file_offset) || 0 };
}

export async function reconstructMeshAsset(assetManifest, options = {}) {
  const chunks = [...(assetManifest.chunks || [])].sort(
    (a, b) => Number(a.file_offset) - Number(b.file_offset),
  );
  if (!chunks.length) throw new Error("asset has no chunks");

  const expectedSize = Number(assetManifest.file_size) || 0;
  const expectedSha = String(
    options.expectedSha256 || assetManifest.file_sha256 || "",
  )
    .trim()
    .toLowerCase();
  const expectedMerkle = String(
    options.expectedMerkle || assetManifest.merkle_root || "",
  )
    .trim()
    .toLowerCase();

  const hashes = chunks.map((c) => String(c.chunk_hash).trim().toLowerCase());
  const merkle = await merkleRootFromChunkHashes(hashes);
  if (expectedMerkle && merkle !== expectedMerkle) {
    throw new Error("mesh merkle root mismatch");
  }

  let downloaded = 0;
  const parts = [];
  const concurrency = Math.min(4, chunks.length);
  for (let i = 0; i < chunks.length; i += concurrency) {
    const batch = chunks.slice(i, i + concurrency);
    const rows = await Promise.all(
      batch.map((chunk) =>
        downloadAssetChunk(chunk, (n) => {
          downloaded += n;
          options.onProgress?.({
            downloaded,
            total: expectedSize,
            chunkHash: chunk.chunk_hash,
          });
        }),
      ),
    );
    parts.push(...rows);
  }

  parts.sort((a, b) => a.offset - b.offset);
  const totalLen = parts.reduce((sum, row) => sum + row.bytes.length, 0);
  const out = new Uint8Array(totalLen);
  let pos = 0;
  for (const row of parts) {
    out.set(row.bytes, pos);
    pos += row.bytes.length;
  }

  if (expectedSize && out.length !== expectedSize) {
    throw new Error("reconstructed size mismatch");
  }
  if (expectedSha) {
    const digest = await sha256HexBytes(out);
    if (digest !== expectedSha) {
      throw new Error("mesh file sha256 mismatch");
    }
  }
  return out;
}

export async function reconstructMeshAssetFromKey(assetKey, options = {}) {
  const manifest = await fetchMeshAssetManifest(assetKey);
  return reconstructMeshAsset(manifest, options);
}
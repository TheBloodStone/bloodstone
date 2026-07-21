/**
 * Bloodstone Mesh File Lookup v1
 * Resolve asset_key / BSM1 anchor → chunk hashes; fetch only those chunks to reconstruct.
 *
 * Usage (browser):
 *   import { lookupMeshFile, fetchMeshFileFromLookup } from "./mesh-file-lookup.js";
 *   const lookup = await lookupMeshFile({ coordinator, assetKey: "downloads/foo.apk" });
 *   const bytes = await fetchMeshFileFromLookup(lookup, { coordinator });
 *
 * Usage (Node 18+):
 *   node mesh-file-lookup.js --key downloads/foo.docx --coordinator https://bloodstonewallet.mytunnel.org
 */

const LOOKUP_PROTOCOL = "mesh-file-lookup-v1";

function apiUrl(coordinator, path) {
  return `${String(coordinator || "").replace(/\/$/, "")}${path}`;
}

function encodeAssetKey(key) {
  return String(key || "")
    .replace(/^\/+/, "")
    .split("/")
    .map((seg) => encodeURIComponent(seg))
    .join("/");
}

export async function lookupMeshFile({
  coordinator,
  assetKey = "",
  txid = "",
  merkleRoot = "",
  byteRange = "",
} = {}) {
  let url;
  if (assetKey) {
    const q = byteRange ? `?range=${encodeURIComponent(byteRange)}` : "";
    url = apiUrl(coordinator, `/api/chain-mesh/asset/${encodeAssetKey(assetKey)}/lookup${q}`);
  } else {
    const params = new URLSearchParams();
    if (txid) params.set("txid", txid);
    if (merkleRoot) params.set("merkle_root", merkleRoot);
    if (byteRange) params.set("range", byteRange);
    url = apiUrl(coordinator, `/api/chain-mesh/lookup?${params}`);
  }
  const res = await fetch(url, { cache: "no-store", headers: { Accept: "application/json" } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    throw new Error(data.error || `lookup failed (${res.status})`);
  }
  if (data.protocol !== LOOKUP_PROTOCOL) {
    throw new Error(`unexpected lookup protocol: ${data.protocol}`);
  }
  return data;
}

function b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
  return out;
}

async function fetchChunkBytes(coordinator, chunkHash) {
  const url = apiUrl(coordinator, `/api/chain-mesh/chunk/${chunkHash}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`chunk ${chunkHash.slice(0, 16)}… failed (${res.status})`);
  const ctype = res.headers.get("content-type") || "";
  if (ctype.includes("json")) {
    const payload = await res.json();
    const b64 = payload.data_b64 || payload.data;
    if (!b64) throw new Error(`chunk ${chunkHash.slice(0, 16)}… missing data_b64`);
    return b64ToBytes(b64);
  }
  return new Uint8Array(await res.arrayBuffer());
}

async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function fetchMeshFileFromLookup(lookup, { coordinator, onProgress } = {}) {
  const chunks = [...(lookup.chunks || [])].sort((a, b) => Number(a.o) - Number(b.o));
  if (!chunks.length) throw new Error("lookup has no chunks");

  let done = 0;
  const parts = [];
  const concurrency = 4;
  for (let i = 0; i < chunks.length; i += concurrency) {
    const batch = chunks.slice(i, i + concurrency);
    const rows = await Promise.all(
      batch.map(async (row) => {
        const bytes = await fetchChunkBytes(coordinator, row.h);
        if (bytes.length !== Number(row.s)) {
          throw new Error(`chunk size mismatch ${row.h.slice(0, 16)}…`);
        }
        done += bytes.length;
        onProgress?.({ downloaded: done, bytesNeeded: lookup.bytes_needed, chunk: row.h });
        return { offset: Number(row.o), bytes };
      }),
    );
    parts.push(...rows);
  }

  let out;
  if (lookup.partial && lookup.byte_range) {
    const start = Number(lookup.byte_range.start);
    const end = Number(lookup.byte_range.end);
    const slices = [];
    for (const { offset, bytes } of parts) {
      const sliceStart = Math.max(0, start - offset);
      const sliceEnd = Math.min(bytes.length, end - offset + 1);
      if (sliceEnd > sliceStart) slices.push(bytes.subarray(sliceStart, sliceEnd));
    }
    const total = slices.reduce((n, u) => n + u.length, 0);
    out = new Uint8Array(total);
    let pos = 0;
    for (const s of slices) {
      out.set(s, pos);
      pos += s.length;
    }
  } else {
    const total = parts.reduce((n, p) => n + p.bytes.length, 0);
    out = new Uint8Array(total);
    let pos = 0;
    for (const { bytes } of parts.sort((a, b) => a.offset - b.offset)) {
      out.set(bytes, pos);
      pos += bytes.length;
    }
    if (lookup.file_size && out.length !== Number(lookup.file_size)) {
      throw new Error("reconstructed size mismatch");
    }
    if (lookup.file_sha256) {
      const digest = await sha256Hex(out);
      if (digest !== String(lookup.file_sha256).toLowerCase()) {
        throw new Error("file sha256 mismatch");
      }
    }
  }
  return out;
}

export async function lookupAndFetchMeshFile(options) {
  const lookup = await lookupMeshFile(options);
  const bytes = await fetchMeshFileFromLookup(lookup, {
    coordinator: options.coordinator,
    onProgress: options.onProgress,
  });
  return { lookup, bytes };
}

// CLI (Node)
async function cliMain() {
  const args = process.argv.slice(2);
  const get = (flag) => {
    const i = args.indexOf(flag);
    return i >= 0 ? args[i + 1] : "";
  };
  const coordinator =
    get("--coordinator") || process.env.BLOODSTONE_COORDINATOR || "https://bloodstonewallet.mytunnel.org";
  const assetKey = get("--key");
  const txid = get("--txid");
  const merkleRoot = get("--merkle-root");
  const byteRange = get("--range");
  const fetchFile = args.includes("--fetch");
  const jsonOnly = args.includes("--json") || !fetchFile;

  const lookup = await lookupMeshFile({ coordinator, assetKey, txid, merkleRoot, byteRange });
  if (jsonOnly) console.log(JSON.stringify(lookup, null, 2));
  if (fetchFile) {
    const bytes = await fetchMeshFileFromLookup(lookup, { coordinator });
    const out = get("-o") || get("--output") || "mesh-download.bin";
    const fs = await import("node:fs");
    fs.writeFileSync(out, bytes);
    console.error(`wrote ${out} (${bytes.length} bytes)`);
  }
}

if (typeof process !== "undefined" && process.argv?.[1]?.includes("mesh-file-lookup")) {
  cliMain().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
  });
}
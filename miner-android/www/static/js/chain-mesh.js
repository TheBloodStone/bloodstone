/**
 * Decentralized blockchain chunk storage on user devices.
 * Browsers use IndexedDB; Android Capacitor uses native filesystem via BloodstoneChainMesh.
 * Devices pin VPS block-fill backups, upload replicas, and act as local VPS chain nodes.
 */

import { apiUrl } from "./miner-paths.js";
import { fleetDeviceId, fleetDeviceModel, loadFleetIdentity } from "./device-fleet.js";

const DB_NAME = "bloodstone-chain-mesh";
const DB_VERSION = 1;
const STORE = "chunks";
const META_KEY = "bloodstone-chain-mesh-meta";
const JOB_CACHE_KEY = "bloodstone-chain-mesh-job-cache";
const PENDING_SHARES_KEY = "bloodstone-chain-mesh-pending-shares";
const PEER_IPS_KEY = "bloodstone-chain-mesh-peer-ips";
const DEFAULT_BACKUP_PCT = 10;
const MAX_LOCAL_CHUNKS_WEB = 32;
const MAX_LOCAL_CHUNKS_ANDROID = 64;
const MAX_LOCAL_CHUNKS_MESH = 128;
const SYNC_INTERVAL_MS = 5 * 60 * 1000;
// Keep each JSON POST under ~1 MiB on strict proxies (256 KiB chunk ≈ 350 KiB base64).
const UPLOAD_BATCH_MAX = 2;
const DEFAULT_CHUNK_PORT = 18341;
const PEER_FETCH_TIMEOUT_MS = 4500;
const PEER_LIST_SYNC_TIMEOUT_MS = 1200;
const LAN_PEER_SCAN_BATCH = 32;
const MAX_SAVED_PEER_IPS = 64;

let dbPromise = null;
let syncTimer = null;
let chainMeshPlugin = null;

function isCapacitorAndroid() {
  try {
    return window.Capacitor?.getPlatform?.() === "android";
  } catch (_) {
    return false;
  }
}

let meshNodeMode = "pruned";

function maxLocalChunks() {
  if (isCapacitorAndroid()) {
    if (meshNodeMode === "mesh" || meshNodeMode === "full") {
      return MAX_LOCAL_CHUNKS_MESH;
    }
    return MAX_LOCAL_CHUNKS_ANDROID;
  }
  return MAX_LOCAL_CHUNKS_WEB;
}

export async function configureMeshForNodeMode(mode = "pruned") {
  meshNodeMode = mode === "mesh" || mode === "full" ? mode : "pruned";
  const plugin = chainMeshNative();
  if (!plugin?.setMeshCapacity) return null;
  try {
    return await plugin.setMeshCapacity({
      mode: meshNodeMode,
      maxChunks: maxLocalChunks(),
    });
  } catch (_) {
    return null;
  }
}

function chainMeshNative() {
  if (chainMeshPlugin !== undefined) return chainMeshPlugin;
  try {
    chainMeshPlugin =
      window.Capacitor?.Plugins?.BloodstoneChainMesh || null;
  } catch (_) {
    chainMeshPlugin = null;
  }
  return chainMeshPlugin;
}

function localDeviceId() {
  try {
    const raw = localStorage.getItem("bloodstone-chain-mesh-device-id");
    if (raw) return raw;
    const id = `web-${crypto.randomUUID().replace(/-/g, "").slice(0, 24)}`;
    localStorage.setItem("bloodstone-chain-mesh-device-id", id);
    return id;
  } catch (_) {
    return `web-${Date.now().toString(36)}`;
  }
}

export async function resolveDeviceId() {
  await loadFleetIdentity();
  return fleetDeviceId() || localDeviceId();
}

function openDb() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "chunk_hash" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

async function idbPut(record) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function idbGetAll() {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
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

async function nativePutChunk(record) {
  const plugin = chainMeshNative();
  if (!plugin) return false;
  await plugin.putChunk({
    chunkHash: record.chunk_hash,
    dataB64: bytesToB64(record.data),
    sourceFile: record.source_file || "",
    fileOffset: record.file_offset || 0,
    size: record.size || record.data?.length || 0,
  });
  return true;
}

async function nativeGetAllChunks() {
  const plugin = chainMeshNative();
  if (!plugin) return [];
  const res = await plugin.listChunks();
  const chunks = res?.chunks || [];
  const out = [];
  for (const meta of chunks) {
    const got = await plugin.getChunk({ chunkHash: meta.chunkHash });
    if (!got?.dataB64) continue;
    out.push({
      chunk_hash: meta.chunkHash,
      source_file: meta.sourceFile || "",
      file_offset: meta.fileOffset || 0,
      size: meta.size || 0,
      data: b64ToBytes(got.dataB64),
      saved_at: meta.savedAt || Date.now(),
    });
  }
  return out;
}

async function storagePut(record) {
  if (chainMeshNative()) {
    return nativePutChunk(record);
  }
  if ("indexedDB" in window) {
    await idbPut(record);
    return true;
  }
  return false;
}

async function storageGetAll() {
  if (chainMeshNative()) {
    return nativeGetAllChunks();
  }
  if ("indexedDB" in window) {
    return idbGetAll();
  }
  return [];
}

async function storageRemove(chunkHash) {
  if (chainMeshNative()) {
    const plugin = chainMeshNative();
    if (plugin?.removeChunk) {
      try {
        await plugin.removeChunk({ chunkHash });
        return true;
      } catch (_) {
        return false;
      }
    }
    return false;
  }
  if ("indexedDB" in window) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(chunkHash);
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => reject(tx.error);
    });
  }
  return false;
}

function assignmentPct(manifest) {
  const pct = Number(manifest?.assignment?.backup_pct);
  if (Number.isFinite(pct) && pct > 0 && pct <= 100) return Math.floor(pct);
  return DEFAULT_BACKUP_PCT;
}

async function sha256Hex(text) {
  const data = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function nodeAssignmentBucket(deviceId, chunkHash) {
  const node = String(deviceId || "").trim().toLowerCase();
  const chunk = String(chunkHash || "").trim().toLowerCase();
  if (!node || !chunk) return 100;
  const digest = await sha256Hex(`${node}:${chunk}`);
  return parseInt(digest.slice(0, 8), 16) % 100;
}

export async function nodeShouldStoreChunk(deviceId, chunkHash, backupPct = DEFAULT_BACKUP_PCT) {
  const pct = Math.max(1, Math.min(100, Number(backupPct) || DEFAULT_BACKUP_PCT));
  const bucket = await nodeAssignmentBucket(deviceId, chunkHash);
  return bucket < pct;
}

async function pickAssignedChunks(manifest, deviceId, heldHashes) {
  const pct = assignmentPct(manifest);
  const all = [...(manifest.chunks || [])];
  const assigned = [];
  for (const chunk of all) {
    if (await nodeShouldStoreChunk(deviceId, chunk.chunk_hash, pct)) {
      assigned.push(chunk);
    }
  }
  assigned.sort((a, b) => {
    const aHave = heldHashes.has(a.chunk_hash) ? 1 : 0;
    const bHave = heldHashes.has(b.chunk_hash) ? 1 : 0;
    return aHave - bHave;
  });
  const cap = Math.max(1, Math.ceil((all.length * pct) / 100) + 2);
  const limit = Math.min(maxLocalChunks(), cap);
  return {
    targets: assigned.slice(0, limit),
    assignedCount: assigned.length,
    backupPct: pct,
    assignedHashes: new Set(assigned.map((c) => c.chunk_hash)),
  };
}

async function fetchManifest() {
  try {
    const res = await fetch(apiUrl("/api/chain-mesh/manifest"));
    if (!res.ok) return null;
    const data = await res.json();
    return data.ok ? data : null;
  } catch (_) {
    return null;
  }
}

function normalizeEndpoint(endpoint = {}) {
  const ip = String(endpoint.ip || endpoint.lan_ip || endpoint.lanIp || "").trim();
  const port = Number(
    endpoint.port || endpoint.chunk_port || endpoint.chunkPort || DEFAULT_CHUNK_PORT,
  );
  const deviceId = String(endpoint.device_id || endpoint.deviceId || "").trim();
  if (!ip || !Number.isFinite(port) || port <= 0) return null;
  return { ip, port, deviceId };
}

function loadSavedPeerIps() {
  try {
    const raw = localStorage.getItem(PEER_IPS_KEY);
    const parsed = raw ? JSON.parse(raw) : { peers: [] };
    const peers = Array.isArray(parsed?.peers) ? parsed.peers : [];
    return peers
      .map(normalizeEndpoint)
      .filter(Boolean)
      .sort((a, b) => (b.lastSuccess || b.lastSeen || 0) - (a.lastSuccess || a.lastSeen || 0));
  } catch (_) {
    return [];
  }
}

function savePeerIps(peers) {
  const normalized = [];
  const seen = new Set();
  for (const peer of peers) {
    const row = normalizeEndpoint(peer);
    if (!row) continue;
    const key = `${row.ip}:${row.port}`;
    if (seen.has(key)) continue;
    seen.add(key);
    normalized.push({
      ip: row.ip,
      port: row.port,
      device_id: row.deviceId || peer.device_id || "",
      last_seen: peer.last_seen || peer.lastSeen || Date.now(),
      last_success: peer.last_success || peer.lastSuccess || 0,
      failures: peer.failures || 0,
    });
  }
  normalized.sort(
    (a, b) => (b.last_success || b.last_seen || 0) - (a.last_success || a.last_seen || 0),
  );
  const trimmed = normalized.slice(0, MAX_SAVED_PEER_IPS);
  try {
    localStorage.setItem(PEER_IPS_KEY, JSON.stringify({ peers: trimmed }));
  } catch (_) {
    /* quota */
  }
  return trimmed;
}

async function nativeListPeerIps() {
  const plugin = chainMeshNative();
  if (!plugin?.listPeerIps) return null;
  try {
    const res = await plugin.listPeerIps();
    return res?.peers || [];
  } catch (_) {
    return null;
  }
}

async function nativeMergePeerIps(peers) {
  if (!peers?.length) return 0;
  const plugin = chainMeshNative();
  if (plugin?.mergePeerIps) {
    try {
      const res = await plugin.mergePeerIps({ peers });
      return Number(res?.merged || peers.length);
    } catch (_) {
      /* fall through */
    }
  }
  for (const peer of peers) {
    await nativeSavePeerIp(peer);
  }
  return peers.length;
}

async function nativeSavePeerIp(endpoint) {
  const row = normalizeEndpoint(endpoint);
  if (!row) return;
  const plugin = chainMeshNative();
  if (plugin?.savePeerIp) {
    try {
      await plugin.savePeerIp({
        ip: row.ip,
        port: row.port,
        deviceId: row.deviceId,
      });
      return;
    } catch (_) {
      /* fall through to web storage */
    }
  }
  const existing = loadSavedPeerIps();
  savePeerIps([
    ...existing,
    {
      ip: row.ip,
      port: row.port,
      device_id: row.deviceId,
      last_seen: Date.now(),
    },
  ]);
}

async function nativeRecordPeerResult(endpoint, success) {
  const row = normalizeEndpoint(endpoint);
  if (!row) return;
  const plugin = chainMeshNative();
  if (plugin?.recordPeerResult) {
    try {
      await plugin.recordPeerResult({
        ip: row.ip,
        port: row.port,
        success,
      });
      return;
    } catch (_) {
      /* fall through */
    }
  }
  const peers = loadSavedPeerIps();
  const now = Date.now();
  const updated = peers.map((peer) => {
    if (peer.ip !== row.ip || peer.port !== row.port) return peer;
    return {
      ...peer,
      last_seen: now,
      last_success: success ? now : peer.last_success || 0,
      failures: success ? 0 : (peer.failures || 0) + 1,
    };
  });
  savePeerIps(updated.filter((peer) => (peer.failures || 0) < 5));
}

function mapNativePeer(peer) {
  return {
    ip: peer.ip,
    port: peer.port,
    device_id: peer.deviceId || peer.device_id || "",
    last_seen: peer.lastSeen || peer.last_seen || 0,
    last_success: peer.lastSuccess || peer.last_success || 0,
    failures: peer.failures || 0,
  };
}

function mergePeerEndpointLists(...lists) {
  const merged = [];
  const seen = new Set();
  for (const list of lists) {
    for (const peer of list) {
      const row = normalizeEndpoint(peer);
      if (!row) continue;
      const key = `${row.ip}:${row.port}`;
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push({ ...row, ...peer, ip: row.ip, port: row.port });
    }
  }
  return merged.sort(
    (a, b) => (b.last_success || b.last_seen || 0) - (a.last_success || a.last_seen || 0),
  );
}

async function loadKnownPeerEndpoints() {
  const nativePeers = (await nativeListPeerIps()) || [];
  const webPeers = loadSavedPeerIps();
  return mergePeerEndpointLists(
    nativePeers.map(mapNativePeer),
    webPeers,
  );
}

function lanSubnetHosts(localIp) {
  const parts = String(localIp || "").split(".");
  if (parts.length !== 4) return [];
  const prefix = `${parts[0]}.${parts[1]}.${parts[2]}.`;
  const self = parts[3];
  const hosts = [];
  for (let host = 1; host <= 254; host += 1) {
    if (String(host) === self) continue;
    hosts.push(`${prefix}${host}`);
  }
  return hosts;
}

async function fetchPeerListFromEndpoint(endpoint, timeoutMs = PEER_LIST_SYNC_TIMEOUT_MS) {
  const row = normalizeEndpoint(endpoint);
  if (!row) return { peers: [], responded: false };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const url = `http://${row.ip}:${row.port}/peers`;
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) return { peers: [], responded: false };
    const data = await res.json();
    const peers = Array.isArray(data?.peers) ? data.peers : [];
    return { peers, responded: true, source: row };
  } catch (_) {
    return { peers: [], responded: false };
  } finally {
    clearTimeout(timer);
  }
}

async function scanLanPeerLists(localEndpoint) {
  if (!isCapacitorAndroid() || !localEndpoint?.ip) return [];
  const hosts = lanSubnetHosts(localEndpoint.ip);
  const collected = [];
  for (let i = 0; i < hosts.length; i += LAN_PEER_SCAN_BATCH) {
    const batch = hosts.slice(i, i + LAN_PEER_SCAN_BATCH);
    const results = await Promise.all(
      batch.map((ip) =>
        fetchPeerListFromEndpoint({ ip, port: localEndpoint.port || DEFAULT_CHUNK_PORT }),
      ),
    );
    for (const result of results) {
      if (result.responded && result.source) {
        collected.push(result.source);
      }
      for (const peer of result.peers) {
        collected.push(peer);
      }
    }
  }
  return collected;
}

async function syncPeerIpsOnLoad() {
  if (!isCapacitorAndroid()) return [];
  const localEndpoint = await localChunkEndpoint();
  const known = await loadKnownPeerEndpoints();
  const candidates = mergePeerEndpointLists(known);
  const gathered = [...candidates];

  const probeResults = await Promise.all(
    candidates.map((endpoint) => fetchPeerListFromEndpoint(endpoint)),
  );
  for (let i = 0; i < probeResults.length; i += 1) {
    const result = probeResults[i];
    if (result.responded) {
      gathered.push(candidates[i]);
    }
    for (const peer of result.peers) {
      gathered.push(peer);
    }
  }

  const lanPeers = await scanLanPeerLists(localEndpoint);
  gathered.push(...lanPeers);

  if (localEndpoint?.ip) {
    gathered.push({
      ip: localEndpoint.ip,
      port: localEndpoint.port || DEFAULT_CHUNK_PORT,
      last_seen: Date.now(),
    });
  }

  const merged = mergePeerEndpointLists(gathered);
  await nativeMergePeerIps(merged);
  savePeerIps(merged);
  return merged;
}

async function discoverPeerEndpoints(hash) {
  const discovered = [];
  try {
    const res = await fetch(apiUrl(`/api/chain-mesh/peers-for/${encodeURIComponent(hash)}`));
    if (res.ok) {
      const data = await res.json();
      for (const endpoint of data.endpoints || []) {
        const row = normalizeEndpoint(endpoint);
        if (row) discovered.push(row);
      }
    }
  } catch (_) {
    /* offline */
  }
  try {
    const res = await fetch(apiUrl("/api/local-node/nearby"));
    if (res.ok) {
      const data = await res.json();
      for (const node of data.nodes || []) {
        const row = normalizeEndpoint({
          ip: node.lan_ip,
          port: node.chunk_port || DEFAULT_CHUNK_PORT,
          device_id: node.device_id,
        });
        if (row) discovered.push(row);
      }
    }
  } catch (_) {
    /* offline */
  }
  for (const endpoint of discovered) {
    await nativeSavePeerIp(endpoint);
  }
  return discovered;
}

async function localChunkEndpoint() {
  const plugin = chainMeshNative();
  if (!plugin) return null;
  try {
    const status = await plugin.getChunkServerStatus?.();
    if (status?.lanIp) {
      return {
        ip: status.lanIp,
        port: Number(status.port || DEFAULT_CHUNK_PORT),
      };
    }
  } catch (_) {
    /* ignore */
  }
  try {
    const localNode = window.Capacitor?.Plugins?.BloodstoneLocalNode;
    const nodeStatus = await localNode?.getLocalNodeStatus?.();
    if (nodeStatus?.lanIp) {
      return {
        ip: nodeStatus.lanIp,
        port: DEFAULT_CHUNK_PORT,
      };
    }
  } catch (_) {
    /* ignore */
  }
  return null;
}

async function downloadChunkFromPeer(hash, endpoint) {
  const row = normalizeEndpoint(endpoint);
  if (!row) return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PEER_FETCH_TIMEOUT_MS);
  try {
    const url = `http://${row.ip}:${row.port}/chunk/${encodeURIComponent(hash)}`;
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) {
      await nativeRecordPeerResult(row, false);
      return null;
    }
    const data = await res.json();
    if (!data?.data_b64) {
      await nativeRecordPeerResult(row, false);
      return null;
    }
    await nativeRecordPeerResult(row, true);
    return b64ToBytes(data.data_b64);
  } catch (_) {
    await nativeRecordPeerResult(row, false);
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function downloadChunkFromVps(hash) {
  try {
    const res = await fetch(apiUrl(`/api/chain-mesh/chunk/${hash}`));
    if (res.ok) {
      const data = await res.json();
      if (data.data_b64) return b64ToBytes(data.data_b64);
    }
  } catch (_) {
    /* VPS unreachable */
  }
  return null;
}

async function downloadChunk(hash) {
  const savedPeers = await loadKnownPeerEndpoints();
  const discoveredPeers = await discoverPeerEndpoints(hash);
  const candidates = [];
  const seen = new Set();
  for (const peer of [...savedPeers, ...discoveredPeers]) {
    const row = normalizeEndpoint(peer);
    if (!row) continue;
    const key = `${row.ip}:${row.port}`;
    if (seen.has(key)) continue;
    seen.add(key);
    candidates.push(row);
  }

  for (const peer of candidates) {
    const bytes = await downloadChunkFromPeer(hash, peer);
    if (bytes) return bytes;
  }

  return downloadChunkFromVps(hash);
}

async function uploadChunksToCoordinator(records) {
  if (!records.length) return { uploaded: 0 };
  const deviceId = await resolveDeviceId();
  const batch = records.slice(0, UPLOAD_BATCH_MAX).map((r) => ({
    chunk_hash: r.chunk_hash,
    data_b64: bytesToB64(r.data),
  }));
  try {
    const res = await fetch(apiUrl("/api/chain-mesh/upload"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_id: deviceId,
        peer_kind: isCapacitorAndroid() ? "android" : "browser",
        model: fleetDeviceModel(),
        capacity_bytes: records.length * 256 * 1024,
        chunks: batch,
      }),
    });
    if (!res.ok) return { uploaded: 0 };
    const data = await res.json();
    return { uploaded: batch.length, result: data };
  } catch (_) {
    return { uploaded: 0 };
  }
}

async function announcePeer(deviceId, chunkHashes, manifest) {
  const chunkEndpoint = await localChunkEndpoint();
  try {
    await fetch(apiUrl("/api/chain-mesh/peer"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_id: deviceId,
        peer_kind: isCapacitorAndroid() ? "android" : "browser",
        model: fleetDeviceModel(),
        chunk_hashes: chunkHashes,
        capacity_bytes: chunkHashes.length * 256 * 1024,
        lan_ip: chunkEndpoint?.ip || "",
        chunk_port: chunkEndpoint?.port || DEFAULT_CHUNK_PORT,
      }),
    });
    await fetch(apiUrl("/api/chain-mesh/local-node"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_id: deviceId,
        peer_kind: isCapacitorAndroid() ? "android" : "browser",
        model: fleetDeviceModel(),
        block_height: manifest?.block_height || 0,
        best_block_hash: manifest?.best_block_hash || "",
        chunks_held: chunkHashes.length,
        offline_capable: Boolean(loadJobCacheLocal()),
      }),
    });
  } catch (_) {
    /* offline — local node still works */
  }
}

function loadJobCacheLocal() {
  try {
    const raw = localStorage.getItem(JOB_CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;
  }
}

export function saveJobCacheLocal(session) {
  const record = {
    ...session,
    saved_at: Date.now(),
  };
  try {
    localStorage.setItem(JOB_CACHE_KEY, JSON.stringify(record));
  } catch (_) {
    /* quota */
  }
  void pushJobCacheToCoordinator(record);
  return record;
}

async function pushJobCacheToCoordinator(record) {
  const deviceId = await resolveDeviceId();
  try {
    await fetch(apiUrl("/api/chain-mesh/job-cache"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_id: deviceId,
        peer_kind: isCapacitorAndroid() ? "android" : "browser",
        model: fleetDeviceModel(),
        ...record,
        job_cached: true,
        offline_capable: true,
      }),
    });
  } catch (_) {
    /* keep local copy */
  }
}

export function getCachedMiningSession() {
  const local = loadJobCacheLocal();
  if (!local?.job || !local?.targetHex) return null;
  const ageMs = Date.now() - (local.saved_at || 0);
  if (ageMs > 6 * 3600 * 1000) return null;
  return local;
}

export function queuePendingShare(share) {
  let shares = [];
  try {
    const raw = localStorage.getItem(PENDING_SHARES_KEY);
    shares = raw ? JSON.parse(raw) : [];
  } catch (_) {
    shares = [];
  }
  shares.push({ ...share, queued_at: Date.now() });
  if (shares.length > 200) shares = shares.slice(-200);
  try {
    localStorage.setItem(PENDING_SHARES_KEY, JSON.stringify(shares));
  } catch (_) {
    /* ignore */
  }
  void flushPendingSharesToCoordinator(shares);
  return shares.length;
}

async function flushPendingSharesToCoordinator(shares) {
  const deviceId = await resolveDeviceId();
  try {
    await fetch(apiUrl("/api/chain-mesh/pending-shares"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId, shares }),
    });
  } catch (_) {
    /* drain on reconnect */
  }
}

export async function drainPendingShares() {
  const deviceId = await resolveDeviceId();
  let local = [];
  try {
    const raw = localStorage.getItem(PENDING_SHARES_KEY);
    local = raw ? JSON.parse(raw) : [];
  } catch (_) {
    local = [];
  }
  try {
    const res = await fetch(
      apiUrl(`/api/chain-mesh/pending-shares?device_id=${encodeURIComponent(deviceId)}`),
    );
    if (res.ok) {
      const data = await res.json();
      const remote = data.shares || [];
      if (remote.length) {
        local = [...remote, ...local];
      }
    }
  } catch (_) {
    /* use local only */
  }
  try {
    localStorage.removeItem(PENDING_SHARES_KEY);
  } catch (_) {
    /* ignore */
  }
  return local;
}

export function canMineOffline() {
  const session = getCachedMiningSession();
  const meta = chainMeshMeta();
  return Boolean(session && (meta?.chunks_held > 0 || meta?.block_height > 0));
}

export async function syncChainMesh() {
  const canStore = chainMeshNative() || "indexedDB" in window;
  if (!canStore) return null;

  const manifest = await fetchManifest();
  const deviceId = await resolveDeviceId();
  const existing = await storageGetAll();
  const held = new Map(existing.map((r) => [r.chunk_hash, r]));

  let assignment = {
    targets: [],
    assignedCount: 0,
    backupPct: DEFAULT_BACKUP_PCT,
    assignedHashes: new Set(),
  };

  if (manifest) {
    assignment = await pickAssignedChunks(manifest, deviceId, new Set(held.keys()));

    for (const hash of [...held.keys()]) {
      if (!assignment.assignedHashes.has(hash)) {
        await storageRemove(hash);
        held.delete(hash);
      }
    }

    for (const chunk of assignment.targets) {
      if (held.has(chunk.chunk_hash)) continue;
      const bytes = await downloadChunk(chunk.chunk_hash);
      if (!bytes) continue;
      const record = {
        chunk_hash: chunk.chunk_hash,
        source_file: chunk.source_file,
        file_offset: chunk.file_offset,
        size: chunk.size,
        data: bytes,
        saved_at: Date.now(),
      };
      await storagePut(record);
      held.set(chunk.chunk_hash, record);
    }
    await uploadChunksToCoordinator([...held.values()]);
  }

  const hashes = [...held.keys()];
  if (hashes.length && manifest) {
    await announcePeer(deviceId, hashes, manifest);
  }

  const meta = {
    device_id: deviceId,
    chunks_held: hashes.length,
    assigned_count: assignment.assignedCount,
    assignment_pct: assignment.backupPct,
    assignment_algo: manifest?.assignment?.algo || "node_id_hash_v1",
    block_height: manifest?.block_height || chainMeshMeta()?.block_height || 0,
    best_block_hash: manifest?.best_block_hash || "",
    synced_at: Date.now(),
    role:
      meshNodeMode === "full"
        ? "full-vps-node"
        : meshNodeMode === "mesh"
          ? "mesh-federation-node"
          : "local-vps-node",
    offline_capable: canMineOffline(),
    storage: chainMeshNative() ? "capacitor" : "indexeddb",
  };
  try {
    localStorage.setItem(META_KEY, JSON.stringify(meta));
  } catch (_) {
    /* ignore quota */
  }
  return meta;
}

export function chainMeshMeta() {
  try {
    const raw = localStorage.getItem(META_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;
  }
}

async function ensureChunkServer() {
  const plugin = chainMeshNative();
  if (!plugin?.startChunkServer) return null;
  try {
    const status = await plugin.getChunkServerStatus?.();
    if (status?.running) return status;
    return await plugin.startChunkServer({ port: DEFAULT_CHUNK_PORT });
  } catch (_) {
    return null;
  }
}

export function startChainMeshPeer(options = {}) {
  const canStore = chainMeshNative() || "indexedDB" in window;
  if (!canStore) return;
  const run = async () => {
    if (options.nodeMode) {
      await configureMeshForNodeMode(options.nodeMode);
    }
    await ensureChunkServer();
    try {
      await syncPeerIpsOnLoad();
    } catch (_) {
      /* keep mining even if peer sync fails */
    }
    await syncChainMesh();
  };
  void run();
  if (syncTimer) clearInterval(syncTimer);
  syncTimer = setInterval(() => {
    void run();
  }, SYNC_INTERVAL_MS);
}

export async function refreshChainMeshStats() {
  try {
    const res = await fetch(apiUrl("/api/chain-mesh/status"));
    if (!res.ok) return null;
    return await res.json();
  } catch (_) {
    return null;
  }
}

/** Download a single mesh chunk from LAN peers, then coordinator VPS. */
export async function downloadMeshChunk(hash) {
  return downloadChunk(hash);
}

/** All chunk records held locally (for backup export). */
export async function exportLocalMeshChunks() {
  const rows = await storageGetAll();
  return rows.filter((r) => r?.chunk_hash && r?.data?.length);
}

/** Restore one chunk from a backup file into local storage. */
export async function importLocalMeshChunks(record) {
  if (!record?.chunk_hash || !record?.data?.length) {
    throw new Error("invalid chunk record");
  }
  await storagePut({
    chunk_hash: record.chunk_hash,
    source_file: record.source_file || "",
    file_offset: Number(record.file_offset) || 0,
    size: Number(record.size) || record.data.length,
    data: record.data,
    saved_at: Date.now(),
  });
  return true;
}
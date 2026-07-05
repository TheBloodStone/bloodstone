/**
 * Local BSM3 packet cache (IndexedDB) for LAN relay from miners/browsers.
 */

const DB_NAME = "bloodstone-mesh-packets";
const DB_VERSION = 1;
const STORE = "packets";

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const os = db.createObjectStore(STORE, { keyPath: "packet_id" });
        os.createIndex("recipient", "recipient", { unique: false });
        os.createIndex("channel_seq", ["channel_id", "seq"], { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function cacheMeshPacket(packet) {
  if (!packet?.packet_id) return false;
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put({ ...packet, cached_at: Date.now() });
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => reject(tx.error);
  });
}

export async function listCachedPackets(recipient, { sinceSeq = 0 } = {}) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => {
      const rows = (req.result || []).filter((p) => {
        if (recipient && p.recipient !== recipient) return false;
        if (sinceSeq > 0 && Number(p.seq) <= sinceSeq) return false;
        return true;
      });
      rows.sort((a, b) => Number(a.seq) - Number(b.seq));
      resolve(rows);
    };
    req.onerror = () => reject(req.error);
  });
}

export async function pushPacketToLanServer(packet, endpoint) {
  const row = endpoint || {};
  const ip = row.ip || row.lan_ip;
  const port = row.port || row.chunk_port || 18341;
  if (!ip || !packet?.packet_id) return false;
  try {
    const res = await fetch(`http://${ip}:${port}/packet`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ packet }),
    });
    return res.ok;
  } catch (_) {
    return false;
  }
}
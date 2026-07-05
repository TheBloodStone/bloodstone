/**
 * BSM3 LAN P2P — fetch packet inbox from household peers on :18341 before VPS.
 */

import { apiUrl } from "./miner-paths.js";
import { listCachedPackets } from "./mesh-packet-store.js";

const DEFAULT_CHUNK_PORT = 18341;
const PEER_TIMEOUT_MS = 3500;

function normalizeEndpoint(endpoint) {
  const ip = String(endpoint?.ip || endpoint?.lan_ip || "").trim();
  if (!ip) return null;
  const port = Number(endpoint?.port || endpoint?.chunk_port || DEFAULT_CHUNK_PORT);
  return { ip, port };
}

async function fetchLanPacketInbox(recipient, endpoint, sinceSeq = 0) {
  const row = normalizeEndpoint(endpoint);
  if (!row) return [];
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PEER_TIMEOUT_MS);
  try {
    const q = sinceSeq > 0 ? `?since_seq=${sinceSeq}` : "";
    const url = `http://${row.ip}:${row.port}/packet/inbox/${encodeURIComponent(recipient)}${q}`;
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) return [];
    const data = await res.json();
    return data.packets || [];
  } catch (_) {
    return [];
  } finally {
    clearTimeout(timer);
  }
}

export async function discoverPacketPeerEndpoints() {
  const endpoints = [];
  try {
    const res = await fetch(apiUrl("/api/local-node/nearby"));
    if (res.ok) {
      const data = await res.json();
      for (const node of data.nodes || []) {
        const row = normalizeEndpoint({
          ip: node.lan_ip,
          port: node.chunk_port,
          device_id: node.device_id,
        });
        if (row) endpoints.push(row);
      }
    }
  } catch (_) {
    /* offline */
  }
  return endpoints;
}

/**
 * Merge LAN peer inbox, local IndexedDB cache, and coordinator poll.
 */
export async function fetchMeshPacketInboxHybrid(recipient, {
  channelId = "",
  sinceSeq = 0,
  limit = 50,
  coordinatorFetch,
} = {}) {
  const seen = new Set();
  const merged = [];

  const push = (pkt) => {
    const id = pkt?.packet_id;
    if (!id || seen.has(id)) return;
    if (channelId && pkt.channel_id !== channelId) return;
    seen.add(id);
    merged.push(pkt);
  };

  const local = await listCachedPackets(recipient, { sinceSeq }).catch(() => []);
  local.forEach(push);

  const peers = await discoverPacketPeerEndpoints();
  for (const peer of peers) {
    const rows = await fetchLanPacketInbox(recipient, peer, sinceSeq);
    rows.forEach(push);
  }

  if (typeof coordinatorFetch === "function") {
    const remote = await coordinatorFetch();
    for (const pkt of remote?.packets || []) push(pkt);
  }

  merged.sort((a, b) => Number(a.seq) - Number(b.seq));
  return {
    ok: true,
    recipient,
    packets: merged.slice(0, limit),
    count: merged.length,
    sources: { local: local.length, peers: peers.length },
  };
}
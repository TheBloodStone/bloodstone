/**
 * Wire BSM3 packet relay attestation into the mining loop (after share accept).
 */

import { apiUrl } from "./miner-paths.js";
import { resolveDeviceId } from "./chain-mesh.js";
import { attestMeshPacketRelay, pollMeshPacketInbox } from "./mesh-packet.js";
import {
  cacheMeshPacket,
  pushPacketToLanServer,
} from "./mesh-packet-store.js";
import { discoverPacketPeerEndpoints } from "./mesh-packet-lan.js";

let relayEnabled = true;
let lastRelayAt = 0;
const RELAY_COOLDOWN_MS = 2500;

export function setMeshPacketRelayEnabled(on) {
  relayEnabled = !!on;
}

export async function relayMeshPacketOnShare(share, { worker = "", model = "" } = {}) {
  if (!relayEnabled || !share?.jobId) return null;
  const now = Date.now();
  if (now - lastRelayAt < RELAY_COOLDOWN_MS) return null;
  lastRelayAt = now;

  const deviceId = await resolveDeviceId();
  const q = new URLSearchParams({ device_id: deviceId, limit: "4" });
  const res = await fetch(apiUrl(`/api/chain-mesh/packet/relay-queue?${q}`), {
    cache: "no-store",
  });
  if (!res.ok) return null;
  const data = await res.json().catch(() => ({}));
  const item = (data.queue || [])[0];
  if (!item?.packet_id || !item?.channel_id) return null;

  const nonceHex = String(share.nonce || share.nonceHex || "").trim();
  if (!nonceHex) return null;

  const result = await attestMeshPacketRelay({
    channelId: item.channel_id,
    packetId: item.packet_id,
    deviceId,
    worker,
    jobId: share.jobId,
    nonceHex,
    model,
  });

  void (async () => {
    try {
      const inbox = await pollMeshPacketInbox(item.recipient || "", {
        channelId: item.channel_id,
        sinceSeq: Math.max(0, (item.seq || 1) - 1),
        limit: 4,
      });
      const pkt = (inbox.packets || []).find((p) => p.packet_id === item.packet_id);
      if (!pkt) return;
      await cacheMeshPacket(pkt);
      const peers = await discoverPacketPeerEndpoints();
      for (const peer of peers.slice(0, 3)) {
        await pushPacketToLanServer(pkt, peer);
      }
    } catch (_) {
      /* best-effort LAN mirror */
    }
  })();

  return result;
}
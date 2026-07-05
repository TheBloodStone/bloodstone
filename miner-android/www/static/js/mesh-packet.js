/**
 * BSM3 mesh packet client — virtual LAN datagrams over mining-attested relay.
 */

import { apiUrl } from "./miner-paths.js";

const PACKET_PROTOCOL = "bsm3-packet-v1";

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
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
  return out;
}

export async function fetchPacketProtocol() {
  const res = await fetch(apiUrl("/api/chain-mesh/packet/protocol"));
  return res.json();
}

export async function openMeshPacketChannel({
  sender,
  recipient,
  label = "",
  anchor = false,
} = {}) {
  const res = await fetch(apiUrl("/api/chain-mesh/packet/channel"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sender, recipient, label, anchor }),
  });
  const data = await res.json();
  if (!data?.ok) throw new Error(data?.error || "channel open failed");
  return data;
}

export async function sendMeshPacket({
  channelId,
  sender = "",
  recipient = "",
  payload,
  payloadType = "text",
  seq = null,
} = {}) {
  let bytes;
  let ptype = payloadType;
  if (typeof payload === "string") {
    bytes = new TextEncoder().encode(payload);
    if (!ptype) ptype = "text";
  } else if (payload instanceof Uint8Array) {
    bytes = payload;
    if (!ptype) ptype = "raw";
  } else if (payload && typeof payload === "object") {
    bytes = new TextEncoder().encode(JSON.stringify(payload));
    ptype = "json";
  } else {
    throw new Error("payload required");
  }

  const res = await fetch(apiUrl("/api/chain-mesh/packet/send"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      protocol: PACKET_PROTOCOL,
      channel_id: channelId,
      sender,
      recipient,
      payload_type: ptype,
      payload_b64: bytesToB64(bytes),
      seq: seq ?? undefined,
    }),
  });
  const data = await res.json();
  if (!data?.ok) throw new Error(data?.error || "packet send failed");
  return data;
}

export async function pollMeshPacketInbox(recipient, {
  channelId = "",
  sinceSeq = 0,
  limit = 50,
} = {}) {
  const q = new URLSearchParams({ limit: String(limit) });
  if (channelId) q.set("channel_id", channelId);
  if (sinceSeq > 0) q.set("since_seq", String(sinceSeq));
  const res = await fetch(
    apiUrl(`/api/chain-mesh/packet/inbox/${encodeURIComponent(recipient)}?${q}`),
    { cache: "no-store" },
  );
  return res.json();
}

/** SSE stream — calls onPacket for each incoming BSM3 packet. Returns close(). */
export function streamMeshPacketInbox(recipient, { onPacket, onError, timeoutSec = 300 } = {}) {
  const q = new URLSearchParams({ timeout: String(timeoutSec) });
  const source = new EventSource(
    apiUrl(`/api/chain-mesh/packet/stream/${encodeURIComponent(recipient)}?${q}`),
  );
  source.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data?.type === "packet" && data.packet && onPacket) {
        onPacket(data.packet);
      }
    } catch (err) {
      if (onError) onError(err);
    }
  };
  source.onerror = (err) => {
    if (onError) onError(err);
  };
  return () => source.close();
}

export async function getMeshPacketChannel(channelId) {
  const res = await fetch(apiUrl(`/api/chain-mesh/packet/channel/${channelId}`));
  return res.json();
}

export async function attestMeshPacketRelay({
  channelId,
  packetId,
  deviceId,
  worker = "",
  jobId,
  nonceHex,
  model = "",
} = {}) {
  const res = await fetch(apiUrl("/api/chain-mesh/packet/attest"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      channel_id: channelId,
      packet_id: packetId,
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

export function decodePacketPayload(packet) {
  if (!packet) return "";
  if (packet.payload_text != null) return packet.payload_text;
  if (packet.payload_b64) {
    try {
      return new TextDecoder().decode(b64ToBytes(packet.payload_b64));
    } catch (_) {
      return packet.payload_hex || "";
    }
  }
  return packet.payload_hex || "";
}

export { PACKET_PROTOCOL, bytesToB64, b64ToBytes };
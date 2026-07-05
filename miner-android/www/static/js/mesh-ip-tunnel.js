/**
 * BSM4 — raw IPv4 encapsulation over BSM3 mesh packets (browser userspace tunnel).
 */

import { apiUrl } from "./miner-paths.js";
import { bytesToB64 } from "./mesh-packet.js";

const TUNNEL_PROTOCOL = "bsm4-ip-tunnel-v1";

export async function fetchIpTunnelProtocol() {
  const res = await fetch(apiUrl("/api/chain-mesh/tunnel/ip/protocol"));
  return res.json();
}

export async function openIpTunnelChannel(opts = {}) {
  const res = await fetch(apiUrl("/api/chain-mesh/tunnel/ip/channel"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
  const data = await res.json();
  if (!data?.ok) throw new Error(data?.error || "tunnel channel open failed");
  return data;
}

export async function sendIpDatagram({
  channelId,
  sender = "",
  recipient = "",
  ipPacket,
  verifyChecksum = true,
} = {}) {
  const bytes =
    ipPacket instanceof Uint8Array
      ? ipPacket
      : typeof ipPacket === "string"
        ? hexToBytes(ipPacket.replace(/\s+/g, ""))
        : null;
  if (!bytes?.length) throw new Error("ipPacket required (Uint8Array or hex)");

  const res = await fetch(apiUrl("/api/chain-mesh/tunnel/ip/send"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      channel_id: channelId,
      sender,
      recipient,
      ip_packet_b64: bytesToB64(bytes),
      verify_checksum: verifyChecksum,
    }),
  });
  const data = await res.json();
  if (!data?.ok) throw new Error(data?.error || "IP send failed");
  return data;
}

export async function pollIpTunnelInbox(recipient, { channelId = "", sinceSeq = 0 } = {}) {
  const q = new URLSearchParams({ since_seq: String(sinceSeq), limit: "50" });
  if (channelId) q.set("channel_id", channelId);
  const res = await fetch(
    apiUrl(`/api/chain-mesh/tunnel/ip/inbox/${encodeURIComponent(recipient)}?${q}`),
    { cache: "no-store" },
  );
  return res.json();
}

export function hexToBytes(hex) {
  const h = String(hex || "").trim();
  if (h.length % 2) throw new Error("invalid hex length");
  const out = new Uint8Array(h.length / 2);
  for (let i = 0; i < out.length; i += 1) {
    out[i] = parseInt(h.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

export function bytesToHex(bytes) {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Build minimal IPv4 ICMP echo request (protocol demo / ping-over-mesh). */
export function buildIcmpEchoRequest(srcIp, dstIp, { id = 1, seq = 1 } = {}) {
  const src = parseIpv4(srcIp);
  const dst = parseIpv4(dstIp);
  const icmp = new Uint8Array(8);
  icmp[0] = 8;
  icmp[1] = 0;
  icmp[2] = 0;
  icmp[3] = 0;
  icmp[4] = (id >> 8) & 0xff;
  icmp[5] = id & 0xff;
  icmp[6] = (seq >> 8) & 0xff;
  icmp[7] = seq & 0xff;
  const csum = icmpChecksum(icmp);
  icmp[2] = (csum >> 8) & 0xff;
  icmp[3] = csum & 0xff;

  const totalLen = 20 + icmp.length;
  const ip = new Uint8Array(totalLen);
  ip[0] = 0x45;
  ip[1] = 0;
  ip[2] = (totalLen >> 8) & 0xff;
  ip[3] = totalLen & 0xff;
  ip[4] = 0;
  ip[5] = 0;
  ip[6] = 0;
  ip[7] = 0;
  ip[8] = 64;
  ip[9] = 1;
  ip[10] = 0;
  ip[11] = 0;
  ip.set(src, 12);
  ip.set(dst, 16);
  const ipCsum = ipv4HeaderChecksum(ip);
  ip[10] = (ipCsum >> 8) & 0xff;
  ip[11] = ipCsum & 0xff;
  ip.set(icmp, 20);
  return ip;
}

function parseIpv4(addr) {
  return Uint8Array.from(String(addr).split(".").map((n) => Number(n) & 0xff));
}

function ipv4HeaderChecksum(header) {
  let sum = 0;
  for (let i = 0; i < 20; i += 2) {
    if (i === 10) continue;
    sum += (header[i] << 8) + header[i + 1];
  }
  while (sum > 0xffff) sum = (sum & 0xffff) + (sum >> 16);
  return (~sum) & 0xffff;
}

function icmpChecksum(data) {
  let sum = 0;
  for (let i = 0; i < data.length; i += 2) {
    sum += (data[i] << 8) + (data[i + 1] || 0);
  }
  while (sum > 0xffff) sum = (sum & 0xffff) + (sum >> 16);
  return (~sum) & 0xffff;
}

/** Build IPv4 packet with TCP segment (20-byte header, no options). */
export function buildTcpIpPacket(
  srcIp,
  dstIp,
  {
    srcPort = 44000,
    dstPort = 80,
    seq = 1,
    ack = 1,
    flags = 0x18,
    payload = new Uint8Array(0),
  } = {},
) {
  const dstAddr = String(dstIp).replace(/:.*/, "");
  if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(dstAddr)) {
    throw new Error("dstIp required (IPv4 destination for TCP header)");
  }
  const src = parseIpv4(srcIp);
  const dst = parseIpv4(dstAddr);
  const tcpLen = 20 + payload.length;
  const totalLen = 20 + tcpLen;
  const ip = new Uint8Array(totalLen);
  ip[0] = 0x45;
  ip[2] = (totalLen >> 8) & 0xff;
  ip[3] = totalLen & 0xff;
  ip[8] = 64;
  ip[9] = 6;
  ip.set(src, 12);
  ip.set(dst, 16);
  const ipCsum = ipv4HeaderChecksum(ip);
  ip[10] = (ipCsum >> 8) & 0xff;
  ip[11] = ipCsum & 0xff;

  const tcp = new Uint8Array(tcpLen);
  tcp[0] = (srcPort >> 8) & 0xff;
  tcp[1] = srcPort & 0xff;
  tcp[2] = (dstPort >> 8) & 0xff;
  tcp[3] = dstPort & 0xff;
  tcp[4] = (seq >> 24) & 0xff;
  tcp[5] = (seq >> 16) & 0xff;
  tcp[6] = (seq >> 8) & 0xff;
  tcp[7] = seq & 0xff;
  tcp[8] = (ack >> 24) & 0xff;
  tcp[9] = (ack >> 16) & 0xff;
  tcp[10] = (ack >> 8) & 0xff;
  tcp[11] = ack & 0xff;
  tcp[12] = 0x50;
  tcp[13] = flags & 0xff;
  tcp[14] = 0x20;
  tcp[15] = 0x00;
  const tcpCsum = tcpChecksum(srcIp, dstAddr, tcp, payload);
  tcp[16] = (tcpCsum >> 8) & 0xff;
  tcp[17] = tcpCsum & 0xff;
  tcp.set(payload, 20);

  const out = new Uint8Array(totalLen);
  out.set(ip);
  out.set(tcp, 20);
  return out;
}

/** Minimal TLS 1.2 ClientHello with SNI for end-to-end passthrough. */
export function buildTlsClientHello(hostname) {
  const random = crypto.getRandomValues(new Uint8Array(32));
  const host = new TextEncoder().encode(String(hostname || "").trim());
  if (!host.length) throw new Error("hostname required for ClientHello");

  const ciphers = new Uint8Array([0x13, 0x01, 0x13, 0x02, 0x13, 0x03, 0xc0, 0x2f]);
  const sniEntry = new Uint8Array(1 + 2 + host.length);
  sniEntry[0] = 0;
  sniEntry[1] = (host.length >> 8) & 0xff;
  sniEntry[2] = host.length & 0xff;
  sniEntry.set(host, 3);
  const sniList = new Uint8Array(2 + sniEntry.length);
  sniList[0] = (sniEntry.length >> 8) & 0xff;
  sniList[1] = sniEntry.length & 0xff;
  sniList.set(sniEntry, 2);
  const sniExt = new Uint8Array(4 + sniList.length);
  sniExt[0] = 0;
  sniExt[1] = 0;
  sniExt[2] = (sniList.length >> 8) & 0xff;
  sniExt[3] = sniList.length & 0xff;
  sniExt.set(sniList, 4);

  const groupsExt = new Uint8Array([
    0x00, 0x0a, 0x00, 0x08, 0x00, 0x06, 0x00, 0x17, 0x00, 0x18, 0x00, 0x1d,
  ]);
  const sigExt = new Uint8Array([
    0x00, 0x0d, 0x00, 0x12, 0x00, 0x10, 0x04, 0x03, 0x08, 0x04, 0x04, 0x01, 0x05,
    0x03, 0x08, 0x05, 0x05, 0x01, 0x08, 0x06, 0x06, 0x01, 0x02, 0x01,
  ]);
  const keyMaterial = crypto.getRandomValues(new Uint8Array(32));
  const keyShareEntry = new Uint8Array(2 + 2 + 32);
  keyShareEntry[0] = 0x00;
  keyShareEntry[1] = 0x1d;
  keyShareEntry[2] = 0;
  keyShareEntry[3] = 32;
  keyShareEntry.set(keyMaterial, 4);
  const keyShareList = new Uint8Array(2 + keyShareEntry.length);
  keyShareList[0] = (keyShareEntry.length >> 8) & 0xff;
  keyShareList[1] = keyShareEntry.length & 0xff;
  keyShareList.set(keyShareEntry, 2);
  const keyShareExt = new Uint8Array(4 + keyShareList.length);
  keyShareExt[0] = 0x00;
  keyShareExt[1] = 0x33;
  keyShareExt[2] = (keyShareList.length >> 8) & 0xff;
  keyShareExt[3] = keyShareList.length & 0xff;
  keyShareExt.set(keyShareList, 4);
  const extensions = new Uint8Array(
    sniExt.length + groupsExt.length + sigExt.length + keyShareExt.length,
  );
  extensions.set(sniExt, 0);
  extensions.set(groupsExt, sniExt.length);
  extensions.set(sigExt, sniExt.length + groupsExt.length);
  extensions.set(keyShareExt, sniExt.length + groupsExt.length + sigExt.length);

  const body = new Uint8Array(2 + 32 + 1 + 2 + ciphers.length + 2 + 2 + extensions.length);
  let p = 0;
  body[p++] = 0x03;
  body[p++] = 0x03;
  body.set(random, p);
  p += 32;
  body[p++] = 0;
  body[p++] = 0;
  body[p++] = ciphers.length;
  body.set(ciphers, p);
  p += ciphers.length;
  body[p++] = 1;
  body[p++] = 0;
  body[p++] = (extensions.length >> 8) & 0xff;
  body[p++] = extensions.length & 0xff;
  body.set(extensions, p);

  const handshake = new Uint8Array(4 + body.length);
  handshake[0] = 0x01;
  handshake[1] = (body.length >> 16) & 0xff;
  handshake[2] = (body.length >> 8) & 0xff;
  handshake[3] = body.length & 0xff;
  handshake.set(body, 4);

  const record = new Uint8Array(5 + handshake.length);
  record[0] = 0x16;
  record[1] = 0x03;
  record[2] = 0x01;
  record[3] = (handshake.length >> 8) & 0xff;
  record[4] = handshake.length & 0xff;
  record.set(handshake, 5);
  return record;
}

export function buildTlsClientHelloPacket(
  srcIp,
  dstIp,
  hostname,
  { srcPort = 44100, dstPort = 443, seq = 1, ack = 1 } = {},
) {
  const tls = buildTlsClientHello(hostname);
  return buildTcpIpPacket(srcIp, dstIp, {
    srcPort,
    dstPort,
    seq,
    ack,
    flags: 0x18,
    payload: tls,
  });
}

export function summarizeTlsPayload(bytes) {
  if (!bytes?.length || bytes.length < 5) return "";
  const t = bytes[0];
  if (![0x14, 0x15, 0x16, 0x17].includes(t)) return "";
  const ver = `${bytes[1]}.${bytes[2].toString(16).padStart(2, "0")}`;
  const names = {
    0x14: "change_cipher_spec",
    0x15: "alert",
    0x16: "handshake",
    0x17: "application_data",
  };
  let extra = "";
  if (t === 0x16 && bytes.length > 5) {
    if (bytes[5] === 0x01) extra = " ClientHello";
    else if (bytes[5] === 0x02) extra = " ServerHello";
    else extra = ` hs=${bytes[5].toString(16)}`;
  }
  return `tls ${names[t] || t} v${ver}${extra}`;
}

/** Build IPv4 TCP segment with HTTP GET for mesh-gateway egress (port 80 or 443). */
export function buildHttpGetRequest(
  srcIp,
  host,
  path = "/",
  { srcPort = 44000, dstIp = "", dstPort = 80 } = {},
) {
  const reqPath = path.startsWith("/") ? path : `/${path}`;
  const http =
    `GET ${reqPath} HTTP/1.1\r\n` +
    `Host: ${host}\r\n` +
    "User-Agent: Bloodstone-BSM4-Browser/1.0\r\n" +
    "Connection: close\r\n" +
    "\r\n";
  const payload = new TextEncoder().encode(http);
  const dstAddr = String(dstIp || host).replace(/:.*/, "");
  return buildTcpIpPacket(srcIp, dstAddr, { srcPort, dstPort, payload });
}

/** Convenience wrapper for HTTPS GET (TCP port 443). */
export function buildHttpsGetRequest(srcIp, host, path = "/", opts = {}) {
  return buildHttpGetRequest(srcIp, host, path, { ...opts, dstPort: 443 });
}

function tcpChecksum(srcIp, dstIp, tcpHeader, payload) {
  const src = parseIpv4(srcIp);
  const dst = parseIpv4(dstIp);
  const pseudo = new Uint8Array(12 + tcpHeader.length + payload.length);
  pseudo.set(src, 0);
  pseudo.set(dst, 4);
  pseudo[9] = 6;
  const total = tcpHeader.length + payload.length;
  pseudo[10] = (total >> 8) & 0xff;
  pseudo[11] = total & 0xff;
  pseudo.set(tcpHeader, 12);
  pseudo.set(payload, 12 + tcpHeader.length);
  let sum = 0;
  for (let i = 0; i < pseudo.length; i += 2) {
    sum += (pseudo[i] << 8) + (pseudo[i + 1] || 0);
  }
  while (sum > 0xffff) sum = (sum & 0xffff) + (sum >> 16);
  return (~sum) & 0xffff;
}

export function formatIpv4Summary(ipv4) {
  if (!ipv4) return "";
  let s = `${ipv4.src} → ${ipv4.dst} ${ipv4.protocol_name || ipv4.protocol}`;
  if (ipv4.src_port != null) s += ` :${ipv4.src_port}→:${ipv4.dst_port}`;
  if (ipv4.icmp_type != null) s += ` icmp type ${ipv4.icmp_type}`;
  return s;
}

export { TUNNEL_PROTOCOL };
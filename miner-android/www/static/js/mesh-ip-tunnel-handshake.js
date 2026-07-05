/**
 * Multi-round TLS handshake over BSM4 — flights 1–2 + application data decrypt.
 */

import {
  buildTcpIpPacket,
  pollIpTunnelInbox,
  sendIpDatagram,
  summarizeTlsPayload,
} from "./mesh-ip-tunnel.js";
import { resolveMeshGatewayRecipient, COORDINATOR_FALLBACK } from "./mesh-internet-gateway.js";
import { apiUrl } from "./miner-paths.js";
import {
  buildClientFlight2,
  decryptServerAppData,
  encryptClientAppData,
  flightHasAlert,
  generateX25519Keypair,
  parseTlsRecords,
  patchClientHelloKeyShare,
  patchClientHelloRandom,
  tlsStreamComplete,
} from "./mesh-tls13-crypto.js";

const GATEWAY_RECIPIENT = COORDINATOR_FALLBACK;

function b64ToBytes(b64) {
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0) & 0xff);
}

function bytesToB64(bytes) {
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
}

function extractTcpMeta(ipPacket) {
  if (ipPacket.length < 40) return { seq: 0, payload: new Uint8Array(0) };
  const ihl = (ipPacket[0] & 0x0f) * 4;
  const seq =
    ((ipPacket[ihl + 4] << 24) |
      (ipPacket[ihl + 5] << 16) |
      (ipPacket[ihl + 6] << 8) |
      ipPacket[ihl + 7]) >>>
    0;
  const dataOffset = (ipPacket[ihl + 12] >> 4) * 4;
  return { seq, payload: ipPacket.subarray(ihl + dataOffset) };
}

function randomBytes(n) {
  const out = new Uint8Array(n);
  crypto.getRandomValues(out);
  return out;
}

export class MeshTlsHandshake {
  constructor({
    channelId,
    sender,
    virtualIp,
    dstIp,
    dstPort = 18443,
    host = "bloodstone-tls-lab",
    useBrowserCrypto = true,
    gatewayRecipient = GATEWAY_RECIPIENT,
  }) {
    this.channelId = channelId;
    this.sender = sender;
    this.gatewayRecipient = gatewayRecipient;
    this.virtualIp = virtualIp;
    this.dstIp = dstIp;
    this.dstPort = dstPort;
    this.host = host;
    this.useBrowserCrypto = useBrowserCrypto;
    this.srcPort = 44100 + Math.floor(Math.random() * 800);
    this.clientSeq = 1;
    this.clientAck = 1;
    this.lastInboxSeq = 0;
    this.clientHelloRecord = null;
    this.handshakeId = "";
    this.connectIp = "";
    this.privateKey = null;
    this.serverFlight = new Uint8Array(0);
    this.appDataFlight = new Uint8Array(0);
    this.rxSegments = new Map();
    this.rxBaseSeq = null;
    this.phase = "idle";
  }

  async fetchClientHelloTemplate() {
    if (this.useBrowserCrypto) {
      const { privateKey, publicKeyRaw } = await generateX25519Keypair();
      this.privateKey = privateKey;
      const q = new URLSearchParams({
        host: this.host,
        connect_host: this.dstIp,
        port: String(this.dstPort),
        session: "0",
      });
      const res = await fetch(apiUrl(`/api/chain-mesh/tunnel/ip/tls/client-hello?${q}`), { cache: "no-store" });
      const data = await res.json();
      if (!data?.ok) throw new Error(data?.error || "ClientHello template failed");
      this.connectIp = data.connect_ip || "";
      let hello = b64ToBytes(data.client_hello_b64);
      hello = patchClientHelloRandom(hello, randomBytes(32));
      hello = patchClientHelloKeyShare(hello, publicKeyRaw);
      this.clientHelloRecord = hello;
      return hello;
    }
    const q = new URLSearchParams({
      host: this.host,
      connect_host: this.dstIp,
      port: String(this.dstPort),
    });
    const res = await fetch(apiUrl(`/api/chain-mesh/tunnel/ip/tls/client-hello?${q}`), { cache: "no-store" });
    const data = await res.json();
    if (!data?.ok) throw new Error(data?.error || "ClientHello template failed");
    this.handshakeId = data.handshake_id || "";
    this.connectIp = data.connect_ip || "";
    const hello = b64ToBytes(data.client_hello_b64);
    this.clientHelloRecord = hello;
    return hello;
  }

  async buildClientFlight2Bytes() {
    if (this.useBrowserCrypto && this.privateKey) {
      const built = await buildClientFlight2({
        clientHelloRecord: this.clientHelloRecord,
        serverFlight: this.serverFlight,
        privateKey: this.privateKey,
      });
      return built.flight2;
    }
    if (!this.handshakeId) throw new Error("handshake_id missing");
    const res = await fetch(apiUrl("/api/chain-mesh/tunnel/ip/tls/client-flight2"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        handshake_id: this.handshakeId,
        server_flight_b64: bytesToB64(this.serverFlight),
      }),
    });
    const data = await res.json();
    if (!data?.ok) throw new Error(data?.error || "Client flight 2 failed");
    return b64ToBytes(data.client_flight2_b64);
  }

  async encryptAppDataBytes(plaintext, seqOffset = 0) {
    if (this.useBrowserCrypto && this.privateKey) {
      return encryptClientAppData({
        clientHelloRecord: this.clientHelloRecord,
        serverFlight: this.serverFlight,
        privateKey: this.privateKey,
        plaintext,
        seqOffset,
      });
    }
    const res = await fetch(apiUrl("/api/chain-mesh/tunnel/ip/tls/encrypt-app-data"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        handshake_id: this.handshakeId,
        server_flight_b64: bytesToB64(this.serverFlight),
        plaintext_b64: bytesToB64(new TextEncoder().encode(plaintext)),
        seq_offset: seqOffset,
      }),
    });
    const data = await res.json();
    if (!data?.ok) throw new Error(data?.error || "App data encrypt failed");
    return b64ToBytes(data.app_data_b64 || "");
  }

  async decryptAppDataBytes(appBytes, seqOffset = 0) {
    if (this.useBrowserCrypto && this.privateKey) {
      return decryptServerAppData({
        clientHelloRecord: this.clientHelloRecord,
        serverFlight: this.serverFlight,
        privateKey: this.privateKey,
        appDataBytes: appBytes,
        seqOffset,
      });
    }
    const res = await fetch(apiUrl("/api/chain-mesh/tunnel/ip/tls/decrypt-app-data"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        handshake_id: this.handshakeId,
        server_flight_b64: bytesToB64(this.serverFlight),
        app_data_b64: bytesToB64(appBytes),
        seq_offset: seqOffset,
      }),
    });
    const data = await res.json();
    if (!data?.ok) throw new Error(data?.error || "App data decrypt failed");
    return {
      preview: data.preview || "",
      isHttp: Boolean(data.is_http),
      plaintext: b64ToBytes(data.plaintext_b64 || ""),
      records: Number(data.records) || 0,
      ticketRecords: Number(data.ticket_records) || 0,
      nextSeq: Number(data.next_seq) || 0,
    };
  }

  async sendTlsRecords(tlsBytes) {
    const ipPacket = buildTcpIpPacket(this.virtualIp, this.dstIp, {
      srcPort: this.srcPort,
      dstPort: this.dstPort,
      seq: this.clientSeq,
      ack: this.clientAck,
      flags: 0x18,
      payload: tlsBytes,
    });
    this.clientSeq += tlsBytes.length;
    return sendIpDatagram({
      channelId: this.channelId,
      sender: this.sender,
      recipient: this.gatewayRecipient,
      ipPacket,
    });
  }

  async triggerGatewayEgress() {
    await fetch(apiUrl("/api/chain-mesh/tunnel/ip/gateway/egress"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit: 8 }),
    });
  }

  _rebuildServerFlight() {
    if (!this.rxSegments.size) {
      this.serverFlight = new Uint8Array(0);
      return 0;
    }
    const baseSeq = Math.min(...this.rxSegments.keys());
    this.rxBaseSeq = baseSeq;
    const parts = [];
    let seq = baseSeq;
    while (this.rxSegments.has(seq)) {
      const chunk = this.rxSegments.get(seq);
      parts.push(chunk);
      seq += chunk.length;
    }
    const total = parts.reduce((n, p) => n + p.length, 0);
    const merged = new Uint8Array(total);
    let off = 0;
    for (const p of parts) {
      merged.set(p, off);
      off += p.length;
    }
    this.serverFlight = merged;
    return total;
  }

  ingestInboxPackets(packets) {
    const rx = (packets || [])
      .filter(
        (p) =>
          p.sender === GATEWAY_RECIPIENT &&
          Number(p.seq) > this.lastInboxSeq &&
          (!this.channelId || !p.channel_id || p.channel_id === this.channelId),
      )
      .sort((a, b) => Number(a.seq) - Number(b.seq));
    let appended = 0;
    for (const pkt of rx) {
      this.lastInboxSeq = Math.max(this.lastInboxSeq, Number(pkt.seq) || 0);
      if (!pkt.payload_b64) continue;
      const ip = b64ToBytes(pkt.payload_b64);
      const { seq, payload } = extractTcpMeta(ip);
      if (!payload.length) continue;
      this.rxSegments.set(seq, payload);
      appended += payload.length;
    }
    const total = this._rebuildServerFlight();
    if (!appended) return { appended: 0, summary: "", bytes: total };
    return {
      appended,
      bytes: total,
      summary: summarizeTlsPayload(this.serverFlight.subarray(0, 120)),
      records: parseTlsRecords(this.serverFlight).length,
      streamComplete: tlsStreamComplete(this.serverFlight),
    };
  }

  async pollServerFlight({
    attempts = 12,
    intervalMs = 1500,
    baselineBytes = 0,
    minNewBytes = 50,
    settlePolls = 0,
    requireStreamComplete = false,
  } = {}) {
    let idlePolls = 0;
    for (let i = 0; i < attempts; i += 1) {
      await this.triggerGatewayEgress();
      const inbox = await pollIpTunnelInbox(this.sender, {
        channelId: this.channelId,
        sinceSeq: 0,
      });
      const ingested = this.ingestInboxPackets(inbox.packets);
      const newBytes = this.serverFlight.length - baselineBytes;
      if (ingested.appended > 0) idlePolls = 0;
      else if (newBytes >= minNewBytes) idlePolls += 1;
      const streamOk = !requireStreamComplete || ingested.streamComplete;
      const settled = settlePolls > 0 ? idlePolls >= settlePolls : true;
      if (newBytes >= minNewBytes && settled && streamOk) {
        const tail = this.serverFlight.subarray(baselineBytes);
        this.phase = flightHasAlert(tail) ? "alert" : baselineBytes ? "handshake_complete" : "server_flight";
        return {
          ok: !flightHasAlert(tail),
          bytes: this.serverFlight.length,
          newBytes,
          ingested,
          phase: this.phase,
        };
      }
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    this.phase = "timeout";
    return { ok: false, bytes: this.serverFlight.length, phase: "timeout" };
  }

  async runFlight1() {
    this.phase = "fetching_hello";
    const hello = await this.fetchClientHelloTemplate();
    this.phase = "hello_sent";
    await this.sendTlsRecords(hello);
    await this.triggerGatewayEgress();
    const result = await this.pollServerFlight({
      attempts: 24,
      intervalMs: 1200,
      minNewBytes: 50,
      settlePolls: 2,
      requireStreamComplete: true,
    });
    return {
      phase: this.phase,
      clientHelloBytes: hello.length,
      serverFlightBytes: this.serverFlight.length,
      serverSummary: summarizeTlsPayload(this.serverFlight.subarray(0, 200)),
      handshakeId: this.handshakeId,
      connectIp: this.connectIp,
      useBrowserCrypto: this.useBrowserCrypto,
      ...result,
    };
  }

  async runFlight2() {
    if (this.phase !== "server_flight" || !this.serverFlight.length) {
      throw new Error("server flight 1 required before flight 2");
    }
    this.phase = "building_flight2";
    const flight2 = await this.buildClientFlight2Bytes();
    this.phase = "flight2_sent";
    await this.sendTlsRecords(flight2);
    const baselineBytes = this.serverFlight.length;
    const result = await this.pollServerFlight({
      attempts: 12,
      intervalMs: 1200,
      baselineBytes,
      minNewBytes: 1,
      settlePolls: 1,
    });
    this.appDataFlight = this.serverFlight.subarray(baselineBytes);
    return {
      phase: this.phase,
      clientFlight2Bytes: flight2.length,
      appDataBytes: this.appDataFlight.length,
      serverFlightBytes: this.serverFlight.length,
      serverSummary: summarizeTlsPayload(this.serverFlight.subarray(0, 200)),
      ...result,
    };
  }

  async runFlight3() {
    try {
      const ticketInfo = await this.decryptAppDataBytes(this.appDataFlight);
      const seqOffset = ticketInfo.nextSeq ?? ticketInfo.records ?? 0;

      const httpReq = `GET / HTTP/1.1\r\nHost: ${this.host}\r\nConnection: close\r\n\r\n`;
      this.phase = "app_data_sent";
      const clientApp = await this.encryptAppDataBytes(httpReq, 0);
      await this.sendTlsRecords(clientApp);

      const baselineBytes = this.serverFlight.length;
      const poll = await this.pollServerFlight({
        attempts: 12,
        intervalMs: 1200,
        baselineBytes,
        minNewBytes: 20,
        settlePolls: 1,
      });
      const httpFlight = this.serverFlight.subarray(baselineBytes);
      if (!httpFlight.length) {
        return {
          ok: false,
          phase: "no_http_response",
          ticketRecords: ticketInfo.ticketRecords ?? ticketInfo.records ?? 0,
          ...poll,
        };
      }

      const decrypted = await this.decryptAppDataBytes(httpFlight, seqOffset);
      return {
        ok: Boolean(decrypted.isHttp || decrypted.preview),
        phase: decrypted.isHttp ? "http_decrypted" : "app_data_decrypted",
        preview: decrypted.preview,
        isHttp: decrypted.isHttp,
        bytes: decrypted.plaintext?.length || 0,
        ticketRecords: ticketInfo.ticketRecords ?? 0,
        httpBytes: httpFlight.length,
        seqOffset,
        ...poll,
      };
    } catch (err) {
      return { ok: false, phase: "app_data_decrypt_failed", error: err.message || String(err) };
    }
  }
}

export async function runMeshTlsHandshake(opts) {
  const gatewayRecipient =
    opts.gatewayRecipient ||
    (await resolveMeshGatewayRecipient({
      publicIp: opts.publicIp || "",
      deviceId: opts.sender || "",
    }));
  const session = new MeshTlsHandshake({ ...opts, gatewayRecipient });
  const flight1 = await session.runFlight1();
  if (!flight1.ok) return { ...flight1, flights: 1 };
  if (!session.useBrowserCrypto && !session.handshakeId) return { ...flight1, flights: 1 };
  try {
    const flight2 = await session.runFlight2();
    const flight3 = await session.runFlight3();
    return {
      flights: flight3.ok ? 3 : 2,
      flight1,
      flight2,
      flight3,
      ok: Boolean(flight2.ok),
      phase: flight3.ok ? flight3.phase : flight2.phase,
      serverFlightBytes: flight2.serverFlightBytes,
      appDataBytes: flight2.appDataBytes,
      appPreview: flight3.preview || "",
      serverSummary: flight2.serverSummary,
      clientHelloBytes: flight1.clientHelloBytes,
      clientFlight2Bytes: flight2.clientFlight2Bytes,
      connectIp: flight1.connectIp,
      useBrowserCrypto: session.useBrowserCrypto,
    };
  } catch (err) {
    return {
      flights: 1,
      ...flight1,
      flight2Error: err.message || String(err),
    };
  }
}
/**
 * Share this device's internet with all LAN miners (BSM4 peer gateway).
 * Runs HTTP/HTTPS egress via fetch() on the APK or browser.
 */

import { apiUrl } from "./miner-paths.js";
import { buildTcpIpPacket } from "./mesh-ip-tunnel.js";
import { registerInternetGateway, unregisterInternetGateway } from "./mesh-internet-gateway.js";

const GATEWAY_VIRTUAL_REPLY = "10.73.0.1";

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

function parseHttpGet(tcpPayload) {
  const text = new TextDecoder().decode(tcpPayload);
  const m = text.match(/^GET\s+(\S+)\s+HTTP\/[\d.]+\r\n/i);
  if (!m) return null;
  const path = m[1];
  const hostM = text.match(/\r\nHost:\s*([^\r\n]+)/i);
  const host = hostM ? hostM[1].trim() : "";
  return { path, host, raw: text };
}

function buildHttpReply(body, contentType = "text/html") {
  const header =
    `HTTP/1.1 200 OK\r\n` +
    `Content-Type: ${contentType}\r\n` +
    `Connection: close\r\n` +
    `Content-Length: ${body.length}\r\n\r\n`;
  const enc = new TextEncoder();
  const head = enc.encode(header);
  const out = new Uint8Array(head.length + body.length);
  out.set(head, 0);
  out.set(body instanceof Uint8Array ? body : enc.encode(String(body)), head.length);
  return out;
}

function extractTcpFromIp(ipPacket) {
  const ihl = (ipPacket[0] & 0x0f) * 4;
  const src = ipPacket.subarray(12, 16);
  const dst = ipPacket.subarray(16, 20);
  const srcIp = Array.from(src).join(".");
  const dstIp = Array.from(dst).join(".");
  const tcpOff = (ipPacket[ihl + 12] >> 4) * 4;
  const srcPort = (ipPacket[ihl] << 8) | ipPacket[ihl + 1];
  const dstPort = (ipPacket[ihl + 2] << 8) | ipPacket[ihl + 3];
  const seq = ((ipPacket[ihl + 4] << 24) | (ipPacket[ihl + 5] << 16) | (ipPacket[ihl + 6] << 8) | ipPacket[ihl + 7]) >>> 0;
  const ack = ((ipPacket[ihl + 8] << 24) | (ipPacket[ihl + 9] << 16) | (ipPacket[ihl + 10] << 8) | ipPacket[ihl + 11]) >>> 0;
  const payload = ipPacket.subarray(ihl + tcpOff);
  return { srcIp, dstIp, srcPort, dstPort, seq, ack, payload };
}

async function handleHttpPacket(pkt, deviceId) {
  const ip = b64ToBytes(pkt.payload_b64);
  const tcp = extractTcpFromIp(ip);
  const req = parseHttpGet(tcp.payload);
  if (!req?.host) return false;
  const useTls = tcp.dstPort === 443;
  const url = `${useTls ? "https" : "http"}://${req.host}${req.path}`;
  const res = await fetch(url, { method: "GET", cache: "no-store" });
  const body = new Uint8Array(await res.arrayBuffer());
  const httpBytes = buildHttpReply(body, res.headers.get("content-type") || "application/octet-stream");
  const replyIp = buildTcpIpPacket(GATEWAY_VIRTUAL_REPLY, tcp.srcIp, {
    srcPort: tcp.dstPort,
    dstPort: tcp.srcPort,
    seq: tcp.ack || 1,
    ack: tcp.seq + tcp.payload.length,
    flags: 0x18,
    payload: httpBytes,
  });
  await fetch(apiUrl("/api/chain-mesh/internet-gateway/reply"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      device_id: deviceId,
      packet_id: pkt.packet_id,
      channel_id: pkt.channel_id,
      mesh_sender: pkt.sender,
      reply_ip_b64: bytesToB64(replyIp),
      action: useTls ? "peer_https_fetch" : "peer_http_fetch",
    }),
  });
  return true;
}

const SHARE_INTERNET_STORAGE_KEY = "bloodstone-share-internet";

export async function resolvePublicIp() {
  try {
    const res = await fetch("https://api.ipify.org?format=json", {
      cache: "no-store",
      signal: AbortSignal.timeout(6000),
    });
    const data = await res.json();
    return String(data?.ip || "").trim();
  } catch {
    return "";
  }
}

export function initShareInternetPanel({
  root = document,
  resolveDeviceId = async () => "",
  getLanIp = async () => "",
  peerKind = "android",
  onLog = () => {},
  onStatus = () => {},
} = {}) {
  const panel = root.getElementById("share-internet-panel");
  const toggle = root.getElementById("share-internet-toggle");
  const statusEl = root.getElementById("share-internet-status");
  const electedEl = root.getElementById("share-internet-elected");
  if (!panel || !toggle) return null;

  let loop = null;
  let publicIpCache = "";

  const setStatus = (text, kind = "") => {
    if (statusEl) {
      statusEl.textContent = text;
      statusEl.className = `muted small${kind ? ` ${kind}` : ""}`;
    }
    onStatus(text, kind);
  };

  const refreshElected = async (deviceId) => {
    if (!electedEl) return;
    try {
      const { fetchElectedGateway } = await import("./mesh-internet-gateway.js");
      const elected = await fetchElectedGateway({
        publicIp: publicIpCache,
        deviceId,
      });
      const src = elected.source === "peer" ? "household peer" : "coordinator VPS";
      electedEl.textContent =
        `LAN miners route through ${elected.recipient || "mesh-gateway"} (${src})`;
    } catch {
      electedEl.textContent = "Gateway election unavailable";
    }
  };

  const startSharing = async () => {
    const deviceId = await resolveDeviceId();
    if (!deviceId) {
      setStatus("Device id required — open miner first", "error");
      toggle.checked = false;
      return;
    }
    if (!publicIpCache) {
      publicIpCache = await resolvePublicIp();
    }
    const lanIp = await getLanIp();
    loop = startShareInternetLoop({
      deviceId,
      publicIp: publicIpCache,
      lanIp,
      peerKind,
      onStatus: (s) => {
        setStatus(s.message || (s.sharing ? "Sharing internet" : "Stopped"), s.ok ? "ok" : "error");
      },
    });
    await loop.start();
    onLog("Sharing internet with LAN miners over mesh", "success");
    void refreshElected(deviceId);
  };

  const stopSharing = async () => {
    if (loop) {
      await loop.stop();
      loop = null;
    }
    onLog("Stopped sharing internet", "");
  };

  toggle.addEventListener("change", async () => {
    try {
      localStorage.setItem(SHARE_INTERNET_STORAGE_KEY, toggle.checked ? "1" : "0");
    } catch {
      /* ignore */
    }
    if (toggle.checked) {
      await startSharing();
    } else {
      await stopSharing();
      setStatus("Not sharing — enable to give LAN miners your internet");
    }
  });

  void (async () => {
    const deviceId = await resolveDeviceId();
    void refreshElected(deviceId);
    window.setInterval(() => void refreshElected(deviceId), 30000);
    let autoStart = false;
    try {
      autoStart = localStorage.getItem(SHARE_INTERNET_STORAGE_KEY) === "1";
    } catch {
      /* ignore */
    }
    if (autoStart) {
      toggle.checked = true;
      await startSharing();
    } else {
      setStatus("Not sharing — enable when this phone has Wi‑Fi or mobile data");
    }
  })();

  return {
    isSharing: () => Boolean(loop?.isActive?.()),
    stop: stopSharing,
  };
}

export function startShareInternetLoop({
  deviceId,
  publicIp = "",
  lanIp = "",
  peerKind = "android",
  intervalMs = 4000,
  onStatus = () => {},
} = {}) {
  let timer = null;
  let active = false;

  const tick = async () => {
    if (!active) return;
    try {
      await registerInternetGateway({
        deviceId,
        publicIp,
        lanIp,
        peerKind,
        shareInternet: true,
      });
      const res = await fetch(
        apiUrl(`/api/chain-mesh/internet-gateway/pending/${encodeURIComponent(deviceId)}?limit=8`),
        { cache: "no-store" },
      );
      const data = await res.json();
      const packets = data?.packets || [];
      let handled = 0;
      for (const pkt of packets) {
        try {
          if (await handleHttpPacket(pkt, deviceId)) handled += 1;
        } catch {
          /* try server-side peer-egress fallback */
          await fetch(apiUrl("/api/chain-mesh/internet-gateway/peer-egress"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device_id: deviceId, limit: 4 }),
          });
        }
      }
      onStatus({
        ok: true,
        sharing: true,
        pending: packets.length,
        handled,
        message: handled
          ? `Shared internet · ${handled} request(s)`
          : packets.length
            ? `${packets.length} pending`
            : "Listening for LAN miners",
      });
    } catch (err) {
      onStatus({ ok: false, sharing: true, message: err.message || String(err) });
    }
  };

  return {
    async start() {
      if (active) return;
      active = true;
      await tick();
      timer = setInterval(() => void tick(), intervalMs);
    },
    async stop() {
      active = false;
      if (timer) clearInterval(timer);
      timer = null;
      try {
        await unregisterInternetGateway(deviceId);
      } catch {
        /* ignore */
      }
      onStatus({ ok: true, sharing: false, message: "Stopped sharing" });
    },
    isActive: () => active,
  };
}
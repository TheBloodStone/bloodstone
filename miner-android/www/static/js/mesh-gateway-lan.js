/**
 * Direct LAN internet gateway — phones on the same Wi‑Fi proxy HTTP via :18341.
 */

import { apiUrl } from "./miner-paths.js";
import { discoverPacketPeerEndpoints } from "./mesh-packet-lan.js";
import { listDiscoveredLanPeers } from "./local-node.js";

const GATEWAY_PORT = 18341;
const PROBE_TIMEOUT_MS = 2500;

async function probeGateway(ip) {
  if (!ip) return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const res = await fetch(`http://${ip}:${GATEWAY_PORT}/gateway/status`, {
      signal: controller.signal,
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (!data?.sharing) return null;
    return { ip, port: GATEWAY_PORT, deviceId: data.device_id || "" };
  } catch (_) {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export async function discoverLanInternetGateways() {
  const seen = new Set();
  const gateways = [];
  const push = (row) => {
    if (!row?.ip || seen.has(row.ip)) return;
    seen.add(row.ip);
    gateways.push(row);
  };

  try {
    const peers = await listDiscoveredLanPeers({ fullOnly: false });
    for (const peer of peers || []) {
      const ip = String(peer.lan_ip || peer.host || "").trim();
      const row = await probeGateway(ip);
      if (row) push(row);
    }
  } catch (_) {
    /* ignore */
  }

  const endpoints = await discoverPacketPeerEndpoints();
  for (const ep of endpoints) {
    const row = await probeGateway(ep.ip);
    if (row) push({ ...row, deviceId: ep.device_id || row.deviceId });
  }

  return gateways;
}

export async function findBestLanGateway() {
  const gateways = await discoverLanInternetGateways();
  return gateways.length ? gateways[0] : null;
}

export async function lanGatewayFetch(url, { timeoutMs = 20000 } = {}) {
  const gateway = await findBestLanGateway();
  if (!gateway?.ip) return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`http://${gateway.ip}:${gateway.port}/gateway/http`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({ url, method: "GET" }),
    });
    const data = await res.json();
    if (!data?.ok || !data.body_b64) return null;
    const bytes = Uint8Array.from(atob(data.body_b64), (c) => c.charCodeAt(0) & 0xff);
    const text = new TextDecoder().decode(bytes);
    return {
      ok: data.status >= 200 && data.status < 300,
      status: data.status,
      text,
      json: () => Promise.resolve(JSON.parse(text)),
      gatewayIp: gateway.ip,
    };
  } catch (_) {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export async function checkDirectInternet() {
  try {
    const res = await fetch("https://api.ipify.org?format=json", {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    return res.ok;
  } catch (_) {
    return false;
  }
}
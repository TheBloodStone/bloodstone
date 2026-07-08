/**
 * Auto-use a household LAN gateway when this phone has no direct internet.
 * Works while mining or idle — no full node required on the client.
 */

import { apiUrl } from "./miner-paths.js";
import {
  checkDirectInternet,
  findBestLanGateway,
  lanGatewayFetch,
} from "./mesh-gateway-lan.js";
import { fetchElectedGateway } from "./mesh-internet-gateway.js";
import { resolveDeviceId } from "./chain-mesh.js";

const CLIENT_STORAGE_KEY = "bloodstone-lan-internet-client";
let clientEnabled = true;
let lastGatewayIp = "";
let pollTimer = null;

export function setLanInternetClientEnabled(on) {
  clientEnabled = on !== false;
  try {
    localStorage.setItem(CLIENT_STORAGE_KEY, clientEnabled ? "1" : "0");
  } catch (_) {
    /* ignore */
  }
}

export function isLanInternetClientEnabled() {
  return clientEnabled;
}

async function refreshGatewayHint(deviceId) {
  if (await checkDirectInternet()) {
    lastGatewayIp = "";
    return { mode: "direct", message: "Using phone internet" };
  }
  const lan = await findBestLanGateway();
  if (lan?.ip) {
    lastGatewayIp = lan.ip;
    return { mode: "lan", message: `Using LAN gateway ${lan.ip}`, gateway: lan };
  }
  try {
    const elected = await fetchElectedGateway({ deviceId });
    if (elected?.lan_ip) {
      lastGatewayIp = elected.lan_ip;
      return { mode: "mesh", message: `Mesh gateway ${elected.recipient}`, gateway: elected };
    }
  } catch (_) {
    /* offline */
  }
  return { mode: "offline", message: "No internet — enable Share internet on a LAN phone" };
}

export async function fetchViaLanGateway(url) {
  if (!clientEnabled) return null;
  if (await checkDirectInternet()) return null;
  return lanGatewayFetch(url);
}

export async function fetchPoolApi(path) {
  const url = apiUrl(path);
  try {
    const res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(12000) });
    if (res.ok) return res;
  } catch (_) {
    /* try LAN gateway */
  }
  const proxied = await fetchViaLanGateway(url);
  if (!proxied?.ok) return null;
  return {
    ok: true,
    json: () => proxied.json(),
    text: () => Promise.resolve(proxied.text),
  };
}

export function initLanInternetClient({
  onLog = () => {},
  onStatus = () => {},
  resolveId = resolveDeviceId,
} = {}) {
  try {
    clientEnabled = localStorage.getItem(CLIENT_STORAGE_KEY) !== "0";
  } catch (_) {
    clientEnabled = true;
  }

  const tick = async () => {
    if (!clientEnabled) return;
    const deviceId = await resolveId();
    const hint = await refreshGatewayHint(deviceId);
    onStatus(hint.message, hint.mode === "offline" ? "warn" : "ok");
    if (hint.mode === "lan" && hint.gateway?.ip) {
      onLog(`LAN internet via ${hint.gateway.ip} (optional gateway on household Wi‑Fi)`, "success");
    }
  };

  void tick();
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => void tick(), 30000);

  return {
    stop: () => {
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = null;
    },
    lastGatewayIp: () => lastGatewayIp,
  };
}
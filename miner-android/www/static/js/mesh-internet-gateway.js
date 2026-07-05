/**
 * Free internet over the mesh — elect household gateway, register as sharer.
 */

import { apiUrl } from "./miner-paths.js";

const COORDINATOR_FALLBACK = "mesh-gateway";

export async function fetchElectedGateway({ publicIp = "", deviceId = "" } = {}) {
  const q = new URLSearchParams();
  if (publicIp) q.set("public_ip", publicIp);
  if (deviceId) q.set("device_id", deviceId);
  const res = await fetch(apiUrl(`/api/chain-mesh/internet-gateway/elected?${q}`), {
    cache: "no-store",
  });
  const data = await res.json();
  if (!data?.ok) throw new Error(data?.error || "gateway election failed");
  return data;
}

export async function registerInternetGateway({
  deviceId,
  publicIp = "",
  lanIp = "",
  peerKind = "android",
  shareInternet = true,
  label = "",
} = {}) {
  const res = await fetch(apiUrl("/api/chain-mesh/internet-gateway/register"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      device_id: deviceId,
      public_ip: publicIp,
      lan_ip: lanIp,
      peer_kind: peerKind,
      share_internet: shareInternet,
      label: label || `Gateway ${deviceId?.slice(0, 12) || ""}`,
    }),
  });
  const data = await res.json();
  if (!data?.ok) throw new Error(data?.error || "gateway register failed");
  return data;
}

export async function unregisterInternetGateway(deviceId) {
  const res = await fetch(apiUrl("/api/chain-mesh/internet-gateway/unregister"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_id: deviceId }),
  });
  return res.json();
}

export async function resolveMeshGatewayRecipient({ publicIp = "", deviceId = "" } = {}) {
  try {
    const elected = await fetchElectedGateway({ publicIp, deviceId });
    return elected.recipient || COORDINATOR_FALLBACK;
  } catch {
    return COORDINATOR_FALLBACK;
  }
}

export { COORDINATOR_FALLBACK };
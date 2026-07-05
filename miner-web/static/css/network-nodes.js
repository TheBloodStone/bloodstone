/** Network-wide connected node counts (APK + web dashboards). */

import { apiUrl } from "./miner-paths.js";
import { isCapacitorAndroid } from "./device-fleet.js";
import { registerLanOnNetwork } from "./local-node.js";

let lastPayload = null;
let pollTimer = null;

function formatBreakdown(data) {
  if (!data) return "";
  const parts = [];
  if (data.chain_p2p_connections > 0) {
    parts.push(`${data.chain_p2p_connections} chain P2P`);
  }
  if (data.mesh_storage_peers > 0) {
    parts.push(`${data.mesh_storage_peers} mesh storage`);
  }
  if (data.local_vps_nodes > 0) {
    parts.push(`${data.local_vps_nodes} local VPS`);
  }
  if (data.fleet_offload_nodes > 0) {
    parts.push(`${data.fleet_offload_nodes} fleet offload`);
  }
  if (data.lan_registered_nodes > 0) {
    parts.push(`${data.lan_registered_nodes} LAN registered`);
  }
  return parts.length ? parts.join(" · ") : "No peers reported yet";
}

export function updateNetworkNodesPanel(data = lastPayload) {
  if (!data) return;
  lastPayload = data;

  const totalEl = document.getElementById("network-nodes-total");
  const breakdownEl = document.getElementById("network-nodes-breakdown");
  const chainEl = document.getElementById("network-nodes-chain");
  const meshEl = document.getElementById("network-nodes-mesh");
  const localEl = document.getElementById("network-nodes-local");
  const fleetEl = document.getElementById("network-nodes-fleet");
  const lanEl = document.getElementById("network-nodes-lan");
  const fleetLineEl = document.getElementById("fleet-network-nodes");

  const total = Number(data.total_connected ?? 0);
  if (totalEl) totalEl.textContent = String(total);
  if (breakdownEl) breakdownEl.textContent = formatBreakdown(data);
  if (chainEl) chainEl.textContent = String(data.chain_p2p_connections ?? "—");
  if (meshEl) meshEl.textContent = String(data.mesh_storage_peers ?? "—");
  if (localEl) localEl.textContent = String(data.local_vps_nodes ?? "—");
  if (fleetEl) {
    fleetEl.textContent = String(data.fleet_offload_nodes ?? data.fleet_active_devices ?? "—");
  }
  if (lanEl) lanEl.textContent = String(data.lan_registered_nodes ?? "—");
  if (fleetLineEl) {
    fleetLineEl.textContent = `${total} network node${total === 1 ? "" : "s"} connected`;
  }
}

export async function refreshNetworkNodes() {
  try {
    const res = await fetch(apiUrl("/api/network/nodes"));
    if (!res.ok) return null;
    const data = await res.json();
    if (!data?.ok) return null;
    updateNetworkNodesPanel(data);
    return data;
  } catch (_) {
    return null;
  }
}

export function startNetworkNodesPolling(intervalMs = 60000) {
  if (pollTimer) return;
  void refreshNetworkNodes();
  pollTimer = window.setInterval(() => {
    void refreshNetworkNodes();
  }, intervalMs);
}

export function cachedNetworkNodes() {
  return lastPayload;
}

function setRegisterLanStatus(text, kind = "") {
  const el = document.getElementById("register-lan-status");
  if (!el) return;
  el.textContent = text;
  el.className = `muted small${kind ? ` ${kind}` : ""}`;
}

export function initRegisterLanButton() {
  const btn = document.getElementById("btn-register-lan");
  if (!btn || !isCapacitorAndroid()) return;
  btn.hidden = false;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    setRegisterLanStatus("Registering this phone on the network…");
    try {
      const result = await registerLanOnNetwork();
      const deviceId = result?.response?.device_id || result?.response?.node?.device_id || "";
      const httpCode = result?.httpCode;
      setRegisterLanStatus(
        deviceId
          ? `LAN registered (${deviceId}${httpCode ? ` · HTTP ${httpCode}` : ""})`
          : `LAN registered with pool${httpCode ? ` · HTTP ${httpCode}` : ""}`,
        result?.ok === false ? "error" : "ok",
      );
      if (result?.ok === false) {
        throw new Error(result?.error || result?.response?.error || "LAN registration failed");
      }
      await refreshNetworkNodes();
    } catch (err) {
      setRegisterLanStatus(err.message || String(err), "error");
    } finally {
      btn.disabled = false;
    }
  });
}
/** Android APK: pool + LAN stratum host/port values for external miners. */

import { stratumEndpoints } from "./stratum-transport.js";
import { isCapacitorAndroid } from "./device-fleet.js";
import { isAndroidAppContext } from "./capacitor-ready.js";
import { fetchDeviceNetworkInfo } from "./device-network-info.js";

const POOL_ALGOS = [
  { id: "neoscrypt", label: "Neoscrypt-Xaya (CPU / GPU)", bitaxeNote: false },
  { id: "yespower", label: "Yespower R16 (CPU)", bitaxeNote: false },
  { id: "sha256d", label: "SHA256d / Bitaxe (ASIC)", bitaxeNote: true },
];

const LAN_ALGOS = [
  { id: "neoscrypt", label: "Neoscrypt-Xaya" },
  { id: "yespower", label: "Yespower R16" },
];

let copyBound = false;
let addressListenerBound = false;

function payoutAddress() {
  const el = document.getElementById("miner-address");
  const raw = (el?.value || "").trim();
  return raw || "YOUR_STONE_ADDRESS";
}

function workerName(address, suffix = "rig1") {
  const base = address || "YOUR_STONE_ADDRESS";
  return `${base}.${suffix}`;
}

async function copyText(text, btn) {
  const value = String(text || "").trim();
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    if (btn) {
      const prev = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(() => {
        btn.textContent = prev;
      }, 1200);
    }
  } catch (_) {
    window.prompt("Copy:", value);
  }
}

function bindCopyButtons(root = document) {
  if (copyBound) return;
  copyBound = true;
  root.querySelectorAll("[data-setup-copy]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-setup-copy");
      const el = targetId ? document.getElementById(targetId) : null;
      void copyText(el?.textContent || "", btn);
    });
  });
}

function setField(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value != null && value !== "" ? String(value) : "—";
}

function setCopyTarget(btnId, fieldId) {
  const btn = document.getElementById(btnId);
  if (btn) btn.setAttribute("data-setup-copy", fieldId);
}

export function updatePoolStratumSetup(address = payoutAddress()) {
  const { hosts, ports } = stratumEndpoints();
  const worker = workerName(address);

  POOL_ALGOS.forEach((algo) => {
    const host = hosts[algo.id] || hosts.neoscrypt;
    const port = ports[algo.id] ?? ports.neoscrypt;
    setField(`pool-host-${algo.id}`, host);
    setField(`pool-port-${algo.id}`, String(port));
    setField(`pool-worker-${algo.id}`, worker);
    setCopyTarget(`btn-copy-pool-host-${algo.id}`, `pool-host-${algo.id}`);
    setCopyTarget(`btn-copy-pool-port-${algo.id}`, `pool-port-${algo.id}`);
    setCopyTarget(`btn-copy-pool-worker-${algo.id}`, `pool-worker-${algo.id}`);
  });
}

export function updateLanStratumSetup(info, address = payoutAddress()) {
  const worker = workerName(address, "lan1");
  const details = document.getElementById("lan-setup-details");
  const statusEl = document.getElementById("lan-setup-status");

  if (!info) {
    setField("lan-host-neoscrypt", "—");
    setField("lan-port-neoscrypt", "—");
    setField("lan-host-yespower", "—");
    setField("lan-port-yespower", "—");
    setField("lan-rpc-url", "—");
    setField("lan-rpc-port", "—");
    setField("lan-rpc-user", "—");
    setField("lan-rpc-password", "—");
    setField("lan-p2p-port", "—");
    setField("lan-worker", worker);
    if (statusEl) statusEl.textContent = "Connect to Wi‑Fi and start the local node.";
    if (details) details.open = false;
    return;
  }

  const host = info.lanIp || info.host || "Wi‑Fi required";
  const portsOpen = Boolean(info.portsOpen);
  const neoPort = info.neoscryptPort ?? 3437;
  const ypPort = info.yespowerPort ?? 3438;
  const rpcPort = info.rpcPort ?? 18340;
  const p2pPort = info.p2pPort ?? 17333;

  setField("lan-host-neoscrypt", host);
  setField("lan-port-neoscrypt", portsOpen ? String(neoPort) : `${neoPort} (closed)`);
  setField("lan-host-yespower", host);
  setField("lan-port-yespower", portsOpen ? String(ypPort) : `${ypPort} (closed)`);
  setField("lan-rpc-url", info.rpcUrl || (portsOpen && host !== "Wi‑Fi required" ? `http://${host}:${rpcPort}/` : "—"));
  setField("lan-rpc-port", portsOpen ? String(rpcPort) : `${rpcPort} (closed)`);
  setField("lan-rpc-user", info.rpcUser || "—");
  setField("lan-rpc-password", info.rpcPassword || (info.role === "lan-client" ? "on host device" : "—"));
  setField("lan-p2p-port", String(p2pPort));
  setField("lan-worker", worker);

  setCopyTarget("btn-copy-lan-host-neoscrypt", "lan-host-neoscrypt");
  setCopyTarget("btn-copy-lan-port-neoscrypt", "lan-port-neoscrypt");
  setCopyTarget("btn-copy-lan-host-yespower", "lan-host-yespower");
  setCopyTarget("btn-copy-lan-port-yespower", "lan-port-yespower");
  setCopyTarget("btn-copy-lan-rpc-url", "lan-rpc-url");
  setCopyTarget("btn-copy-lan-rpc-port", "lan-rpc-port");
  setCopyTarget("btn-copy-lan-rpc-user", "lan-rpc-user");
  setCopyTarget("btn-copy-lan-rpc-password", "lan-rpc-password");
  setCopyTarget("btn-copy-lan-p2p-port", "lan-p2p-port");
  setCopyTarget("btn-copy-lan-worker", "lan-worker");

  if (statusEl) {
    if (!info.lanIp) {
      statusEl.textContent = "Connect to Wi‑Fi to get a LAN IP for other miners on your network.";
    } else if (portsOpen) {
      statusEl.textContent =
        `Stratum listening on ${host}. Other devices on your Wi‑Fi can use these host/port values.`;
    } else if (info.batteryDormant) {
      statusEl.textContent =
        "Local node is in battery-save mode. Tap Start mining to open stratum ports.";
    } else {
      statusEl.textContent =
        `Tap Start mining to open ports :${neoPort} (neoscrypt) and :${ypPort} (yespower) on ${host}.`;
    }
  }
  if (details && info.lanIp) details.open = true;
}

export async function refreshMiningSetupInstructions() {
  if (!isCapacitorAndroid()) return;
  const address = payoutAddress();
  updatePoolStratumSetup(address);
  const lanInfo = await fetchDeviceNetworkInfo();
  updateLanStratumSetup(lanInfo, address);
}

export function initMiningSetupInstructions() {
  if (!isAndroidAppContext()) return;

  const panel = document.getElementById("mining-setup-panel");
  if (panel) panel.hidden = false;

  bindCopyButtons();

  if (!addressListenerBound) {
    addressListenerBound = true;
    document.getElementById("miner-address")?.addEventListener("input", () => {
      updatePoolStratumSetup();
      void fetchDeviceNetworkInfo().then((info) => updateLanStratumSetup(info));
    });
    document.getElementById("miner-address")?.addEventListener("change", () => {
      updatePoolStratumSetup();
      void fetchDeviceNetworkInfo().then((info) => updateLanStratumSetup(info));
    });
  }

  void refreshMiningSetupInstructions();
  setInterval(() => void refreshMiningSetupInstructions(), 12000);
}
/** Android LAN IP, RPC, and stratum ports for mining through this phone or a LAN peer. */

import {
  getLocalNodeStatus,
  getActiveLanPeer,
  isLanClientMode,
  listDiscoveredLanPeers,
} from "./local-node.js";
import { isCapacitorAndroid } from "./device-fleet.js";
import { isAndroidAppContext, whenCapacitorReady } from "./capacitor-ready.js";
import { stratumEndpoints } from "./stratum-transport.js";

const DEFAULT_STRATUM_PORTS = {
  neoscrypt: 3437,
  yespower: 3438,
};

const DEFAULT_RPC_PORT = 18340;
const P2P_PORT = 17333;

const REFRESH_MS = 12000;

let refreshTimer = null;
let copyHandlersBound = false;

function chainMeshPlugin() {
  try {
    return window.Capacitor?.Plugins?.BloodstoneChainMesh || null;
  } catch (_) {
    return null;
  }
}

async function resolveLanIp(nodeStatus) {
  const fromNode = String(nodeStatus?.lanIp || "").trim();
  if (fromNode) return fromNode;

  const mesh = chainMeshPlugin();
  if (!mesh?.getChunkServerStatus) return "";
  try {
    const status = await mesh.getChunkServerStatus();
    return String(status?.lanIp || "").trim();
  } catch (_) {
    return "";
  }
}

function stratumEndpoint(ip, port) {
  return `stratum+tcp://${ip}:${port}`;
}

function stratumPortsFromStatus(nodeStatus) {
  const ports = nodeStatus?.stratumPorts || {};
  return {
    neoscrypt: Number(
      ports.neoscrypt || nodeStatus?.stratumPort || DEFAULT_STRATUM_PORTS.neoscrypt,
    ),
    yespower: Number(
      ports.yespower ||
        nodeStatus?.stratumPortYespower ||
        DEFAULT_STRATUM_PORTS.yespower,
    ),
  };
}

function peerHost(peer) {
  return String(peer?.displayHost || peer?.host || peer?.lan_ip || "").trim();
}

function peerStratumNeo(peer, fallback) {
  return Number(peer?.port || peer?.stratum_port || fallback);
}

function peerStratumYespower(peer, fallback) {
  return Number(peer?.stratum_port_yespower || peer?.stratumPortYespower || fallback);
}

async function resolveLanClientEndpoints(nodeStatus) {
  const { neoscrypt, yespower } = stratumPortsFromStatus(nodeStatus);
  const active = getActiveLanPeer();
  if (active?.displayHost || active?.host) {
    const host = peerHost(active);
    const rpcPort = Number(active.rpc_port || active.rpcPort || DEFAULT_RPC_PORT);
    return {
      role: "lan-client",
      host,
      lanIp: host,
      rpcUrl: host ? `http://${host}:${rpcPort}/` : "",
      rpcPort,
      rpcUser: String(active.rpc_user || active.rpcUser || "").trim(),
      rpcPassword: "",
      neoscryptPort: Number(active.port || active.stratum_port || neoscrypt),
      yespowerPort: Number(active.stratum_port_yespower || yespower),
      neoscryptEndpoint: host ? stratumEndpoint(host, Number(active.port || neoscrypt)) : "",
      yespowerEndpoint: host
        ? stratumEndpoint(host, Number(active.stratum_port_yespower || yespower))
        : "",
      p2pPort: P2P_PORT,
      portsOpen: Boolean(host),
      nodeRunning: false,
      batteryDormant: Boolean(nodeStatus.batteryDormant),
      mode: active.mode || "full",
      peerSource: active.source || "lan-peer",
    };
  }

  const peers = await listDiscoveredLanPeers({ fullOnly: true });
  const peer = peers[0];
  if (!peer) {
    return {
      role: "lan-client",
      host: "",
      lanIp: "",
      rpcUrl: "",
      rpcPort: DEFAULT_RPC_PORT,
      rpcUser: "",
      rpcPassword: "",
      neoscryptPort: neoscrypt,
      yespowerPort: yespower,
      neoscryptEndpoint: "",
      yespowerEndpoint: "",
      p2pPort: P2P_PORT,
      portsOpen: false,
      nodeRunning: false,
      batteryDormant: Boolean(nodeStatus.batteryDormant),
      mode: "lan-client",
      peerSource: "",
    };
  }

  const host = peerHost(peer);
  const rpcPort = Number(peer.rpc_port || DEFAULT_RPC_PORT);
  const neoPort = peerStratumNeo(peer, neoscrypt);
  const ypPort = peerStratumYespower(peer, yespower);
  return {
    role: "lan-client",
    host,
    lanIp: host,
    rpcUrl: host ? `http://${host}:${rpcPort}/` : "",
    rpcPort,
    rpcUser: String(peer.rpc_user || "").trim(),
    rpcPassword: "",
    neoscryptPort: neoPort,
    yespowerPort: ypPort,
    neoscryptEndpoint: host ? stratumEndpoint(host, neoPort) : "",
    yespowerEndpoint: host ? stratumEndpoint(host, ypPort) : "",
    p2pPort: P2P_PORT,
    portsOpen: Boolean(host),
    nodeRunning: false,
    batteryDormant: Boolean(nodeStatus.batteryDormant),
    mode: peer.mode || "full",
    peerSource: peer.source || "lan-peer",
  };
}

function vpsMineTargets() {
  const { hosts, ports } = stratumEndpoints();
  return {
    neoscrypt: `${hosts.neoscrypt}:${ports.neoscrypt}`,
    yespower: `${hosts.yespower}:${ports.yespower}`,
    sha256d: `${hosts.sha256d || hosts.neoscrypt}:${ports.sha256d}`,
  };
}

export function updateMineTargetsPanel(info) {
  const panel = document.getElementById("mine-targets-panel");
  if (!panel || !isAndroidAppContext()) return;
  panel.hidden = false;
  const vps = vpsMineTargets();
  const neoHost = info?.host || info?.lanIp || "";
  const lanNeo =
    info?.portsOpen && neoHost
      ? `${neoHost}:${info.neoscryptPort ?? DEFAULT_STRATUM_PORTS.neoscrypt}`
      : info?.lanIp
        ? `${info.lanIp}:${info.neoscryptPort ?? DEFAULT_STRATUM_PORTS.neoscrypt} (starting…)`
        : "Start node on Wi‑Fi";
  const lanYp =
    info?.portsOpen && neoHost
      ? `${neoHost}:${info.yespowerPort ?? DEFAULT_STRATUM_PORTS.yespower}`
      : info?.lanIp
        ? `${info.lanIp}:${info.yespowerPort ?? DEFAULT_STRATUM_PORTS.yespower} (starting…)`
        : "—";

  const set = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };
  set("mine-target-vps-neo", vps.neoscrypt);
  set("mine-target-vps-yp", vps.yespower);
  set("mine-target-lan-neo", info?.role === "lan-client" && info.lanIp
    ? `${info.lanIp}:${info.neoscryptPort}`
    : lanNeo);
  set("mine-target-lan-yp", info?.role === "lan-client" && info.lanIp
    ? `${info.lanIp}:${info.yespowerPort}`
    : lanYp);

  const targets = [
    ["mine-target-vps-neo", "btn-copy-mine-target-vps-neo"],
    ["mine-target-vps-yp", "btn-copy-mine-target-vps-yp"],
    ["mine-target-lan-neo", "btn-copy-mine-target-lan-neo"],
    ["mine-target-lan-yp", "btn-copy-mine-target-lan-yp"],
  ];
  targets.forEach(([fieldId, btnId]) => {
    const btn = document.getElementById(btnId);
    const el = document.getElementById(fieldId);
    if (btn && el) {
      const text = el.textContent?.trim() || "";
      const copyable =
        text && !text.startsWith("—") && !text.includes("Start node") && !text.includes("starting");
      btn.setAttribute("data-lan-copy", copyable ? text : "");
      btn.disabled = !copyable;
    }
  });
}

export async function fetchDeviceNetworkInfo() {
  if (!isAndroidAppContext()) return null;
  await whenCapacitorReady(12000);
  if (!isCapacitorAndroid()) return null;

  const nodeStatus = (await getLocalNodeStatus()) || {};
  if (isLanClientMode(nodeStatus.mode || "")) {
    return resolveLanClientEndpoints(nodeStatus);
  }

  const lanIp = await resolveLanIp(nodeStatus);
  const { neoscrypt, yespower } = stratumPortsFromStatus(nodeStatus);
  const nodeRunning = Boolean(nodeStatus.running);
  const portsOpen = nodeRunning;
  const host = lanIp || (nodeRunning ? "127.0.0.1" : "");
  const rpcPort = Number(nodeStatus.rpcPort || DEFAULT_RPC_PORT);
  const rpcUrl =
    String(nodeStatus.rpcUrl || "").trim() ||
    (host && nodeRunning ? `http://${host}:${rpcPort}/` : "");

  return {
    role: "host",
    host,
    lanIp,
    rpcUrl,
    rpcPort,
    rpcUser: String(nodeStatus.rpcUser || "").trim(),
    rpcPassword: String(nodeStatus.rpcPassword || "").trim(),
    neoscryptPort: neoscrypt,
    yespowerPort: yespower,
    neoscryptEndpoint: portsOpen && host ? stratumEndpoint(host, neoscrypt) : "",
    yespowerEndpoint: portsOpen && host ? stratumEndpoint(host, yespower) : "",
    p2pPort: P2P_PORT,
    portsOpen,
    nodeRunning,
    batteryDormant: Boolean(nodeStatus.batteryDormant),
    mode: nodeStatus.mode || "",
    peerSource: "local-node",
  };
}

function bindCopyButtons() {
  if (copyHandlersBound) return;
  copyHandlersBound = true;
  document.querySelectorAll("[data-lan-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const text = (btn.getAttribute("data-lan-copy") || "").trim();
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        const prev = btn.textContent;
        btn.textContent = "Copied!";
        setTimeout(() => {
          btn.textContent = prev;
        }, 1200);
      } catch (_) {
        window.prompt("Copy:", text);
      }
    });
  });
}

function setCopyButton(id, value) {
  const btn = document.getElementById(id);
  if (!btn) return;
  const text = String(value || "").trim();
  btn.setAttribute("data-lan-copy", text);
  btn.disabled = !text;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  const text = value != null && value !== "" ? String(value) : "—";
  el.textContent = text;
}

export function updateDeviceNetworkPanel(info) {
  updateMineTargetsPanel(info);
  const panel = document.getElementById("device-lan-mining-panel");
  if (!panel) return;

  if (!isAndroidAppContext()) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;
  bindCopyButtons();
  if (!info) {
    setText("device-lan-ip", "Loading…");
    setText("device-lan-neoscrypt-endpoint", "—");
    setText("device-lan-yespower-endpoint", "—");
    if (document.getElementById("device-lan-port-status")) {
      document.getElementById("device-lan-port-status").textContent = "Waiting for node";
    }
    return;
  }

  const titleEl = document.getElementById("device-node-panel-title");
  const subtitleEl = document.getElementById("device-node-panel-subtitle");
  const hintEl = document.getElementById("device-lan-mining-hint");
  const statusEl = document.getElementById("device-lan-port-status");

  const hostLabel = info.role === "lan-client" ? "LAN full node IP" : "Phone LAN IP";
  setText("device-node-host-label", hostLabel);
  setText("device-lan-ip", info.lanIp || "Not on Wi‑Fi");
  setCopyButton("btn-copy-lan-ip", info.lanIp);

  setText("device-node-mode", info.mode || "—");
  setText("device-node-rpc-url", info.rpcUrl || (info.portsOpen ? "—" : "Node offline"));
  setCopyButton("btn-copy-node-rpc-url", info.rpcUrl);

  setText(
    "device-node-rpc-port",
    info.portsOpen || info.role === "lan-client" ? String(info.rpcPort || DEFAULT_RPC_PORT) : "—",
  );
  setCopyButton("btn-copy-node-rpc-port", info.portsOpen ? String(info.rpcPort) : "");

  setText("device-node-rpc-user", info.rpcUser || "—");
  setCopyButton("btn-copy-node-rpc-user", info.rpcUser);

  const rpcPass = info.rpcPassword || "";
  setText("device-node-rpc-password", rpcPass || (info.role === "lan-client" ? "on host device" : "—"));
  setCopyButton("btn-copy-node-rpc-password", rpcPass);

  const neoHost = info.host || info.lanIp || "";
  const neoDisplay = info.portsOpen && neoHost
    ? `${neoHost}:${info.neoscryptPort}`
    : info.lanIp
      ? `:${info.neoscryptPort} (closed)`
      : "—";
  const ypDisplay = info.portsOpen && neoHost
    ? `${neoHost}:${info.yespowerPort}`
    : info.lanIp
      ? `:${info.yespowerPort} (closed)`
      : "—";

  setText("device-lan-neoscrypt-endpoint", neoDisplay);
  setText("device-lan-yespower-endpoint", ypDisplay);
  setCopyButton("btn-copy-neoscrypt", info.neoscryptEndpoint);
  setCopyButton("btn-copy-yespower", info.yespowerEndpoint);

  setText("device-node-p2p-port", String(info.p2pPort || P2P_PORT));
  setCopyButton("btn-copy-node-p2p-port", String(info.p2pPort || P2P_PORT));

  if (titleEl) {
    titleEl.textContent =
      info.role === "lan-client"
        ? "Android node — mine via LAN full node"
        : "Android node — mine to this phone";
  }

  if (statusEl) {
    if (info.role === "lan-client") {
      statusEl.textContent = info.lanIp ? "LAN peer found" : "Searching LAN";
      statusEl.dataset.state = info.lanIp ? "open" : "closed";
    } else {
      statusEl.textContent = info.portsOpen ? "Node running" : "Node offline";
      statusEl.dataset.state = info.portsOpen ? "open" : "closed";
    }
  }

  if (subtitleEl) {
    if (info.role === "lan-client") {
      subtitleEl.textContent = info.lanIp
        ? "This phone mines through a household full node on Wi‑Fi. Point other miners at the same host/ports below."
        : "LAN client mode — searching mDNS and the pool registry for a synced full node on your Wi‑Fi.";
    } else {
      subtitleEl.textContent =
        "Other devices on your Wi‑Fi can mine to this phone using the RPC and stratum ports below.";
    }
  }

  if (hintEl) {
    if (info.role === "lan-client") {
      if (!info.lanIp) {
        hintEl.textContent =
          "No LAN full node found yet. Run Full chain mode on one plugged-in phone on the same Wi‑Fi.";
      } else {
        hintEl.textContent =
          `RPC ${info.rpcUrl || "—"} · stratum neoscrypt :${info.neoscryptPort} · yespower :${info.yespowerPort} · chain P2P :${info.p2pPort}. Worker = YOUR_STONE_ADDRESS.rig1 · password x.`;
      }
    } else if (!info.lanIp) {
      hintEl.textContent =
        "Connect to Wi‑Fi to expose LAN endpoints. RPC stays on 127.0.0.1 until a LAN IP is available.";
    } else if (info.portsOpen) {
      hintEl.textContent =
        `Node active on ${info.lanIp}. RPC :${info.rpcPort} · stratum :${info.neoscryptPort}/:${info.yespowerPort} · P2P :${info.p2pPort}.`;
    } else if (info.batteryDormant) {
      hintEl.textContent =
        "Local node is in battery-save mode. Tap Start full node above to open RPC/stratum.";
    } else {
      hintEl.textContent =
        `Tap Start full node above to open RPC :${info.rpcPort} and stratum :${info.neoscryptPort} / :${info.yespowerPort} on ${info.lanIp || "this device"}.`;
    }
  }
}

export async function refreshDeviceNetworkPanel() {
  if (!isAndroidAppContext()) return null;
  updateMineTargetsPanel(null);
  const info = await fetchDeviceNetworkInfo();
  updateDeviceNetworkPanel(info);
  return info;
}

export function initDeviceNetworkPanel() {
  if (!isAndroidAppContext()) return;
  updateMineTargetsPanel(null);
  updateDeviceNetworkPanel(null);
  void refreshDeviceNetworkPanel();
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(() => void refreshDeviceNetworkPanel(), REFRESH_MS);
}
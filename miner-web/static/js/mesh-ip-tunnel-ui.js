/**
 * BSM4 Internet Tunnel UI — ping/DNS over mesh via mesh-gateway egress.
 */

import {
  buildHttpGetRequest,
  buildHttpsGetRequest,
  buildIcmpEchoRequest,
  buildTlsClientHelloPacket,
  fetchIpTunnelProtocol,
  formatIpv4Summary,
  openIpTunnelChannel,
  pollIpTunnelInbox,
  sendIpDatagram,
  summarizeTlsPayload,
} from "./mesh-ip-tunnel.js";
import { resolveDeviceId } from "./chain-mesh.js";
import { apiUrl } from "./miner-paths.js";
import { runMeshTlsHandshake } from "./mesh-ip-tunnel-handshake.js";
import { resolveMeshGatewayRecipient, COORDINATOR_FALLBACK } from "./mesh-internet-gateway.js";

const GATEWAY_RECIPIENT = COORDINATOR_FALLBACK;
const DEFAULT_VIRTUAL_IP = "10.73.0.42";

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function appendLog(el, line, kind = "") {
  if (!el) return;
  const row = document.createElement("div");
  row.className = `mesh-packet-log-line${kind ? ` ${kind}` : ""}`;
  row.innerHTML = line;
  el.appendChild(row);
  el.scrollTop = el.scrollHeight;
}

export function initMeshIpTunnel(root = document) {
  const openBtn = root.getElementById("mesh-ip-open-btn");
  const pingBtn = root.getElementById("mesh-ip-ping-btn");
  const httpBtn = root.getElementById("mesh-ip-http-btn");
  const httpsBtn = root.getElementById("mesh-ip-https-btn");
  const tlsBtn = root.getElementById("mesh-ip-tls-btn");
  const handshakeBtn = root.getElementById("mesh-ip-handshake-btn");
  const handshakeLabBtn = root.getElementById("mesh-ip-handshake-lab-btn");
  const handshakeProdBtn = root.getElementById("mesh-ip-handshake-prod-btn");
  const httpPortInput = root.getElementById("mesh-ip-http-port");
  const listenBtn = root.getElementById("mesh-ip-listen-btn");
  const senderInput = root.getElementById("mesh-ip-sender");
  const virtualIpInput = root.getElementById("mesh-ip-virtual");
  const pingTargetInput = root.getElementById("mesh-ip-ping-target");
  const httpHostInput = root.getElementById("mesh-ip-http-host");
  const httpDstInput = root.getElementById("mesh-ip-http-dst");
  const httpPathInput = root.getElementById("mesh-ip-http-path");
  const channelInput = root.getElementById("mesh-ip-channel");
  const logEl = root.getElementById("mesh-ip-log");
  const statusEl = root.getElementById("mesh-ip-status");
  const gatewayEl = root.getElementById("mesh-ip-gateway-status");

  let listening = false;
  let pollTimer = null;
  let lastSeq = 0;
  let localSender = "";

  const setStatus = (text, kind = "") => {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.className = `muted small mesh-upload-status${kind ? ` ${kind}` : ""}`;
  };

  const inboxRecipient = async () => {
    const sender = senderInput?.value?.trim() || localSender;
    if (sender) return sender;
    const id = await resolveDeviceId();
    if (senderInput) senderInput.value = id;
    localSender = id;
    return id;
  };

  const tlsHintFromPacket = (pkt) => {
    try {
      const b64 = pkt.payload_b64;
      if (!b64) return "";
      const raw = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      if (raw.length < 40) return "";
      const tcpPayload = raw.subarray(40);
      const hint = summarizeTlsPayload(tcpPayload);
      return hint ? ` · ${hint}` : "";
    } catch {
      return "";
    }
  };

  const renderIpv4Packet = (pkt, direction = "rx") => {
    const ipv4 = pkt.ipv4;
    let summary = formatIpv4Summary(ipv4) || pkt.ip_packet_hex?.slice(0, 40) || "?";
    summary += tlsHintFromPacket(pkt);
    appendLog(
      logEl,
      `<span class="muted">[${direction} ${pkt.seq}]</span> ` +
        `<span class="mono">${escapeHtml(summary)}</span>`,
      direction === "tx" ? "tx" : "rx",
    );
  };

  const refreshGatewayStatus = async () => {
    if (!gatewayEl) return;
    try {
      const res = await fetch(apiUrl("/api/chain-mesh/tunnel/ip/gateway/status"), {
        cache: "no-store",
      });
      const data = await res.json();
      if (!data?.ok) {
        gatewayEl.textContent = "Gateway status unavailable";
        return;
      }
      const elected = data.elected || {};
      const src = elected.source === "peer" ? "household peer" : "coordinator";
      gatewayEl.textContent =
        `Gateway ${elected.recipient || data.recipient} (${src}) · virtual ${data.virtual_ip} · ` +
        `${data.enabled ? "enabled" : "disabled"} · ` +
        `pending ${data.pending_count} · candidates ${(data.candidates || []).length}`;
    } catch {
      gatewayEl.textContent = "Gateway status unavailable";
    }
  };

  void refreshGatewayStatus();
  window.setInterval(() => void refreshGatewayStatus(), 15000);

  openBtn?.addEventListener("click", async () => {
    let sender = senderInput?.value?.trim() || "";
    if (!sender) {
      sender = await resolveDeviceId();
      if (senderInput) senderInput.value = sender;
    }
    const virtualIp = virtualIpInput?.value?.trim() || DEFAULT_VIRTUAL_IP;
    openBtn.disabled = true;
    setStatus("Resolving household internet gateway…");
    try {
      const gw = await resolveMeshGatewayRecipient({ deviceId: sender });
      const ch = await openIpTunnelChannel({
        sender,
        recipient: gw,
        label: "bsm4-internet",
        virtual_subnet: "10.73.0.0/16",
        virtual_ip: virtualIp,
        anchor: false,
      });
      if (channelInput) channelInput.value = ch.channel_id || "";
      localSender = sender;
      setStatus(`Tunnel open → ${gw}`, "ok");
      appendLog(
        logEl,
        `<span class="muted">[open]</span> BSM4 channel to <span class="mono">${escapeHtml(gw)}</span>`,
      );
      void refreshGatewayStatus();
    } catch (err) {
      setStatus(err.message || String(err), "error");
    } finally {
      openBtn.disabled = false;
    }
  });

  const sendWebGet = async ({ tls = false, btn } = {}) => {
    const channelId = channelInput?.value?.trim() || "";
    const sender = senderInput?.value?.trim() || localSender;
    const virtualIp = virtualIpInput?.value?.trim() || DEFAULT_VIRTUAL_IP;
    const host = httpHostInput?.value?.trim() || (tls ? "example.com" : "example.com");
    const dstIp = httpDstInput?.value?.trim() || (tls ? "93.184.216.34" : "93.184.216.34");
    const path = httpPathInput?.value?.trim() || "/";
    const dstPort = tls ? 443 : 80;
    if (!channelId) {
      setStatus("Open a tunnel channel first.", "error");
      return;
    }
    if (btn) btn.disabled = true;
    setStatus(`${tls ? "HTTPS" : "HTTP"} GET ${host}${path} over mesh…`);
    try {
      const build = tls ? buildHttpsGetRequest : buildHttpGetRequest;
      const ipPacket = build(virtualIp, host, path, { dstIp });
      const result = await sendIpDatagram({
        channelId,
        sender,
        recipient: GATEWAY_RECIPIENT,
        ipPacket,
      });
      const pkt = result.packet || {};
      lastSeq = Math.max(lastSeq, Number(pkt.seq) || 0);
      renderIpv4Packet(
        {
          seq: pkt.seq,
          ipv4: result.ipv4 || {
            src: virtualIp,
            dst: dstIp,
            protocol_name: "tcp",
            dst_port: dstPort,
          },
        },
        "tx",
      );
      setStatus(`${tls ? "HTTPS" : "HTTP"} GET sent via gateway for ${host}`, "ok");
      void refreshGatewayStatus();
    } catch (err) {
      setStatus(err.message || String(err), "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  httpsBtn?.addEventListener("click", () => void sendWebGet({ tls: true, btn: httpsBtn }));

  const applyTlsPreset = (preset) => {
    if (preset === "lab") {
      if (httpHostInput) httpHostInput.value = "bloodstone-tls-lab";
      if (httpDstInput) httpDstInput.value = "127.0.0.1";
      if (httpPortInput) httpPortInput.value = "18443";
    } else if (preset === "prod") {
      if (httpHostInput) httpHostInput.value = "bloodstonewallet.mytunnel.org";
      if (httpDstInput) httpDstInput.value = "64.188.22.190";
      if (httpPortInput) httpPortInput.value = "443";
    }
  };

  handshakeLabBtn?.addEventListener("click", () => {
    applyTlsPreset("lab");
    setStatus("Lab preset loaded (bloodstone-tls-lab → 127.0.0.1:18443).", "ok");
  });

  handshakeProdBtn?.addEventListener("click", () => {
    applyTlsPreset("prod");
    setStatus("Production preset loaded (bloodstonewallet.mytunnel.org → 64.188.22.190:443).", "ok");
  });

  handshakeBtn?.addEventListener("click", async () => {
    const channelId = channelInput?.value?.trim() || "";
    const sender = senderInput?.value?.trim() || localSender;
    const virtualIp = virtualIpInput?.value?.trim() || DEFAULT_VIRTUAL_IP;
    const host = httpHostInput?.value?.trim() || "bloodstone-tls-lab";
    const dstIp = httpDstInput?.value?.trim() || "127.0.0.1";
    const dstPort = Number(httpPortInput?.value || 18443);
    if (!channelId) {
      setStatus("Open a tunnel channel first.", "error");
      return;
    }
    handshakeBtn.disabled = true;
    setStatus("TLS handshake flight 1 (ClientHello → ServerHello)…");
    try {
      const result = await runMeshTlsHandshake({
        channelId,
        sender,
        virtualIp,
        dstIp,
        dstPort,
        host,
      });
      if (result.connectIp && httpDstInput) {
        httpDstInput.value = result.connectIp;
      }
      lastSeq = Math.max(lastSeq, 0);
      appendLog(
        logEl,
        `<span class="muted">[handshake]</span> ` +
          `<span class="mono">${escapeHtml(result.serverSummary || result.phase || "?")}</span> ` +
          `<span class="muted">(${result.serverFlightBytes || 0} B down)</span>`,
        result.ok ? "rx" : "error",
      );
      if (result.appPreview) {
        appendLog(
          logEl,
          `<span class="muted">[app]</span> <span class="mono">${escapeHtml(result.appPreview.slice(0, 240))}</span>`,
          "rx",
        );
      }
      setStatus(
        result.ok
          ? result.flights >= 3
            ? `TLS complete + app data · ${result.appDataBytes || 0} B encrypted · ${result.useBrowserCrypto ? "browser crypto" : "coordinator"}`
            : result.flights === 2
              ? `TLS handshake complete · ${result.serverFlightBytes} B total · flight2 ${result.clientFlight2Bytes || 0} B up`
              : `Server flight received · ${result.serverFlightBytes} bytes · ${result.serverSummary || ""}`
          : `Handshake stopped: ${result.phase} (${result.serverFlightBytes || 0} B)`,
        result.ok ? "ok" : "error",
      );
      void refreshGatewayStatus();
    } catch (err) {
      setStatus(err.message || String(err), "error");
    } finally {
      handshakeBtn.disabled = false;
    }
  });

  tlsBtn?.addEventListener("click", async () => {
    const channelId = channelInput?.value?.trim() || "";
    const sender = senderInput?.value?.trim() || localSender;
    const virtualIp = virtualIpInput?.value?.trim() || DEFAULT_VIRTUAL_IP;
    const host = httpHostInput?.value?.trim() || "bloodstonewallet.mytunnel.org";
    const dstIp = httpDstInput?.value?.trim() || "64.188.22.190";
    if (!channelId) {
      setStatus("Open a tunnel channel first.", "error");
      return;
    }
    tlsBtn.disabled = true;
    setStatus(`TLS ClientHello → ${host} over mesh…`);
    try {
      const ipPacket = buildTlsClientHelloPacket(virtualIp, dstIp, host, {
        srcPort: 44100 + (lastSeq % 500),
      });
      const result = await sendIpDatagram({
        channelId,
        sender,
        recipient: GATEWAY_RECIPIENT,
        ipPacket,
      });
      const pkt = result.packet || {};
      lastSeq = Math.max(lastSeq, Number(pkt.seq) || 0);
      const tlsHint = summarizeTlsPayload(ipPacket.subarray(40));
      renderIpv4Packet(
        {
          seq: pkt.seq,
          ipv4: result.ipv4 || {
            src: virtualIp,
            dst: dstIp,
            protocol_name: "tcp",
            dst_port: 443,
          },
          payload_b64: btoa(String.fromCharCode(...ipPacket)),
        },
        "tx",
      );
      setStatus(`TLS ClientHello sent (${tlsHint || "handshake"}) — listen for ServerHello`, "ok");
      void refreshGatewayStatus();
    } catch (err) {
      setStatus(err.message || String(err), "error");
    } finally {
      tlsBtn.disabled = false;
    }
  });

  httpBtn?.addEventListener("click", () => void sendWebGet({ tls: false, btn: httpBtn }));

  pingBtn?.addEventListener("click", async () => {
    const channelId = channelInput?.value?.trim() || "";
    const sender = senderInput?.value?.trim() || localSender;
    const virtualIp = virtualIpInput?.value?.trim() || DEFAULT_VIRTUAL_IP;
    const target = pingTargetInput?.value?.trim() || "8.8.8.8";
    if (!channelId) {
      setStatus("Open a tunnel channel first.", "error");
      return;
    }
    pingBtn.disabled = true;
    setStatus(`Pinging ${target} over mesh…`);
    try {
      const ipPacket = buildIcmpEchoRequest(virtualIp, target, {
        id: Math.floor(Math.random() * 0xffff),
        seq: lastSeq + 1,
      });
      const result = await sendIpDatagram({
        channelId,
        sender,
        recipient: GATEWAY_RECIPIENT,
        ipPacket,
      });
      const pkt = result.packet || {};
      lastSeq = Math.max(lastSeq, Number(pkt.seq) || 0);
      renderIpv4Packet(
        { seq: pkt.seq, ipv4: result.ipv4 || { src: virtualIp, dst: target, protocol_name: "icmp" } },
        "tx",
      );
      setStatus(`ICMP echo sent to gateway for ${target}`, "ok");
      void refreshGatewayStatus();
    } catch (err) {
      setStatus(err.message || String(err), "error");
    } finally {
      pingBtn.disabled = false;
    }
  });

  const pollInbox = async () => {
    const who = await inboxRecipient();
    const channelId = channelInput?.value?.trim() || "";
    const data = await pollIpTunnelInbox(who, { channelId, sinceSeq: lastSeq });
    for (const pkt of data.packets || []) {
      if (!pkt.ipv4 && pkt.payload_type !== "ipv4") continue;
      if (Number(pkt.seq) <= lastSeq) continue;
      lastSeq = Math.max(lastSeq, Number(pkt.seq) || 0);
      renderIpv4Packet(pkt, pkt.sender === GATEWAY_RECIPIENT ? "rx" : "tx");
    }
    if (listening) {
      setStatus(`Listening · last seq ${lastSeq}`, "ok");
    }
  };

  listenBtn?.addEventListener("click", async () => {
    listening = !listening;
    if (listening) {
      listenBtn.textContent = "Stop listening";
      setStatus("Polling IP tunnel inbox…");
      void pollInbox();
      pollTimer = window.setInterval(() => void pollInbox(), 3000);
    } else {
      listenBtn.textContent = "Listen for IP replies";
      setStatus("Stopped listening.");
      if (pollTimer) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
    }
  });
}
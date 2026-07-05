/**
 * BSM3 virtual LAN UI — SSE stream + LAN P2P inbox + browser decode.
 */

import {
  decodePacketPayload,
  openMeshPacketChannel,
  pollMeshPacketInbox,
  streamMeshPacketInbox,
} from "./mesh-packet.js";
import { fetchMeshPacketInboxHybrid } from "./mesh-packet-lan.js";
import { resolveDeviceId } from "./chain-mesh.js";

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

function renderPacket(logEl, pkt, direction = "rx") {
  const body = escapeHtml(decodePacketPayload(pkt));
  appendLog(
    logEl,
    `<span class="muted">[${direction} ${pkt.seq}] relay:${pkt.relay_count || 0}</span> ` +
      `<span class="mono">${escapeHtml(pkt.sender || "?")}</span>: ${body}`,
    direction === "tx" ? "tx" : "rx",
  );
}

export function initMeshPacketLan(root = document) {
  const openBtn = root.getElementById("mesh-packet-open-btn");
  const sendBtn = root.getElementById("mesh-packet-send-btn");
  const listenBtn = root.getElementById("mesh-packet-listen-btn");
  const senderInput = root.getElementById("mesh-packet-sender");
  const recipientInput = root.getElementById("mesh-packet-recipient");
  const channelInput = root.getElementById("mesh-packet-channel");
  const messageInput = root.getElementById("mesh-packet-message");
  const logEl = root.getElementById("mesh-packet-log");
  const statusEl = root.getElementById("mesh-packet-status");

  let listening = false;
  let closeStream = null;
  let lastSeq = 0;
  let localRecipient = "";

  const setStatus = (text, kind = "") => {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.className = `muted small mesh-upload-status${kind ? ` ${kind}` : ""}`;
  };

  const inboxRecipient = async () =>
    recipientInput?.value?.trim() || localRecipient || (await resolveDeviceId());

  const handlePacket = (pkt) => {
    if (!pkt || Number(pkt.seq) <= lastSeq) return;
    lastSeq = Math.max(lastSeq, Number(pkt.seq) || 0);
    renderPacket(logEl, pkt, "rx");
  };

  openBtn?.addEventListener("click", async () => {
    const sender = senderInput?.value?.trim() || "";
    let recipient = recipientInput?.value?.trim() || "";
    if (!sender) {
      setStatus("Enter your STONE address or device id as sender.", "error");
      return;
    }
    if (!recipient) {
      recipient = await resolveDeviceId();
      if (recipientInput) recipientInput.value = recipient;
    }
    openBtn.disabled = true;
    setStatus("Opening virtual LAN channel…");
    try {
      const ch = await openMeshPacketChannel({
        sender,
        recipient,
        label: "browser-lan",
        anchor: false,
      });
      if (channelInput) channelInput.value = ch.channel_id || "";
      localRecipient = recipient;
      setStatus(`Channel open · ${(ch.channel_id || "").slice(0, 16)}…`, "ok");
      appendLog(
        logEl,
        `<span class="muted">[open]</span> channel to <span class="mono">${escapeHtml(recipient)}</span>`,
      );
    } catch (err) {
      setStatus(err.message || String(err), "error");
    } finally {
      openBtn.disabled = false;
    }
  });

  sendBtn?.addEventListener("click", async () => {
    const channelId = channelInput?.value?.trim() || "";
    const sender = senderInput?.value?.trim() || "";
    const recipient = recipientInput?.value?.trim() || "";
    const text = messageInput?.value || "";
    if (!channelId || !text) {
      setStatus("Open a channel and enter a message.", "error");
      return;
    }
    sendBtn.disabled = true;
    try {
      const { sendMeshPacket } = await import("./mesh-packet.js");
      const result = await sendMeshPacket({
        channelId,
        sender,
        recipient,
        payload: text,
        payloadType: "text",
      });
      const pkt = result.packet || {};
      lastSeq = Math.max(lastSeq, Number(pkt.seq) || 0);
      if (messageInput) messageInput.value = "";
      renderPacket(logEl, { ...pkt, payload_text: text }, "tx");
      setStatus(`Sent packet #${pkt.seq}`, "ok");
    } catch (err) {
      setStatus(err.message || String(err), "error");
    } finally {
      sendBtn.disabled = false;
    }
  });

  async function hybridPoll() {
    const who = await inboxRecipient();
    const channelId = channelInput?.value?.trim() || "";
    const data = await fetchMeshPacketInboxHybrid(who, {
      channelId,
      sinceSeq: lastSeq,
      coordinatorFetch: () => pollMeshPacketInbox(who, { channelId, sinceSeq: lastSeq }),
    });
    for (const pkt of data.packets || []) handlePacket(pkt);
    if (data.sources) {
      setStatus(
        `Listening · local ${data.sources.local} · LAN peers ${data.sources.peers}`,
        "ok",
      );
    }
  }

  listenBtn?.addEventListener("click", async () => {
    listening = !listening;
    if (listening) {
      listenBtn.textContent = "Stop listening";
      setStatus("Connecting SSE + LAN peers…");
      const who = await inboxRecipient();
      closeStream = streamMeshPacketInbox(who, {
        onPacket: handlePacket,
        onError: () => {
          void hybridPoll();
        },
      });
      void hybridPoll();
      window.meshPacketPollTimer = window.setInterval(() => {
        void hybridPoll();
      }, 12000);
    } else {
      listenBtn.textContent = "Listen for packets";
      setStatus("Stopped listening.");
      if (closeStream) closeStream();
      closeStream = null;
      if (window.meshPacketPollTimer) {
        window.clearInterval(window.meshPacketPollTimer);
        window.meshPacketPollTimer = null;
      }
    }
  });

  messageInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendBtn?.click();
    }
  });
}
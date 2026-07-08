/**
 * Bloodstone Network Chat UI — retro buddy list + lobby + DMs over BSM3.
 */

import { resolveDeviceId } from "./chain-mesh.js";
import { fleetDeviceModel } from "./device-fleet.js";
import { isDesktopAppContext } from "./capacitor-ready.js";
import {
  decodePacketPayload,
  pollMeshPacketInbox,
  sendMeshPacket,
  streamMeshPacketInbox,
} from "./mesh-packet.js";
import { fetchMeshPacketInboxHybrid } from "./mesh-packet-lan.js";
import {
  LOBBY_ROOM_ID,
  fetchChatPresence,
  fetchLobbyInbox,
  heartbeatChatPresence,
  openDmChannel,
  sendLobbyMessage,
} from "./network-chat.js";

const STORAGE_NICK = "bloodstone-network-chat-nick";
const STORAGE_STATUS = "bloodstone-network-chat-status";

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function formatTime(ts) {
  const n = Number(ts);
  if (!n) return "";
  const d = new Date(n * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function shortId(id) {
  const s = String(id || "");
  if (s.length <= 14) return s;
  return `${s.slice(0, 6)}…${s.slice(-4)}`;
}

export function initNetworkChat(root = document) {
  const nickInput = root.getElementById("nc-nick");
  const statusInput = root.getElementById("nc-status-msg");
  const buddyList = root.getElementById("nc-buddy-list");
  const chatHead = root.getElementById("nc-chat-head");
  const messagesEl = root.getElementById("nc-messages");
  const composeEl = root.getElementById("nc-compose");
  const sendBtn = root.getElementById("nc-send");
  const statusBar = root.getElementById("nc-statusbar");
  const countsEl = root.getElementById("nc-online-counts");

  let selfId = "";
  let selfNick = "";
  let activeTarget = { kind: "lobby", id: LOBBY_ROOM_ID, label: "Network Lobby" };
  let dmChannels = new Map();
  let lobbyLastSeq = 0;
  let dmLastSeq = new Map();
  let closeLobbyStream = null;
  let closeDmStream = null;
  let presenceTimer = null;
  let pollTimer = null;

  const setStatus = (text, kind = "") => {
    if (!statusBar) return;
    statusBar.textContent = text;
    statusBar.className = `nc-statusbar${kind ? ` ${kind}` : ""}`;
  };

  const appendMessage = ({
    nick,
    text,
    ts,
    system = false,
    self = false,
  }) => {
    if (!messagesEl) return;
    const row = document.createElement("div");
    row.className = `nc-msg${system ? " system" : ""}${self ? " self" : ""}`;
    const time = formatTime(ts);
    if (system) {
      row.innerHTML = `<span class="nc-nick">*</span> ${escapeHtml(text)}`;
    } else {
      row.innerHTML =
        `<span class="nc-time">${escapeHtml(time)}</span>` +
        `<span class="nc-nick">${escapeHtml(nick || "?")}:</span> ` +
        escapeHtml(text);
    }
    messagesEl.appendChild(row);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  };

  const clearMessages = () => {
    if (messagesEl) messagesEl.innerHTML = "";
  };

  const renderBuddy = (buddy, { lobby = false } = {}) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `nc-buddy${lobby ? " lobby" : ""}`;
    btn.dataset.id = buddy.device_id || LOBBY_ROOM_ID;
    btn.dataset.kind = lobby ? "lobby" : "dm";
    const status = lobby ? "online" : buddy.status || "offline";
    if (
      activeTarget.kind === btn.dataset.kind &&
      activeTarget.id === btn.dataset.id
    ) {
      btn.classList.add("active");
    }
    const name = lobby ? "Network Lobby" : buddy.display_name || shortId(buddy.device_id);
    const sub = lobby
      ? "Everyone on the mesh"
      : buddy.status_message || buddy.model || buddy.peer_kind || "";
    btn.innerHTML =
      `<span class="nc-dot ${escapeHtml(status)}"></span>` +
      `<span class="nc-buddy-meta">` +
      `<div class="nc-name">${escapeHtml(name)}</div>` +
      `<div class="nc-sub">${escapeHtml(sub)}</div>` +
      `</span>`;
    btn.addEventListener("click", () => selectTarget(btn.dataset.kind, btn.dataset.id, name));
    return btn;
  };

  const renderBuddies = (data) => {
    if (!buddyList) return;
    buddyList.innerHTML = "";
    buddyList.appendChild(renderBuddy({ device_id: LOBBY_ROOM_ID }, { lobby: true }));
    for (const buddy of data?.buddies || []) {
      if ((buddy.device_id || "").toLowerCase() === selfId.toLowerCase()) continue;
      buddyList.appendChild(renderBuddy(buddy));
    }
    if (countsEl && data?.counts) {
      countsEl.textContent =
        `${data.counts.online || 0} online · ${data.counts.away || 0} away`;
    }
  };

  const selectTarget = async (kind, id, label) => {
    activeTarget = { kind, id, label: label || id };
    if (chatHead) chatHead.textContent = activeTarget.label;
    clearMessages();
    for (const el of buddyList?.querySelectorAll(".nc-buddy") || []) {
      el.classList.toggle(
        "active",
        el.dataset.kind === kind && el.dataset.id === id,
      );
    }
    if (kind === "lobby") {
      await loadLobbyHistory();
    } else {
      await ensureDm(id);
      await loadDmHistory(id);
    }
    restartStreams();
  };

  const loadLobbyHistory = async () => {
    try {
      const data = await fetchLobbyInbox({ sinceSeq: 0, limit: 120 });
      for (const pkt of data.packets || []) {
        handleLobbyPacket(pkt);
      }
    } catch (err) {
      setStatus(err.message || String(err), "error");
    }
  };

  const handleLobbyPacket = (pkt) => {
    if (!pkt) return;
    const seq = Number(pkt.seq) || 0;
    if (seq <= lobbyLastSeq) return;
    lobbyLastSeq = Math.max(lobbyLastSeq, seq);
    const body = decodePacketPayload(pkt);
    if (!body || body.startsWith('{"type":"typing"')) return;
    const nick = pkt.sender === selfId ? selfNick : shortId(pkt.sender);
    appendMessage({
      nick,
      text: body,
      ts: pkt.created_at,
      self: pkt.sender === selfId,
    });
  };

  const ensureDm = async (peerId) => {
    if (dmChannels.has(peerId)) return dmChannels.get(peerId);
    const ch = await openDmChannel({ sender: selfId, recipient: peerId });
    dmChannels.set(peerId, ch.channel_id);
    return ch.channel_id;
  };

  const loadDmHistory = async (peerId) => {
    const channelId = dmChannels.get(peerId) || (await ensureDm(peerId));
    try {
      const data = await fetchMeshPacketInboxHybrid(selfId, {
        channelId,
        sinceSeq: 0,
        coordinatorFetch: () =>
          pollMeshPacketInbox(selfId, { channelId, sinceSeq: 0, limit: 120 }),
      });
      for (const pkt of data.packets || []) {
        handleDmPacket(peerId, pkt);
      }
    } catch (err) {
      setStatus(err.message || String(err), "error");
    }
  };

  const handleDmPacket = (peerId, pkt) => {
    if (!pkt) return;
    const channelId = dmChannels.get(peerId);
    if (channelId && pkt.channel_id !== channelId) return;
    const key = peerId;
    const last = dmLastSeq.get(key) || 0;
    const seq = Number(pkt.seq) || 0;
    if (seq <= last) return;
    dmLastSeq.set(key, Math.max(last, seq));
    if (activeTarget.kind !== "dm" || activeTarget.id !== peerId) return;
    const body = decodePacketPayload(pkt);
    if (!body) return;
    const nick = pkt.sender === selfId ? selfNick : shortId(pkt.sender);
    appendMessage({
      nick,
      text: body,
      ts: pkt.created_at,
      self: pkt.sender === selfId,
    });
  };

  const restartStreams = () => {
    if (closeLobbyStream) closeLobbyStream();
    if (closeDmStream) closeDmStream();
    closeLobbyStream = null;
    closeDmStream = null;

    closeLobbyStream = streamMeshPacketInbox(LOBBY_ROOM_ID, {
      onPacket: handleLobbyPacket,
      onError: () => {},
    });
    closeDmStream = streamMeshPacketInbox(selfId, {
      onPacket: (pkt) => {
        const peer =
          pkt.sender === selfId ? pkt.recipient : pkt.sender;
        if (peer && peer !== LOBBY_ROOM_ID) {
          handleDmPacket(peer, pkt);
        }
      },
      onError: () => {},
    });
  };

  const pollActive = async () => {
    if (activeTarget.kind === "lobby") {
      const data = await fetchLobbyInbox({ sinceSeq: lobbyLastSeq, limit: 50 });
      for (const pkt of data.packets || []) handleLobbyPacket(pkt);
      return;
    }
    const peerId = activeTarget.id;
    const channelId = dmChannels.get(peerId);
    if (!channelId) return;
    const data = await fetchMeshPacketInboxHybrid(selfId, {
      channelId,
      sinceSeq: dmLastSeq.get(peerId) || 0,
      coordinatorFetch: () =>
        pollMeshPacketInbox(selfId, {
          channelId,
          sinceSeq: dmLastSeq.get(peerId) || 0,
          limit: 50,
        }),
    });
    for (const pkt of data.packets || []) handleDmPacket(peerId, pkt);
  };

  const sendCurrent = async () => {
    const text = (composeEl?.value || "").trim();
    if (!text || !selfId) return;
    sendBtn.disabled = true;
    try {
      if (activeTarget.kind === "lobby") {
        const result = await sendLobbyMessage({ sender: selfId, message: text });
        handleLobbyPacket(result.packet || { sender: selfId, seq: lobbyLastSeq + 1, payload_text: text, created_at: Math.floor(Date.now() / 1000) });
      } else {
        const peerId = activeTarget.id;
        const channelId = await ensureDm(peerId);
        const result = await sendMeshPacket({
          channelId,
          sender: selfId,
          recipient: peerId,
          payload: text,
          payloadType: "text",
        });
        handleDmPacket(peerId, { ...result.packet, payload_text: text });
      }
      if (composeEl) composeEl.value = "";
      setStatus("Message sent.", "ok");
    } catch (err) {
      setStatus(err.message || String(err), "error");
    } finally {
      sendBtn.disabled = false;
    }
  };

  const refreshPresence = async () => {
    try {
      const platform = window.Capacitor?.getPlatform?.() || "";
      let peerKind = "browser";
      if (platform === "android") peerKind = "android";
      else if (isDesktopAppContext() || platform === "desktop") peerKind = "desktop";
      await heartbeatChatPresence({
        deviceId: selfId,
        displayName: selfNick,
        statusMessage: statusInput?.value?.trim() || "",
        peerKind,
        model: fleetDeviceModel() || (isDesktopAppContext() ? "desktop" : ""),
      });
      const data = await fetchChatPresence({ includeOffline: true });
      renderBuddies(data);
    } catch (err) {
      setStatus(`Presence: ${err.message || err}`, "error");
    }
  };

  const boot = async () => {
    selfId = await resolveDeviceId();
    selfNick =
      nickInput?.value?.trim() ||
      localStorage.getItem(STORAGE_NICK) ||
      shortId(selfId);
    if (nickInput) nickInput.value = selfNick;
    if (statusInput) {
      statusInput.value = localStorage.getItem(STORAGE_STATUS) || "On the mesh";
    }
    appendMessage({
      nick: "*",
      text: `Connected as ${selfNick} (${shortId(selfId)}). Pick Network Lobby or double-click a buddy.`,
      system: true,
    });
    setStatus("Signing on to Bloodstone Network Chat…");
    await refreshPresence();
    await loadLobbyHistory();
    restartStreams();
    presenceTimer = window.setInterval(refreshPresence, 30000);
    pollTimer = window.setInterval(() => {
      void pollActive();
    }, 8000);
    setStatus("Ready — mesh relay via BSM3 packets.", "ok");
  };

  nickInput?.addEventListener("change", () => {
    selfNick = nickInput.value.trim() || shortId(selfId);
    localStorage.setItem(STORAGE_NICK, selfNick);
    void refreshPresence();
  });

  statusInput?.addEventListener("change", () => {
    localStorage.setItem(STORAGE_STATUS, statusInput.value.trim());
    void refreshPresence();
  });

  sendBtn?.addEventListener("click", () => {
    void sendCurrent();
  });

  composeEl?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendCurrent();
    }
  });

  window.addEventListener("beforeunload", () => {
    if (closeLobbyStream) closeLobbyStream();
    if (closeDmStream) closeDmStream();
    if (presenceTimer) window.clearInterval(presenceTimer);
    if (pollTimer) window.clearInterval(pollTimer);
  });

  boot().catch((err) => {
    setStatus(`Chat failed to start: ${err?.message || err}`, "error");
    appendMessage({
      nick: "*",
      text: `Boot error: ${err?.message || err}. Try a hard refresh (Ctrl+Shift+R).`,
      system: true,
    });
  });
}
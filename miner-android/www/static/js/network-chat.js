/**
 * Network chat API — lobby room, buddy presence, and DM channels (BSM3).
 */

import { apiUrl } from "./miner-paths.js";

export const LOBBY_ROOM_ID = "bloodstone-network-chat";

export async function fetchChatPresence({ includeOffline = false } = {}) {
  const q = new URLSearchParams();
  if (includeOffline) q.set("include_offline", "1");
  const res = await fetch(apiUrl(`/api/network-chat/presence?${q}`), { cache: "no-store" });
  return res.json();
}

export async function heartbeatChatPresence({
  deviceId,
  displayName = "",
  statusMessage = "",
  peerKind = "browser",
  model = "",
} = {}) {
  const res = await fetch(apiUrl("/api/network-chat/heartbeat"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      device_id: deviceId,
      display_name: displayName,
      status_message: statusMessage,
      peer_kind: peerKind,
      model,
    }),
  });
  return res.json();
}

export async function fetchLobbyInfo() {
  const res = await fetch(apiUrl("/api/network-chat/lobby"), { cache: "no-store" });
  return res.json();
}

export async function fetchLobbyInbox({ sinceSeq = 0, limit = 80 } = {}) {
  const q = new URLSearchParams({ inbox: "1", limit: String(limit) });
  if (sinceSeq > 0) q.set("since_seq", String(sinceSeq));
  const res = await fetch(apiUrl(`/api/network-chat/lobby?${q}`), { cache: "no-store" });
  return res.json();
}

export async function sendLobbyMessage({ sender, message } = {}) {
  const res = await fetch(apiUrl("/api/network-chat/lobby/send"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sender, message }),
  });
  const data = await res.json();
  if (!data?.ok) throw new Error(data?.error || "send failed");
  return data;
}

export async function openDmChannel({ sender, recipient } = {}) {
  const res = await fetch(apiUrl("/api/network-chat/dm/open"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sender, recipient }),
  });
  const data = await res.json();
  if (!data?.ok) throw new Error(data?.error || "dm open failed");
  return data;
}

export async function fetchDmChannels(participant) {
  const res = await fetch(
    apiUrl(`/api/network-chat/channels/${encodeURIComponent(participant)}`),
    { cache: "no-store" },
  );
  return res.json();
}
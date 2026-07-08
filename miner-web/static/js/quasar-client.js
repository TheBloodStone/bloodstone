/** QUASAR Phase 2 — witness capsules + LAN echo client helpers. */

import { getLocalNodeStatus } from "./local-node.js";
import { isCapacitorAndroid } from "./device-fleet.js";

function apiBase() {
  const prefix = document.body?.dataset?.urlPrefix || "";
  return `${prefix}/api/quasar`;
}

async function postJson(path, body) {
  const res = await fetch(`${apiBase()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json();
}

async function getJson(path) {
  const res = await fetch(`${apiBase()}${path}`);
  return res.json();
}

export async function fetchQuasarStatus() {
  return getJson("/status");
}

export async function submitWitnessCapsule(capsule) {
  return postJson("/witness/submit", capsule);
}

export async function submitLanEcho(packet) {
  return postJson("/lan-echo", packet);
}

export async function buildLanEchoFromNode() {
  if (!isCapacitorAndroid()) return null;
  const status = await getLocalNodeStatus();
  const deviceId = String(status?.deviceId || status?.device_id || "").trim().toLowerCase();
  const tipHash = String(status?.bestBlockHash || status?.best_block_hash || "").trim().toLowerCase();
  const height = Number(status?.blockHeight || status?.block_height || 0);
  if (!deviceId || tipHash.length !== 64 || height <= 0) return null;
  return {
    type: "bloodstone/lan-echo/v1",
    device_id: deviceId,
    tip_hash: tipHash,
    block_height: height,
    lan_ip: String(status?.lanIp || status?.lan_ip || "").trim(),
    node_mode: String(status?.mode || "gateway"),
    issued_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
  };
}

export async function publishLocalQuasarSignals() {
  if (!isCapacitorAndroid()) return { ok: false, skipped: true };
  const status = await getLocalNodeStatus();
  const deviceId = String(status?.deviceId || status?.device_id || "").trim().toLowerCase();
  const tipHash = String(status?.bestBlockHash || status?.best_block_hash || "").trim().toLowerCase();
  const height = Number(status?.blockHeight || status?.block_height || 0);
  const out = { ok: true, witness: null, lan_echo: null };
  if (deviceId && tipHash.length === 64 && height > 0) {
    const mode = String(status?.mode || "pruned");
    out.witness = await submitWitnessCapsule({
      type: "bloodstone/witness-capsule/v1",
      device_id: deviceId,
      mesh_key: deviceId,
      tip_hash: tipHash,
      height,
      node_mode: mode,
      peer_count: Number(status?.peerCount || status?.peer_count || 0),
      algo_work: status?.difficulty || {},
      issued_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
    });
    const echo = await buildLanEchoFromNode();
    if (echo) out.lan_echo = await submitLanEcho(echo);
  }
  return out;
}

export function renderQuasarHud(data, rootEl) {
  if (!rootEl || !data) return;
  const witness = data.witness || {};
  const lan = data.lan_echo || {};
  const trip = data.tripwire || {};
  const conf = data.confirmations || {};
  rootEl.innerHTML = `
    <div class="quasar-hud-grid">
      <div><span class="muted">Witness</span><br><strong>${witness.status || "—"}</strong> (${witness.quorum_depth || 0}/${witness.required_quorum || 3})</div>
      <div><span class="muted">LAN echo</span><br><strong>${lan.quorum_label || lan.status || "—"}</strong></div>
      <div><span class="muted">Tripwire</span><br><strong>${trip.active ? "ACTIVE" : "clear"}</strong></div>
      <div><span class="muted">Deposit confirms</span><br><strong>${conf.recommended_deposit || 6}</strong></div>
    </div>`;
}

export function startQuasarBackgroundSync(intervalMs = 120000) {
  if (!isCapacitorAndroid()) return () => {};
  const tick = () => {
    publishLocalQuasarSignals().catch(() => {});
  };
  tick();
  const timer = setInterval(tick, intervalMs);
  return () => clearInterval(timer);
}
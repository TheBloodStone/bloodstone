/**
 * Poll LAN miners (Bitaxe / CGMiner) on the household Wi‑Fi and POST hashrate to the pool.
 * Runs on Android full-node hosts so the VPS can show connected device hashrate without a PC forwarder.
 */

import { apiUrl } from "./miner-paths.js";
import { isCapacitorAndroid } from "./device-fleet.js";
import { isNativeMinerAppContext } from "./capacitor-ready.js";
import { getLocalNodeStatus, isLanClientMode } from "./local-node.js";

const REPORT_INTERVAL_MS = 30000;
const GH_TO_HPS = 1_000_000_000;
const MH_TO_HPS = 1_000_000;

let timer = null;
let lastRunAt = 0;

function pickBitaxeGhs(info) {
  const rates = {};
  for (const key of [
    "hashRate",
    "hashRate_1m",
    "hashRate_10m",
    "hashRate_1h",
    "expectedHashrate",
  ]) {
    const val = Number(info?.[key]);
    if (val > 0) rates[key] = val;
  }
  const asics = info?.hashrateMonitor?.asics;
  if (Array.isArray(asics) && asics[0]) {
    const total = Number(asics[0].total);
    if (total > 0) rates.monitor = total;
  }
  for (const key of [
    "hashRate",
    "hashRate_1m",
    "monitor",
    "hashRate_10m",
    "hashRate_1h",
    "expectedHashrate",
  ]) {
    if (rates[key] > 0) return rates[key];
  }
  const vals = Object.values(rates);
  return vals.length ? Math.max(...vals) : 0;
}

function cgminerRateHps(summary) {
  const row = summary?.SUMMARY?.[0];
  if (!row) return 0;
  const pairs = [
    ["GHS 5s", GH_TO_HPS],
    ["GHS av", GH_TO_HPS],
    ["MHS 5s", MH_TO_HPS],
    ["MHS av", MH_TO_HPS],
    ["GHS 5s*", GH_TO_HPS],
    ["MHS 5s*", MH_TO_HPS],
  ];
  for (const [key, mult] of pairs) {
    const val = Number(row[key]);
    if (val > 0) return val * mult;
  }
  return 0;
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: { Accept: "application/json", ...(options.headers || {}) },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function loadDeviceConfig() {
  try {
    const res = await fetch(apiUrl("/api/pool/lan-forwarder/devices?format=json"));
    if (!res.ok) return [];
    const data = await res.json();
    if (Array.isArray(data)) return data;
    return Array.isArray(data?.devices) ? data.devices : [];
  } catch (_) {
    return [];
  }
}

function normalizeHost(host) {
  const raw = String(host || "").trim();
  if (!raw || ["auto", "discover"].includes(raw.toLowerCase())) return "";
  if (raw.includes("://")) return raw.replace(/\/$/, "");
  return `http://${raw.replace(/\/$/, "")}`;
}

async function pollBitaxe(dev) {
  const host = normalizeHost(dev.host);
  if (!host) return null;
  const info = await fetchJson(`${host}/api/system/info`);
  const ghs = pickBitaxeGhs(info);
  if (ghs <= 0) return null;
  const shareHits = Number(info.blockFound || info.blocksFound || 0);
  return {
    type: "bitaxe",
    host,
    name: dev.name || "Bitaxe",
    address: dev.address || "",
    worker: dev.worker || dev.address || "",
    asic_model: info.ASICModel || dev.asic_model || "",
    hashrate_ghs: ghs,
    hashrate_hps: ghs * GH_TO_HPS,
    device_share_hits: shareHits,
    blockFound: shareHits,
    forwarder_id: "android-lan-host",
  };
}

async function pollCgminer(dev) {
  const host = normalizeHost(dev.host);
  if (!host) return null;
  const ip = host.replace(/^https?:\/\//, "").split(":")[0];
  const port = Number(dev.cgminer_port || 4028);
  const summary = await fetchJson(`http://${ip}:${port}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command: "summary" }),
  });
  const hps = cgminerRateHps(summary);
  if (hps <= 0) return null;
  return {
    type: "cgminer",
    host: `http://${ip}`,
    name: dev.name || "ASIC",
    address: dev.address || "",
    worker: dev.worker || dev.address || "",
    asic_model: dev.asic_model || "ASIC",
    hashrate_hps: hps,
    forwarder_id: "android-lan-host",
  };
}

async function postReport(payload) {
  const res = await fetch(apiUrl("/api/pool/bitaxe/report"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.ok;
}

async function fetchWithTimeout(url, ms = 1200) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetchJson(url, { signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function scanSubnetForBitaxe(subnetBase) {
  const base = String(subnetBase || "").trim();
  if (!base) return [];
  const prefix = base.split(".").slice(0, 3).join(".");
  const found = [];
  const ips = [];
  for (let i = 1; i < 255; i += 1) ips.push(`${prefix}.${i}`);
  const batchSize = 24;
  for (let offset = 0; offset < ips.length; offset += batchSize) {
    const batch = ips.slice(offset, offset + batchSize);
    await Promise.all(
      batch.map((ip) =>
        fetchWithTimeout(`http://${ip}/api/system/info`, 900)
          .then((info) => {
            if (pickBitaxeGhs(info) > 0) found.push(ip);
          })
          .catch(() => {}),
      ),
    );
  }
  return found;
}

async function resolveAutoHosts(devices, lanIp) {
  const mapping = {};
  const auto = devices.filter((d) =>
    ["auto", "discover", ""].includes(String(d.host || "").trim().toLowerCase()),
  );
  if (!auto.length || !lanIp) return mapping;
  const ips = await scanSubnetForBitaxe(lanIp);
  let idx = 0;
  for (const dev of auto) {
    if (dev.type === "cgminer") continue;
    if (idx < ips.length) {
      const key = String(dev.worker || dev.name || "").toLowerCase();
      mapping[key] = ips[idx];
      idx += 1;
    }
  }
  return mapping;
}

export async function reportLanDevicesOnce(options = {}) {
  if (!isNativeMinerAppContext()) return { ok: false, skipped: "not-native-app" };
  const status = options.nodeStatus || (await getLocalNodeStatus());
  if (isLanClientMode(status?.mode || "")) {
    return { ok: false, skipped: "lan-client" };
  }
  const lanIp = String(status?.lanIp || "").trim();
  if (!lanIp) return { ok: false, skipped: "no-lan-ip" };

  const devices = await loadDeviceConfig();
  if (!devices.length) return { ok: false, skipped: "no-config" };

  const discovered = await resolveAutoHosts(devices, lanIp);
  let reported = 0;
  const errors = [];

  for (const dev of devices) {
    let host = normalizeHost(dev.host);
    if (!host) {
      const key = String(dev.worker || dev.name || "").toLowerCase();
      const ip = discovered[key];
      if (ip) host = `http://${ip}`;
    }
    if (!host) continue;
    const entry = { ...dev, host };
    try {
      const dtype = String(dev.type || "bitaxe").toLowerCase();
      const payload =
        dtype === "cgminer" || dtype === "luck" || dtype === "asic"
          ? await pollCgminer(entry)
          : await pollBitaxe(entry);
      if (!payload) continue;
      if (await postReport(payload)) reported += 1;
    } catch (err) {
      errors.push(`${dev.name || dev.host}: ${err?.message || err}`);
    }
  }

  lastRunAt = Date.now();
  return { ok: reported > 0, reported, errors, lanIp };
}

export function startLanDeviceReporter(options = {}) {
  if (timer || !isNativeMinerAppContext()) return;
  const intervalMs = Number(options.intervalMs || REPORT_INTERVAL_MS);
  const tick = async () => {
    try {
      const result = await reportLanDevicesOnce(options);
      if (result.reported > 0 && typeof options.onLog === "function") {
        options.onLog(
          `LAN reporter: ${result.reported} device(s) reported to pool`,
          "success",
        );
      }
    } catch (err) {
      if (typeof options.onLog === "function") {
        options.onLog(`LAN reporter: ${err?.message || err}`, "warn");
      }
    }
  };
  void tick();
  timer = window.setInterval(() => void tick(), intervalMs);
}

export function stopLanDeviceReporter() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

export function lastLanReportAt() {
  return lastRunAt;
}
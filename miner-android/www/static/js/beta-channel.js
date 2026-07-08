/**
 * Beta release channel — one-time LAN-gated invite codes unlock beta OTA.
 */

import { getLocalNodeStatus } from "./local-node.js";
import { whenCapacitorReady } from "./capacitor-ready.js";

export const BETA_TOKEN_KEY = "bloodstone-beta-access-token";

function apiBase() {
  const fromBody = document.body?.dataset?.updateBase || document.body?.dataset?.publicRoot;
  if (fromBody) return String(fromBody).replace(/\/$/, "");
  const prefix = document.body?.dataset?.urlPrefix || "";
  if (prefix) {
    try {
      return `${window.location.origin}${prefix}`.replace(/\/$/, "");
    } catch (_) {
      /* ignore */
    }
  }
  return "https://bloodstonewallet.mytunnel.org";
}

export function getBetaAccessToken() {
  try {
    return localStorage.getItem(BETA_TOKEN_KEY) || "";
  } catch (_) {
    return "";
  }
}

export function setBetaAccessToken(token) {
  try {
    const value = String(token || "").trim();
    if (!value) {
      localStorage.removeItem(BETA_TOKEN_KEY);
      return false;
    }
    localStorage.setItem(BETA_TOKEN_KEY, value);
    return true;
  } catch (_) {
    return false;
  }
}

export function clearBetaAccessToken() {
  return setBetaAccessToken("");
}

export function isBetaChannelEnabled() {
  return Boolean(getBetaAccessToken());
}

function isPrivateLanIp(ip) {
  const value = String(ip || "").trim();
  if (!value) return false;
  if (value.startsWith("10.") || value.startsWith("192.168.")) return true;
  if (/^172\.(1[6-9]|2\d|3[0-1])\./.test(value)) return true;
  if (value.startsWith("169.254.")) return true;
  return false;
}

export async function resolveLanIp() {
  try {
    const status = await getLocalNodeStatus();
    const lanIp = String(status?.lanIp || "").trim();
    if (isPrivateLanIp(lanIp)) return lanIp;
  } catch (_) {
    /* ignore */
  }
  return "";
}

export async function isOnLan() {
  return Boolean(await resolveLanIp());
}

async function fetchJson(path, options = {}) {
  const url = `${apiBase()}${path}`;
  const cap = window.Capacitor;
  if (cap?.nativePromise && !options.body) {
    try {
      const headers = { Accept: "application/json", ...(options.headers || {}) };
      const response = await cap.nativePromise("CapacitorHttp", "request", {
        url,
        method: options.method || "GET",
        headers,
      });
      const status = Number(response?.status) || 0;
      if (status < 200 || status >= 300) {
        throw new Error(`Request failed (${status})`);
      }
      const raw = response?.data;
      return typeof raw === "string" ? JSON.parse(raw) : raw;
    } catch (_) {
      /* fall through */
    }
  }
  const res = await fetch(url, {
    cache: "no-store",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }
  return res.json();
}

async function resolveDeviceId() {
  await whenCapacitorReady();
  const cap = window.Capacitor;
  const plugin = cap?.Plugins?.BloodstoneDevicePool;
  if (plugin?.getDeviceId) {
    try {
      const row = await plugin.getDeviceId();
      const id = String(row?.deviceId || row?.device_id || "").trim();
      if (id) return id;
    } catch (_) {
      /* ignore */
    }
  }
  try {
    const key = "bloodstone-device-id";
    let id = localStorage.getItem(key) || "";
    if (!id) {
      id = `web-${Math.random().toString(36).slice(2, 10)}`;
      localStorage.setItem(key, id);
    }
    return id;
  } catch (_) {
    return "unknown-device";
  }
}

export async function redeemBetaCode(code) {
  const lanIp = await resolveLanIp();
  if (!lanIp) {
    return {
      ok: false,
      error: "beta_redeem_requires_lan",
      message: "Connect to Wi‑Fi on your LAN to unlock beta testing.",
    };
  }
  const deviceId = await resolveDeviceId();
  const data = await fetchJson("/mining/api/beta/redeem", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code: String(code || "").trim(),
      device_id: deviceId,
      lan_ip: lanIp,
    }),
  });
  if (data?.ok && data?.token) {
    setBetaAccessToken(data.token);
  }
  return data;
}

export async function refreshBetaStatus() {
  const token = getBetaAccessToken();
  if (!token) {
    return { ok: true, beta_active: false, release_channel: "stable" };
  }
  return fetchJson(
    `/mining/api/beta/status?beta_token=${encodeURIComponent(token)}`,
    {
      headers: { "X-Bloodstone-Beta-Token": token },
    },
  );
}

function setBetaPanelStatus(message, kind = "muted") {
  const el = document.getElementById("android-beta-status");
  if (!el) return;
  el.textContent = message || "";
  el.className = `muted small android-beta-status ${kind}`.trim();
}

function updateBetaPanelVisibility(onLan, betaActive) {
  const panel = document.getElementById("android-beta-panel");
  if (!panel) return;
  panel.hidden = !onLan && !betaActive;
  const form = document.getElementById("android-beta-form");
  const active = document.getElementById("android-beta-active");
  if (form) form.hidden = betaActive;
  if (active) active.hidden = !betaActive;
}

export async function initBetaChannelOptions() {
  const panel = document.getElementById("android-beta-panel");
  if (!panel || panel.dataset.hooked === "1") return;
  panel.dataset.hooked = "1";

  const onLan = await isOnLan();
  let betaActive = isBetaChannelEnabled();
  if (betaActive) {
    try {
      const status = await refreshBetaStatus();
      betaActive = Boolean(status?.beta_active);
      if (!betaActive) clearBetaAccessToken();
    } catch (_) {
      /* keep cached token */
    }
  }

  updateBetaPanelVisibility(onLan, betaActive);
  if (betaActive) {
    setBetaPanelStatus(
      "Beta channel active — test the build, then approve it for everyone on this LAN.",
      "success",
    );
  } else if (onLan) {
    setBetaPanelStatus(
      "On LAN — beta testers unlock pre-release OTA; after validation, this LAN gets the release.",
    );
  } else {
    setBetaPanelStatus("Beta testing unlocks on your home/work LAN.");
  }

  const input = document.getElementById("android-beta-code");
  const redeemBtn = document.getElementById("android-beta-redeem-btn");
  const approveBtn = document.getElementById("android-beta-approve-btn");
  const leaveBtn = document.getElementById("android-beta-leave-btn");

  redeemBtn?.addEventListener("click", async () => {
    const code = input?.value || "";
    redeemBtn.disabled = true;
    try {
      const result = await redeemBetaCode(code);
      if (!result?.ok) {
        setBetaPanelStatus(result?.message || "Could not redeem beta code.", "warn");
        return;
      }
      if (input) input.value = "";
      updateBetaPanelVisibility(true, true);
      setBetaPanelStatus("Beta unlocked. Checking for beta updates…", "success");
      const { runAndroidUpdateCheck } = await import("./app-update.js");
      await runAndroidUpdateCheck({ manual: true, force: true });
    } catch (err) {
      setBetaPanelStatus(err?.message || "Beta redeem failed.", "warn");
    } finally {
      redeemBtn.disabled = false;
    }
  });

  approveBtn?.addEventListener("click", async () => {
    const token = getBetaAccessToken();
    if (!token) {
      setBetaPanelStatus("Beta access required before LAN approval.", "warn");
      return;
    }
    const lanIp = await resolveLanIp();
    if (!lanIp) {
      setBetaPanelStatus("Connect to your LAN before approving a release.", "warn");
      return;
    }
    approveBtn.disabled = true;
    try {
      const deviceId = await resolveDeviceId();
      const data = await fetchJson("/mining/api/beta/validate-lan", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Bloodstone-Beta-Token": token,
        },
        body: JSON.stringify({
          beta_token: token,
          lan_ip: lanIp,
          device_id: deviceId,
        }),
      });
      if (!data?.ok) {
        setBetaPanelStatus(data?.message || "LAN approval failed.", "warn");
        return;
      }
      setBetaPanelStatus(
        `Approved for this LAN — stable OTA is now APK ${data.apk_version || "?"}.`,
        "success",
      );
    } catch (err) {
      setBetaPanelStatus(err?.message || "LAN approval failed.", "warn");
    } finally {
      approveBtn.disabled = false;
    }
  });

  leaveBtn?.addEventListener("click", async () => {
    clearBetaAccessToken();
    updateBetaPanelVisibility(onLan, false);
    setBetaPanelStatus("Returned to stable release channel.");
    const { runAndroidUpdateCheck } = await import("./app-update.js");
    await runAndroidUpdateCheck({ manual: true, force: true });
  });
}
/**
 * Desktop miner updates — .exe / .tar.gz from downloads, never APK or Android web zip.
 */

import { compareAppVersions, versionIsOlder } from "./app-update.js";
import { isDesktopAppContext } from "./capacitor-ready.js";

const AUTO_UPDATE_KEY = "bloodstone-desktop-auto-update";
const DEFAULT_UPDATE_BASE = "https://bloodstonewallet.mytunnel.org";

let optionsHooked = false;
let updateInFlight = false;

function updateApiBase() {
  const fromBody = document.body?.dataset?.updateBase || document.body?.dataset?.publicRoot;
  if (fromBody) return String(fromBody).replace(/\/$/, "");
  return DEFAULT_UPDATE_BASE;
}

function setUpdateStatus(text, kind = "") {
  const el =
    document.getElementById("bs-ota-status")
    || document.getElementById("android-update-status");
  if (!el) return;
  el.textContent = text;
  el.className = kind ? `update-status ${kind}` : "update-status";
}

function setVersionLine(version) {
  const line = document.getElementById("android-app-version-line");
  if (!line || !version) return;
  line.textContent = `Desktop miner v${version}`;
}

function hideAndroidOtaChrome() {
  const strip = document.getElementById("android-update-strip");
  if (strip) strip.hidden = true;
  const sticky = document.getElementById("bs-ota-sticky");
  if (sticky) sticky.hidden = true;
}

export function isDesktopAutoUpdateEnabled() {
  if (!isDesktopAppContext()) return false;
  try {
    const raw = localStorage.getItem(AUTO_UPDATE_KEY);
    if (raw === null) return true;
    return raw === "1";
  } catch (_) {
    return true;
  }
}

async function readInstalledDesktopVersion() {
  try {
    const meta = await window.__bloodstoneDesktop?.getMeta?.();
    if (meta?.version) return String(meta.version).trim();
  } catch (_) {
    /* ignore */
  }
  const stamped = document.body?.dataset?.appVersion;
  if (stamped) return String(stamped).replace(/-desktop$/, "").trim();
  return "";
}

async function fetchDesktopUpdateManifest() {
  const base = updateApiBase();
  const urls = [
    `${base}/mining/api/desktop-miner/update`,
    `${base}/api/desktop-miner/update`,
  ];
  let lastErr = null;
  for (const url of urls) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error(`Update check failed (${res.status})`);
      const data = await res.json();
      if (!data?.ok) throw new Error("Desktop update manifest unavailable");
      return data;
    } catch (err) {
      lastErr = err instanceof Error ? err : new Error(String(err));
    }
  }
  throw lastErr || new Error("Desktop update manifest unavailable");
}

function pickDownloadUrl(manifest, meta = {}) {
  const platform = String(meta.platform || "").toLowerCase();
  if (platform === "win32" || platform === "windows") {
    return (
      manifest.win_portable_url
      || manifest.win_installer_url
      || manifest.windows_url
    );
  }
  if (platform === "linux") {
    return manifest.linux_url;
  }
  const ua = navigator.userAgent || "";
  if (/Windows/i.test(ua)) {
    return manifest.win_portable_url || manifest.win_installer_url;
  }
  if (/Linux/i.test(ua)) {
    return manifest.linux_url;
  }
  return manifest.downloads_page || `${updateApiBase()}/downloads/`;
}

export async function runDesktopUpdateCheck(options = {}) {
  if (!isDesktopAppContext() || updateInFlight) return null;
  const auto = options.force === true || options.manual === true || isDesktopAutoUpdateEnabled();
  if (!auto && !options.manual) return null;

  updateInFlight = true;
  try {
    setUpdateStatus("Checking for desktop updates…");
    const [installed, manifest, meta] = await Promise.all([
      readInstalledDesktopVersion(),
      fetchDesktopUpdateManifest(),
      window.__bloodstoneDesktop?.getMeta?.().catch(() => ({})),
    ]);
    const remote = String(manifest.desktop_version || manifest.version || "").trim();
    setVersionLine(installed || remote);

    if (!remote || !versionIsOlder(installed, remote)) {
      setUpdateStatus(
        installed ? `Up to date (desktop v${installed})` : "Up to date",
        "ok",
      );
      return { upToDate: true, installed, manifest };
    }

    const url = pickDownloadUrl(manifest, meta);
    const label = `Desktop update v${remote} available`;
    setUpdateStatus(`${label} — opening download…`, "warn");

    if (options.manual || options.force || isDesktopAutoUpdateEnabled()) {
      if (window.__bloodstoneDesktop?.openUrl && url) {
        await window.__bloodstoneDesktop.openUrl(url);
        setUpdateStatus(`${label} — download opened in your browser.`, "ok");
      } else if (url) {
        window.open(url, "_blank", "noopener");
      }
    }

    return { updateAvailable: true, installed, remote, manifest, url };
  } catch (err) {
    setUpdateStatus(`Update check failed: ${err?.message || err}`, "error");
    return { error: String(err?.message || err) };
  } finally {
    updateInFlight = false;
  }
}

export function initDesktopUpdateOptions() {
  if (!isDesktopAppContext() || optionsHooked) return;
  optionsHooked = true;
  hideAndroidOtaChrome();

  const checkBtns = document.querySelectorAll(
    ".android-check-update-btn, #android-check-update-btn, #bs-ota-btn",
  );
  for (const btn of checkBtns) {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      void runDesktopUpdateCheck({ manual: true, force: true });
    });
  }
}

export async function initDesktopAppUpdate(options = {}) {
  if (!isDesktopAppContext()) return null;
  initDesktopUpdateOptions();
  try {
    const installed = await readInstalledDesktopVersion();
    setVersionLine(installed);
  } catch (_) {
    setVersionLine("");
  }
  if (!isDesktopAutoUpdateEnabled() && !options.force) {
    setUpdateStatus("Tap Check for updates for desktop builds (.exe / .tar.gz)", "warn");
    return null;
  }
  return runDesktopUpdateCheck({ ...options, force: options.force === true });
}
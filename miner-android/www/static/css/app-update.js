/**
 * Android auto-update: live web-bundle OTA first, APK only when native code changes.
 */

import { fleetPlugin } from "./device-fleet.js";
import { isAndroidAppContext, whenCapacitorReady } from "./capacitor-ready.js";
import {
  bytesToB64,
  reconstructMeshAssetFromKey,
} from "./mesh-asset-reconstruct.js";

const AUTO_UPDATE_KEY = "bloodstone-android-auto-update";
const UPDATE_SESSION_KEY = "bloodstone-android-update-session";
const WEB_BUNDLE_SESSION_KEY = "bloodstone-android-web-bundle-session";
const DEFAULT_UPDATE_BASE = "https://bloodstonewallet.mytunnel.org";

let optionsHooked = false;
let updateInFlight = false;
const MIN_WEB_OTA_APK = "1.3.17";

async function resolveUpdatePlugin() {
  await whenCapacitorReady();
  return fleetPlugin();
}

function webBundleOtaSupported(plugin) {
  return Boolean(plugin?.downloadAndApplyWebBundle);
}

function apkSupportsWebOta(versionName) {
  const v = formatInstalledVersion(versionName);
  if (!v) return false;
  return compareAppVersions(v, MIN_WEB_OTA_APK) >= 0;
}

export function isAndroidAutoUpdateEnabled() {
  if (!isAndroidAppContext()) return false;
  try {
    const raw = localStorage.getItem(AUTO_UPDATE_KEY);
    if (raw === null) return true;
    return raw === "1";
  } catch (_) {
    return true;
  }
}

export function setAndroidAutoUpdateEnabled(enabled) {
  if (!isAndroidAppContext()) return false;
  try {
    localStorage.setItem(AUTO_UPDATE_KEY, enabled ? "1" : "0");
  } catch (_) {
    return false;
  }
  return true;
}

function updateApiBase() {
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
  return DEFAULT_UPDATE_BASE;
}

export function compareAppVersions(localVersion, remoteVersion) {
  const parse = (value) =>
    String(value || "0")
      .split(".")
      .map((part) => parseInt(part, 10) || 0);
  const left = parse(localVersion);
  const right = parse(remoteVersion);
  const len = Math.max(left.length, right.length);
  for (let i = 0; i < len; i += 1) {
    const a = left[i] || 0;
    const b = right[i] || 0;
    if (a > b) return 1;
    if (a < b) return -1;
  }
  return 0;
}

export function versionIsOlder(localVersion, remoteVersion) {
  const local = String(localVersion || "").trim();
  const remote = String(remoteVersion || "").trim();
  if (!remote) return false;
  if (!local) return true;
  if (local === remote) return false;
  const semver = compareAppVersions(local, remote);
  if (semver !== 0) return semver < 0;
  return local < remote;
}

function clearUpdateSessionKeys() {
  try {
    sessionStorage.removeItem(UPDATE_SESSION_KEY);
    sessionStorage.removeItem(WEB_BUNDLE_SESSION_KEY);
  } catch (_) {
    /* ignore */
  }
}

async function fetchJsonUrl(url) {
  const cap = window.Capacitor;
  if (cap?.nativePromise) {
    try {
      const response = await cap.nativePromise("CapacitorHttp", "request", {
        url,
        method: "GET",
        headers: { Accept: "application/json" },
      });
      const status = Number(response?.status) || 0;
      if (status < 200 || status >= 300) {
        throw new Error(`Update check failed (${status})`);
      }
      const raw = response?.data;
      const data = typeof raw === "string" ? JSON.parse(raw) : raw;
      return data;
    } catch (_) {
      /* fall through to fetch */
    }
  }
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Update check failed (${res.status})`);
  }
  return res.json();
}

async function fetchUpdateManifest() {
  const base = updateApiBase();
  const urls = [
    `${base}/mining/api/android-miner/update`,
    `${base}/api/android-miner/update`,
  ];
  let lastErr = null;
  for (const url of urls) {
    try {
      const data = await fetchJsonUrl(url);
      if (!data?.ok) {
        lastErr = new Error("Update manifest unavailable");
        continue;
      }
      if (!data?.apk_url && !data?.web_bundle_url) {
        lastErr = new Error("Update manifest incomplete");
        continue;
      }
      return data;
    } catch (err) {
      lastErr = err instanceof Error ? err : new Error(String(err));
    }
  }
  throw lastErr || new Error("Update manifest unavailable");
}

function normalizeVersionInfo(info, source) {
  if (!info || typeof info !== "object") return null;
  const versionName = info.versionName != null ? String(info.versionName).trim() : "";
  const versionCode = Number(info.versionCode) || 0;
  if (versionName && versionName !== "0") {
    return { versionName, versionCode, source };
  }
  if (versionCode > 0) {
    return { versionName: `build-${versionCode}`, versionCode, source };
  }
  return null;
}

async function readInstalledVersion() {
  await whenCapacitorReady();
  const stamped = document.body?.dataset?.appVersion;
  const fromStamp = normalizeVersionInfo(
    stamped ? { versionName: String(stamped), versionCode: 0 } : null,
    "dataset",
  );
  if (fromStamp) return fromStamp;

  for (let attempt = 0; attempt < 8; attempt += 1) {
    const cap = window.Capacitor;
    if (cap?.nativePromise) {
      try {
        const info = await cap.nativePromise(
          "BloodstoneDevicePool",
          "getAppVersion",
          {},
        );
        const normalized = normalizeVersionInfo(info, "nativePromise");
        if (normalized) return normalized;
      } catch (_) {
        /* retry */
      }
    }

    const plugin = fleetPlugin();
    if (plugin && typeof plugin.getAppVersion === "function") {
      try {
        const info = await plugin.getAppVersion();
        const normalized = normalizeVersionInfo(info, "plugin");
        if (normalized) return normalized;
      } catch (_) {
        /* retry */
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }

  return { versionName: null, versionCode: 0, source: "unknown" };
}

async function readInstalledWebBundleVersion() {
  await whenCapacitorReady();
  const plugin = fleetPlugin();
  if (plugin?.getWebBundleInfo) {
    try {
      const info = await plugin.getWebBundleInfo();
      const version = String(info?.version || "").trim();
      if (version) return version;
    } catch (_) {
      /* fall through */
    }
  }
  try {
    return localStorage.getItem("bloodstone-web-bundle-version") || "";
  } catch (_) {
    return "";
  }
}

function setUpdateStatus(text, kind = "") {
  const targets = document.querySelectorAll("#android-update-status");
  if (!targets.length) return;
  targets.forEach((el) => {
  el.textContent = text || "";
  el.hidden = !text;
  el.classList.toggle("update-ok", kind === "ok");
  el.classList.toggle("update-warn", kind === "warn");
  el.classList.toggle("update-error", kind === "error");
  });
}

function formatInstalledVersion(versionName) {
  const v = versionName != null ? String(versionName).trim() : "";
  return v && v !== "0" ? v : "";
}

function setVersionLine(apkVersion, webBundleVersion = "") {
  const targets = document.querySelectorAll("#android-app-version-line");
  if (!targets.length) return;
  targets.forEach((el) => {
  const apk = formatInstalledVersion(apkVersion);
  const web = String(webBundleVersion || "").trim();
  if (apk && web) {
    el.textContent = `Installed: APK v${apk} · UI ${web}`;
  } else if (apk) {
    el.textContent = `Installed: APK v${apk} · UI bundled`;
  } else if (web) {
    el.textContent = `Installed UI: ${web}`;
  } else {
    el.textContent = "Installed version: —";
  }
  });
}

function markUpdateAttempted(remoteVersion, key = UPDATE_SESSION_KEY) {
  try {
    sessionStorage.setItem(key, String(remoteVersion || ""));
  } catch (_) {
    /* ignore */
  }
}

function updateAlreadyAttempted(remoteVersion, key = UPDATE_SESSION_KEY) {
  try {
    return sessionStorage.getItem(key) === String(remoteVersion || "");
  } catch (_) {
    return false;
  }
}

async function ensureInstallPermission(plugin) {
  if (!plugin?.canInstallApkUpdates) return true;
  try {
    const status = await plugin.canInstallApkUpdates();
    if (status?.allowed) return true;
    if (plugin.requestInstallApkPermission) {
      await plugin.requestInstallApkPermission();
    }
    const retry = await plugin.canInstallApkUpdates();
    return Boolean(retry?.allowed);
  } catch (_) {
    return false;
  }
}

async function installApkFromUrl(plugin, apkUrl) {
  await plugin.downloadAndInstallApk({ url: apkUrl });
}

async function installApkFromMesh(plugin, manifest, onProgress) {
  const assetKey = manifest.mesh_asset_key || manifest.mesh?.asset_key;
  if (!assetKey) {
    throw new Error("No mesh fallback configured for this release");
  }
  if (!plugin?.installApkFromBase64) {
    throw new Error("Mesh install requires a newer Bloodstone miner build");
  }
  const bytes = await reconstructMeshAssetFromKey(assetKey, {
    expectedSha256: manifest.mesh_file_sha256 || manifest.sha256,
    expectedMerkle: manifest.mesh_merkle_root || manifest.mesh?.merkle_root,
    onProgress,
  });
  await plugin.installApkFromBase64({
    data_b64: bytesToB64(bytes),
    sha256: manifest.mesh_file_sha256 || manifest.sha256 || "",
  });
}

async function downloadAndInstallApkUpdate(plugin, manifest, onProgress) {
  const apkUrl = manifest.apk_url_latest || manifest.apk_url;
  try {
    await installApkFromUrl(plugin, apkUrl);
    return { source: "cdn" };
  } catch (cdnErr) {
    const meshKey = manifest.mesh_asset_key || manifest.mesh?.asset_key;
    if (!meshKey) throw cdnErr;
    onProgress?.("CDN unavailable — rebuilding APK from chain mesh…");
    await installApkFromMesh(plugin, manifest, onProgress);
    return { source: "mesh", cdnError: String(cdnErr?.message || cdnErr) };
  }
}

async function applyWebBundleUpdate(plugin, manifest, onProgress) {
  const url = manifest.web_bundle_url_latest || manifest.web_bundle_url;
  const version = manifest.web_bundle_version;
  if (!url || !version) {
    throw new Error("Web bundle manifest incomplete");
  }
  if (!webBundleOtaSupported(plugin)) {
    throw new Error(
      `Live UI updates require Bloodstone miner APK ${MIN_WEB_OTA_APK}+ (install latest APK from downloads)`,
    );
  }
  onProgress?.("downloading UI bundle…");
  const result = await plugin.downloadAndApplyWebBundle({
    url,
    sha256: manifest.web_bundle_sha256 || "",
    version,
  });
  try {
    localStorage.setItem("bloodstone-web-bundle-version", version);
  } catch (_) {
    /* ignore */
  }
  if (document.body?.dataset) {
    document.body.dataset.webBundleVersion = version;
  }
  onProgress?.("UI bundle applied — reloading…");
  if (plugin.reloadApp) {
    await plugin.reloadApp();
  } else {
    window.location.reload();
  }
  return result;
}

async function maybeApplyWebBundleUpdate(plugin, manifest, options = {}) {
  const remoteWeb = String(manifest.web_bundle_version || "").trim();
  const remoteUrl = manifest.web_bundle_url_latest || manifest.web_bundle_url;
  if (!remoteWeb || !remoteUrl) {
    return { skipped: true, reason: "no_web_bundle" };
  }

  const installedWeb = await readInstalledWebBundleVersion();
  if (!versionIsOlder(installedWeb, remoteWeb)) {
    return { upToDate: true, installedWeb, remoteWeb };
  }

  const label = `UI ${remoteWeb} (you have ${installedWeb || "bundled"})`;
  if (
    !options.force
    && !options.manual
    && updateAlreadyAttempted(remoteWeb, WEB_BUNDLE_SESSION_KEY)
  ) {
    setUpdateStatus(`${label} — already updated this session`, "warn");
    return { updateAvailable: true, installedWeb, remoteWeb, skipped: true };
  }

  if (!webBundleOtaSupported(plugin)) {
    const installedApk = formatInstalledVersion(options.installedApk);
    const note = apkSupportsWebOta(installedApk)
      ? `${label} — native bridge not ready; tap Check for updates`
      : `${label} — install APK ${MIN_WEB_OTA_APK}+ for live UI updates (mining still works)`;
    if (options.manual || options.force) {
      throw new Error(note);
    }
    setUpdateStatus(note, "warn");
    return {
      updateAvailable: true,
      installedWeb,
      remoteWeb,
      skipped: true,
      reason: "ota_unsupported",
    };
  }

  setUpdateStatus(`${label} — downloading live update…`, "warn");
  await applyWebBundleUpdate(plugin, manifest, (msg) => {
    if (typeof msg === "string") {
      setUpdateStatus(`${label} — ${msg}`, "warn");
    }
  });
  markUpdateAttempted(remoteWeb, WEB_BUNDLE_SESSION_KEY);
  setUpdateStatus(`${label} — applied`, "ok");
  return { updateAvailable: true, installedWeb, remoteWeb, applied: true };
}

async function maybeApplyApkUpdate(plugin, manifest, installed, options = {}) {
  const remoteApk = String(manifest.apk_version || manifest.version || "").trim();
  if (!remoteApk || !manifest.apk_url) {
    return { skipped: true, reason: "no_apk" };
  }

  const installedVersion = formatInstalledVersion(installed.versionName);
  if (!versionIsOlder(installedVersion, remoteApk)) {
    return { upToDate: true, installedVersion, remoteApk };
  }

  const haveLabel = installedVersion ? `v${installedVersion}` : "unknown version";
  const updateLabel = `APK v${remoteApk} available (you have ${haveLabel})`;
  if (!options.force && !options.manual && updateAlreadyAttempted(remoteApk)) {
    setUpdateStatus(`${updateLabel} — install prompt already shown this session`, "warn");
    return { updateAvailable: true, installed, manifest, skipped: true };
  }

  setUpdateStatus(`${updateLabel} — downloading…`, "warn");
  if (!plugin?.downloadAndInstallApk) {
    setUpdateStatus(`${updateLabel} — open downloads to update manually`, "warn");
    return { updateAvailable: true, installed, manifest, needsManual: true };
  }

  const allowed = await ensureInstallPermission(plugin);
  if (!allowed) {
    setUpdateStatus(
      `${updateLabel} — allow "Install unknown apps" for Bloodstone, then tap Check for updates`,
      "error",
    );
    return { updateAvailable: true, installed, manifest, needsPermission: true };
  }

  await downloadAndInstallApkUpdate(plugin, manifest, (msg) => {
    if (typeof msg === "string") {
      setUpdateStatus(`${updateLabel} — ${msg}`, "warn");
      return;
    }
    if (msg?.total) {
      const pct = Math.min(100, Math.round((msg.downloaded / msg.total) * 100));
      setUpdateStatus(`${updateLabel} — mesh download ${pct}%`, "warn");
    }
  });
  markUpdateAttempted(remoteApk);
  setUpdateStatus(`${updateLabel} — installer opened. Confirm to update.`, "ok");
  options.onUpdatePrompt?.(manifest);
  return { updateAvailable: true, installed, manifest, prompted: true };
}

export async function runAndroidUpdateCheck(options = {}) {
  if (!isAndroidAppContext() || updateInFlight) return null;
  const auto = options.force === true || isAndroidAutoUpdateEnabled();
  if (!auto && !options.manual) return null;
  if (options.force || options.manual) {
    clearUpdateSessionKeys();
  }

  updateInFlight = true;
  try {
    setUpdateStatus("Checking for updates…");
    const [installed, installedWeb, manifest] = await Promise.all([
      readInstalledVersion(),
      readInstalledWebBundleVersion(),
      fetchUpdateManifest(),
    ]);
    setVersionLine(installed.versionName, installedWeb);

    const plugin = await resolveUpdatePlugin();
    const webResult = await maybeApplyWebBundleUpdate(plugin, manifest, {
      ...options,
      installedApk: installed.versionName,
    });
    if (webResult?.applied) {
      return { webBundleUpdated: true, installed, installedWeb, manifest, webResult };
    }

    const apkResult = await maybeApplyApkUpdate(plugin, manifest, installed, options);
    if (apkResult?.prompted || apkResult?.needsManual || apkResult?.needsPermission) {
      return { ...apkResult, webResult };
    }

    const installedVersion = formatInstalledVersion(installed.versionName);
    const remoteWeb = String(manifest.web_bundle_version || "").trim();
    const remoteApk = String(manifest.apk_version || manifest.version || "").trim();
    const webOk = !remoteWeb || !versionIsOlder(installedWeb, remoteWeb);
    const apkOk = !remoteApk || !versionIsOlder(installedVersion, remoteApk);

    if (webOk && apkOk) {
      const parts = [];
      if (installedVersion) parts.push(`APK v${installedVersion}`);
      if (installedWeb) parts.push(`UI ${installedWeb}`);
      setUpdateStatus(parts.length ? `Up to date (${parts.join(" · ")})` : "Up to date", "ok");
      return { upToDate: true, installed, installedWeb, manifest, webResult, apkResult };
    }

    if (!webOk && webResult?.skipped && webResult?.reason === "ota_unsupported") {
      if (apkOk) {
        setUpdateStatus(
          installedVersion
            ? `Mining OK · APK v${installedVersion} (live UI OTA needs ${MIN_WEB_OTA_APK}+)`
            : `Mining OK · live UI OTA needs APK ${MIN_WEB_OTA_APK}+`,
          "warn",
        );
        return { upToDate: true, installed, installedWeb, manifest, webResult, apkResult };
      }
    }

    if (!webOk) {
      setUpdateStatus(`UI update ${remoteWeb} available — tap Check for updates`, "warn");
    } else if (!apkOk) {
      setUpdateStatus(`APK update ${remoteApk} available — tap Check for updates`, "warn");
    }
    return { updateAvailable: true, installed, installedWeb, manifest, webResult, apkResult };
  } catch (err) {
    setUpdateStatus(`Update check failed: ${err.message || err}`, "error");
    return { error: String(err.message || err) };
  } finally {
    updateInFlight = false;
  }
}

export function initAndroidUpdateOptions() {
  if (!isAndroidAppContext() || optionsHooked) return;
  optionsHooked = true;

  const panel = document.getElementById("android-options-panel");
  const strip = document.getElementById("android-update-strip");
  const checkbox = document.getElementById("android-auto-update");
  const checkBtns = document.querySelectorAll("#android-check-update-btn");

  if (panel) panel.hidden = false;
  if (strip) strip.hidden = false;
  if (checkbox) {
    checkbox.checked = isAndroidAutoUpdateEnabled();
    checkbox.addEventListener("change", () => {
      setAndroidAutoUpdateEnabled(checkbox.checked);
      setUpdateStatus(
        checkbox.checked
          ? "Automatic update check enabled on startup"
          : "Automatic update check disabled",
        "ok",
      );
    });
  }
  checkBtns.forEach((checkBtn) => {
    if (checkBtn.dataset.updateHooked === "1") return;
    checkBtn.dataset.updateHooked = "1";
    checkBtn.addEventListener("click", () => {
      void runAndroidUpdateCheck({ manual: true, force: true });
    });
  });
}

export async function initAndroidAppUpdate(options = {}) {
  if (!isAndroidAppContext()) return null;
  initAndroidUpdateOptions();
  try {
    const [installed, installedWeb] = await Promise.all([
      readInstalledVersion(),
      readInstalledWebBundleVersion(),
    ]);
    setVersionLine(installed.versionName, installedWeb);
  } catch (_) {
    setVersionLine("");
  }
  if (!isAndroidAutoUpdateEnabled()) {
    setUpdateStatus("Automatic updates off — tap Check for updates above", "warn");
    return null;
  }
  return runAndroidUpdateCheck(options);
}
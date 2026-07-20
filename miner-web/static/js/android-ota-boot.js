/**
 * Classic (non-module) Android OTA bootstrap — runs before web-miner.js so old APK
 * shells still get a visible update control and automatic UI bundle download.
 */
(function () {
  if (
    document.documentElement?.dataset?.desktopApp === "1"
    || document.body?.dataset?.desktopApp === "1"
    || window.__bloodstoneDesktopBridgeSealed
    || window.__bloodstoneDesktop
  ) {
    return;
  }
  try {
    if (window.Capacitor?.getPlatform?.() === "desktop") return;
  } catch (_) {
    /* ignore */
  }
  if (document.body?.dataset?.androidApp !== "1") return;

  var UPDATE_BASE = (document.body.dataset.updateBase || "https://bloodstonewallet.mytunnel.org").replace(/\/$/, "");
  var BETA_TOKEN_KEY = "bloodstone-beta-access-token";
  var bootInFlight = false;

  function getBetaAccessToken() {
    try {
      return localStorage.getItem(BETA_TOKEN_KEY) || "";
    } catch (e) {
      return "";
    }
  }

  function manifestRequest(url) {
    var token = getBetaAccessToken();
    var headers = { Accept: "application/json" };
    if (token) {
      headers["X-Bloodstone-Beta-Token"] = token;
    }
    var finalUrl = url;
    if (token) {
      finalUrl += (url.indexOf("?") >= 0 ? "&" : "?") + "beta_token=" + encodeURIComponent(token);
    }
    return { url: finalUrl, headers: headers };
  }

  function manifestUrls() {
    return [
      UPDATE_BASE + "/mining/api/android-miner/update",
      UPDATE_BASE + "/api/android-miner/update",
    ];
  }

  var MIN_WEB_UI = "1.3.73-web";

  function hasCurrentLayout() {
    return (
      document.body.getAttribute("data-ui-layout") === "v2"
      || !!document.getElementById("android-miner-controls")
    );
  }

  function bundledWebUiVersion() {
    return String(document.body.getAttribute("data-web-ui-version") || "").trim();
  }

  function needsWebLogicUpgrade() {
    var bundled = bundledWebUiVersion();
    if (!bundled) return true;
    return versionIsOlder(bundled, MIN_WEB_UI);
  }

  function setStatus(text, color) {
    var targets = document.querySelectorAll(
      "#bs-ota-status, #android-update-status, .android-update-status",
    );
    if (!targets.length && text) ensureStickyBar();
    targets.forEach(function (el) {
      el.textContent = text || "";
      el.hidden = !text;
      if (color) el.style.color = color;
    });
  }

  function ensureStickyBar() {
    if (document.getElementById("bs-ota-sticky")) return;
    var wrap = document.querySelector(".wrap");
    if (!wrap) return;
    var bar = document.createElement("div");
    bar.id = "bs-ota-sticky";
    bar.style.cssText =
      "position:sticky;top:0;z-index:10000;margin:-1rem -1rem 1rem -1rem;padding:12px 14px;"
      + "background:linear-gradient(180deg,#1e2a3d 0%,#141a24 100%);"
      + "border-bottom:2px solid #6eb5ff;box-shadow:0 4px 16px rgba(0,0,0,0.45);";
    bar.innerHTML =
      '<strong style="display:block;color:#6eb5ff;font-size:1rem;margin:0 0 6px;">'
      + "Get the latest miner screen</strong>"
      + '<p id="bs-ota-status" style="margin:0 0 10px;font-size:0.88rem;color:#c5d0e0;line-height:1.35;">'
      + "Mining controls and options download over Wi‑Fi — no reinstall needed.</p>"
      + '<button type="button" id="bs-ota-btn" style="display:block;width:100%;box-sizing:border-box;'
      + "background:#6eb5ff;color:#0d0f14;border:none;border-radius:8px;padding:12px 16px;"
      + 'font-weight:700;font-size:0.95rem;cursor:pointer;">Check for updates</button>'
      + '<a href="https://bloodstonewallet.mytunnel.org/downloads/" '
      + 'style="display:block;margin-top:10px;text-align:center;color:#8ec8ff;font-size:0.85rem;">'
      + "Or open Downloads page</a>";
    wrap.insertBefore(bar, wrap.firstChild);
  }

  function visibleUpdateButton() {
    var btn =
      document.getElementById("bs-ota-btn")
      || document.getElementById("android-check-update-btn")
      || document.querySelector(".android-check-update-btn");
    if (!btn) return null;
    var rect = btn.getBoundingClientRect();
    if (rect.width < 8 || rect.height < 8) return null;
    return btn;
  }

  function hookButtons(runUpdate) {
    document
      .querySelectorAll("#bs-ota-btn, #android-check-update-btn, .android-check-update-btn")
      .forEach(function (btn) {
        if (btn.dataset.otaHooked === "1") return;
        btn.dataset.otaHooked = "1";
        btn.addEventListener("click", function (event) {
          event.preventDefault();
          runUpdate({ manual: true });
        });
      });
  }

  function buildPluginAdapter() {
    var cap = window.Capacitor;
    if (!cap) return null;
    var raw = cap.Plugins && cap.Plugins.BloodstoneDevicePool;
    var hasNative = typeof cap.nativePromise === "function";
    var platform =
      typeof cap.getPlatform === "function" ? cap.getPlatform() : "";
    if (!raw && !hasNative && platform !== "android") return null;

    function call(method, args) {
      args = args || {};
      if (raw && typeof raw[method] === "function") {
        return raw[method](args);
      }
      if (hasNative) {
        return cap.nativePromise("BloodstoneDevicePool", method, args);
      }
      throw new Error("BloodstoneDevicePool." + method + " unavailable");
    }

    var adapter = {
      getWebBundleInfo: function () {
        return call("getWebBundleInfo");
      },
      downloadAndApplyWebBundle: function (opts) {
        return call("downloadAndApplyWebBundle", opts);
      },
      reloadApp: function () {
        return call("reloadApp");
      },
    };
    if ((raw && typeof raw.downloadAndInstallApk === "function") || hasNative) {
      adapter.downloadAndInstallApk = function (opts) {
        return call("downloadAndInstallApk", opts);
      };
    }
    if ((raw && typeof raw.canInstallApkUpdates === "function") || hasNative) {
      adapter.canInstallApkUpdates = function () {
        return call("canInstallApkUpdates");
      };
      adapter.requestInstallApkPermission = function () {
        return call("requestInstallApkPermission");
      };
    }
    return adapter;
  }

  function waitForPlugin(maxMs) {
    maxMs = maxMs || 45000;
    if (typeof window.__bloodstoneWaitForBridge === "function") {
      return window.__bloodstoneWaitForBridge(maxMs).then(function () {
        var adapter = buildPluginAdapter();
        if (adapter) return adapter;
        return waitForPluginPoll(maxMs);
      });
    }
    return waitForPluginPoll(maxMs);
  }

  function waitForPluginPoll(maxMs) {
    var deadline = Date.now() + maxMs;
    return new Promise(function (resolve) {
      (function poll() {
        var adapter = buildPluginAdapter();
        if (adapter) {
          resolve(adapter);
          return;
        }
        if (Date.now() >= deadline) {
          resolve(null);
          return;
        }
        setTimeout(poll, 150);
      })();
    });
  }

  function openApkDownloadFallback(manifest, reason) {
    var url =
      (manifest && (manifest.apk_url_latest || manifest.apk_url))
      || UPDATE_BASE + "/downloads/bloodstone-miner-android-latest.apk";
    var ver = (manifest && (manifest.apk_version || manifest.version)) || "latest";
    setStatus(
      (reason || "Native bridge not ready")
        + " — opening APK v"
        + ver
        + " download…",
      "#f0c674",
    );
    window.location.href = url;
  }

  function fetchJson(url, headers) {
    headers = headers || { Accept: "application/json" };
    var cap = window.Capacitor;
    if (cap && typeof cap.nativePromise === "function") {
      return cap
        .nativePromise("CapacitorHttp", "request", {
          url: url,
          method: "GET",
          headers: headers,
        })
        .then(function (response) {
          var status = Number(response && response.status) || 0;
          if (status < 200 || status >= 300) {
            throw new Error("HTTP " + status);
          }
          var raw = response && response.data;
          return typeof raw === "string" ? JSON.parse(raw) : raw;
        });
    }
    return fetch(url, { cache: "no-store", headers: headers }).then(function (res) {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.json();
    });
  }

  function fetchManifest() {
    var chain = Promise.reject(new Error("no manifest"));
    manifestUrls().forEach(function (url) {
      chain = chain.catch(function () {
        var req = manifestRequest(url);
        return fetchJson(req.url, req.headers).then(function (data) {
          if (!data || !data.ok || !data.web_bundle_url) {
            throw new Error("manifest incomplete");
          }
          return data;
        });
      });
    });
    return chain;
  }

  function parseVersion(value) {
    return String(value || "0")
      .split(".")
      .map(function (part) {
        return parseInt(part, 10) || 0;
      });
  }

  function versionIsOlder(localVersion, remoteVersion) {
    var local = String(localVersion || "").trim();
    var remote = String(remoteVersion || "").trim();
    if (!remote) return false;
    if (!local) return true;
    if (local === remote) return false;
    var left = parseVersion(local);
    var right = parseVersion(remote);
    var len = Math.max(left.length, right.length);
    for (var i = 0; i < len; i += 1) {
      var a = left[i] || 0;
      var b = right[i] || 0;
      if (a > b) return false;
      if (a < b) return true;
    }
    return local < remote;
  }

  function readInstalledWebVersion(plugin) {
    if (!plugin || typeof plugin.getWebBundleInfo !== "function") {
      return Promise.resolve("");
    }
    return plugin.getWebBundleInfo().then(function (info) {
      var version = String((info && info.version) || "").trim();
      if (version && info && info.active) return version;
      if (hasCurrentLayout()) {
        try {
          return localStorage.getItem("bloodstone-web-bundle-version") || version || "";
        } catch (e) {
          return version || "";
        }
      }
      return version || "";
    }).catch(function () {
      return "";
    });
  }

  function compareVersions(localVersion, remoteVersion) {
    var left = parseVersion(localVersion);
    var right = parseVersion(remoteVersion);
    var len = Math.max(left.length, right.length);
    for (var i = 0; i < len; i += 1) {
      var a = left[i] || 0;
      var b = right[i] || 0;
      if (a > b) return 1;
      if (a < b) return -1;
    }
    return 0;
  }

  function normalizeApkVersion(info) {
    if (!info || typeof info !== "object") return "";
    var name = String(info.versionName || "").trim();
    if (name && name !== "0") return name;
    var code = Number(info.versionCode) || 0;
    return code > 0 ? "build-" + code : "";
  }

  function probeApkVersionOnce() {
    var cap = window.Capacitor;
    if (!cap) return Promise.resolve("");
    if (typeof cap.nativePromise === "function") {
      return cap
        .nativePromise("BloodstoneDevicePool", "getAppVersion", {})
        .then(function (info) {
          return normalizeApkVersion(info);
        })
        .catch(function () {
          return "";
        });
    }
    var raw = cap.Plugins && cap.Plugins.BloodstoneDevicePool;
    if (raw && typeof raw.getAppVersion === "function") {
      return raw
        .getAppVersion()
        .then(function (info) {
          return normalizeApkVersion(info);
        })
        .catch(function () {
          return "";
        });
    }
    return Promise.resolve("");
  }

  function readInstalledApkVersion(maxMs) {
    maxMs = maxMs || 12000;
    var deadline = Date.now() + maxMs;
    return new Promise(function (resolve) {
      (function poll() {
        probeApkVersionOnce().then(function (version) {
          if (version) {
            resolve(version);
            return;
          }
          if (Date.now() >= deadline) {
            resolve("");
            return;
          }
          setTimeout(poll, 200);
        });
      })();
    });
  }

  function setVersionLines(apkVersion, webVersion) {
    var apk = String(apkVersion || "").trim();
    var web = String(webVersion || "").trim();
    var text =
      apk && web
        ? "Installed: APK v" + apk + " · UI " + web
        : apk
          ? "Installed: APK v" + apk
          : web
            ? "Installed UI: " + web + " (APK version loading…)"
            : "Installed version: reading…";
    document.querySelectorAll(".android-app-version-line, #android-app-version-line").forEach(function (el) {
      el.textContent = text;
    });
    if (apk) {
      document.body.setAttribute("data-native-apk-version", apk);
    }
  }

  function refreshVersionDisplay() {
    return waitForPlugin(8000).then(function (plugin) {
      return Promise.all([
        readInstalledApkVersion(10000),
        plugin ? readInstalledWebVersion(plugin) : Promise.resolve(""),
        fetchManifest().catch(function () {
          return null;
        }),
      ]).then(function (parts) {
        var apk = parts[0];
        var web = parts[1];
        var manifest = parts[2];
        setVersionLines(apk, web);
        if (!manifest) return;
        var remoteApk = String(manifest.apk_version || manifest.version || "").trim();
        if (apk && remoteApk && compareVersions(apk, remoteApk) < 0) {
          setStatus(
            "APK update available: v" + apk + " → v" + remoteApk + " — tap Check for updates",
            "#f0c674",
          );
        } else if (!apk && remoteApk) {
          setStatus(
            "Install APK v" + remoteApk + " from Downloads or tap Check for updates",
            "#f0c674",
          );
        }
      });
    });
  }

  function ensureApkInstallPermission(plugin) {
    if (!plugin || typeof plugin.canInstallApkUpdates !== "function") {
      return Promise.resolve(true);
    }
    return plugin
      .canInstallApkUpdates()
      .then(function (status) {
        if (status && status.allowed) return true;
        if (typeof plugin.requestInstallApkPermission === "function") {
          return plugin.requestInstallApkPermission().then(function () {
            return plugin.canInstallApkUpdates().then(function (retry) {
              return Boolean(retry && retry.allowed);
            });
          });
        }
        return false;
      })
      .catch(function () {
        return false;
      });
  }

  function applyApk(plugin, manifest, installedApk) {
    var remoteApk = String(manifest.apk_version || manifest.version || "").trim();
    var apkUrl = manifest.apk_url_latest || manifest.apk_url;
    if (!remoteApk || !apkUrl || !plugin || typeof plugin.downloadAndInstallApk !== "function") {
      return Promise.reject(new Error("APK update unavailable — open Downloads in browser"));
    }
    if (installedApk && compareVersions(installedApk, remoteApk) >= 0) {
      return Promise.resolve({ upToDate: true });
    }
    return ensureApkInstallPermission(plugin).then(function (allowed) {
      if (!allowed) {
        throw new Error('Allow "Install unknown apps" for Bloodstone, then tap Check for updates');
      }
      setStatus("Downloading APK " + remoteApk + "…", "#f0c674");
      return plugin.downloadAndInstallApk({ url: apkUrl }).then(function () {
        setStatus("Installer opened — confirm APK " + remoteApk, "#7dcea0");
      });
    });
  }

  function applyBundle(plugin, manifest) {
    var url = manifest.web_bundle_url_latest || manifest.web_bundle_url;
    var version = manifest.web_bundle_version;
    setStatus("Downloading UI " + version + "…", "#f0c674");
    return plugin
      .downloadAndApplyWebBundle({
        url: url,
        sha256: manifest.web_bundle_sha256 || "",
        version: version,
      })
      .then(function () {
        try {
          localStorage.setItem("bloodstone-web-bundle-version", version);
        } catch (e) {
          /* ignore */
        }
        setStatus("UI applied — reloading…", "#7dcea0");
        if (typeof plugin.reloadApp === "function") {
          return plugin.reloadApp();
        }
        window.location.reload();
      });
  }

  function runUpdate(options) {
    options = options || {};
    if (bootInFlight) return Promise.resolve();
    bootInFlight = true;
    setStatus("Checking for updates…", "#c5d0e0");
    return waitForPlugin()
      .then(function (plugin) {
        if (!plugin) {
          return fetchManifest().then(function (manifest) {
            openApkDownloadFallback(
              manifest,
              "Native update bridge not ready — install the latest APK",
            );
            return null;
          });
        }
        return Promise.all([
          readInstalledWebVersion(plugin),
          readInstalledApkVersion(),
          fetchManifest(),
        ]).then(function (parts) {
          var installedWeb = parts[0];
          var installedApk = parts[1];
          var manifest = parts[2];
          var remoteWeb = String(manifest.web_bundle_version || "").trim();
          var remoteApk = String(manifest.apk_version || manifest.version || "").trim();
          var layoutStale = !hasCurrentLayout() || needsWebLogicUpgrade();
          if (layoutStale) {
            try {
              localStorage.removeItem("bloodstone-web-bundle-version");
            } catch (e) {
              /* ignore */
            }
            installedWeb = "";
          }
          if (!layoutStale && !versionIsOlder(installedWeb, remoteWeb)) {
            var apkBehind =
              remoteApk && installedApk && compareVersions(installedApk, remoteApk) < 0;
            var apkUnknown = remoteApk && !installedApk;
            if (!apkBehind && !apkUnknown) {
              setStatus("Up to date (UI " + (installedWeb || remoteWeb) + ")", "#7dcea0");
              setVersionLines(installedApk, installedWeb);
              return null;
            }
            return applyApk(plugin, manifest, installedApk);
          }
          return applyBundle(plugin, manifest).catch(function (bundleErr) {
            if (remoteApk && installedApk && compareVersions(installedApk, remoteApk) < 0) {
              setStatus("Live UI download failed — trying APK " + remoteApk + "…", "#f0c674");
              return applyApk(plugin, manifest, installedApk);
            }
            throw bundleErr;
          });
        });
      })
      .catch(function (err) {
        var msg = (err && err.message) || String(err);
        if (/bridge not ready|plugin unavailable|unavailable/i.test(msg)) {
          fetchManifest()
            .then(function (manifest) {
              openApkDownloadFallback(manifest, msg);
            })
            .catch(function () {
              openApkDownloadFallback(null, msg);
            });
          return;
        }
        setStatus("Update failed: " + msg, "#f5a6a6");
      })
      .finally(function () {
        bootInFlight = false;
      });
  }

  function maybeAutoUpdate(plugin) {
    if (!plugin) return Promise.resolve();
    return fetchManifest()
      .then(function (manifest) {
        var remoteWeb = String(manifest.web_bundle_version || "").trim();
        if (!remoteWeb) return null;
        return readInstalledWebVersion(plugin).then(function (installedWeb) {
          var layoutStale = !hasCurrentLayout() || needsWebLogicUpgrade();
          if (!layoutStale && !versionIsOlder(installedWeb, remoteWeb)) {
            return null;
          }
          setStatus(
            "Downloading UI " + remoteWeb + (installedWeb ? " (was " + installedWeb + ")" : "") + "…",
            "#f0c674",
          );
          return runUpdate({ auto: true });
        });
      })
      .catch(function () {
        return null;
      });
  }

  function boot() {
    if (!visibleUpdateButton()) ensureStickyBar();
    hookButtons(runUpdate);
    setTimeout(function () {
      void refreshVersionDisplay();
    }, 400);
    setInterval(function () {
      void refreshVersionDisplay();
    }, 30000);
    if (!hasCurrentLayout()) {
      try {
        localStorage.removeItem("bloodstone-web-bundle-version");
      } catch (e) {
        /* ignore */
      }
      setStatus("New UI ready — tap the blue button above to download", "#f0c674");
      setTimeout(function () {
        runUpdate({ auto: true });
      }, 1200);
      return;
    }
    window.addEventListener("bloodstone-bridge-ready", function () {
      void refreshVersionDisplay();
      waitForPlugin(5000).then(maybeAutoUpdate);
    });
    setTimeout(function () {
      waitForPlugin().then(maybeAutoUpdate);
    }, 2500);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.__bloodstoneRunAndroidUpdate = runUpdate;
})();
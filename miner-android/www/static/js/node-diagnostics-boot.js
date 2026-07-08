/**
 * Standalone diagnostics bootstrap — runs on every Android app screen without waiting
 * for web-miner.js. Wires Run/Copy buttons and dynamic-imports node-diagnostics.js.
 */
(function () {
  if (document.body?.dataset?.androidApp !== "1") {
    try {
      if (window.Capacitor?.getPlatform?.() !== "android") return;
    } catch (_) {
      return;
    }
  }

  var hooked = false;
  var importPromise = null;

  function isAndroidApp() {
    if (document.body?.dataset?.androidApp === "1") return true;
    var params = new URLSearchParams(window.location.search);
    if (params.get("app") === "android") return true;
    try {
      return window.Capacitor?.getPlatform?.() === "android";
    } catch (_) {
      return false;
    }
  }

  if (!isAndroidApp()) return;

  function diagLog(msg, kind) {
    var text = String(msg || "");
    if (!text) return;
    var log = document.getElementById("miner-log");
    if (log) {
      var line = document.createElement("div");
      line.className =
        "log-line log-" + (kind === "error" ? "error" : kind === "warn" ? "warn" : "success");
      line.textContent = text;
      log.appendChild(line);
      log.scrollTop = log.scrollHeight;
      return;
    }
    var summary = document.getElementById("node-diag-summary");
    if (summary) {
      summary.textContent = text;
      summary.classList.remove("diag-ok", "diag-warn", "diag-error");
      if (kind === "error") summary.classList.add("diag-error");
      else if (kind === "warn") summary.classList.add("diag-warn");
      else if (kind === "success" || kind === "ok") summary.classList.add("diag-ok");
    }
  }

  function resolveDiagnosticsModuleUrl() {
    var webMiner = document.querySelector('script[src*="web-miner.js"]');
    if (webMiner && webMiner.src) {
      return webMiner.src.replace(/web-miner\.js[^/]*$/, "node-diagnostics.js");
    }
    var otaBoot = document.querySelector('script[src*="android-ota-boot.js"]');
    if (otaBoot && otaBoot.src) {
      return otaBoot.src.replace(/android-ota-boot\.js[^/]*$/, "node-diagnostics.js");
    }
    var prefix = String(document.body?.getAttribute("data-url-prefix") || "").replace(/\/$/, "");
    if (prefix && prefix.charAt(0) !== "/") prefix = "/" + prefix;
    var host = String(window.location.hostname || "").toLowerCase();
    if (host === "localhost" || host === "127.0.0.1" || host.endsWith(".localhost")) {
      return (window.location.origin || "") + "/static/js/node-diagnostics.js";
    }
    return (window.location.origin || "") + (prefix || "/mining") + "/static/js/node-diagnostics.js";
  }

  function loadDiagnosticsModule() {
    if (!importPromise) {
      var url = resolveDiagnosticsModuleUrl();
      importPromise = import(/* webpackIgnore: true */ url).catch(function (err) {
        importPromise = null;
        throw err;
      });
    }
    return importPromise;
  }

  function normalizePayload(raw) {
    if (raw == null) return null;
    if (typeof raw === "string") {
      try {
        return JSON.parse(raw);
      } catch (_) {
        return null;
      }
    }
    if (typeof raw !== "object") return null;
    if (raw.value != null && typeof raw.value === "object") return raw.value;
    return raw;
  }

  async function probeNative(pluginName, method, args) {
    var cap = window.Capacitor;
    if (!cap) return { ok: false, error: "Capacitor missing" };
    var raw = cap.Plugins && cap.Plugins[pluginName];
    if (raw && typeof raw[method] === "function") {
      try {
        return { ok: true, via: "Plugins", data: normalizePayload(await raw[method](args || {})) };
      } catch (err) {
        return { ok: false, via: "Plugins", error: String(err && err.message ? err.message : err) };
      }
    }
    if (typeof cap.nativePromise === "function") {
      try {
        return {
          ok: true,
          via: "nativePromise",
          data: normalizePayload(await cap.nativePromise(pluginName, method, args || {})),
        };
      } catch (err) {
        return {
          ok: false,
          via: "nativePromise",
          error: String(err && err.message ? err.message : err),
        };
      }
    }
    return { ok: false, error: "no bridge" };
  }

  async function runFallbackDiagnostics() {
    diagLog("Running built-in diagnostics (module unavailable)…", "warn");
    var cap = window.Capacitor;
    var lines = [];
    lines.push("=== Bloodstone built-in diagnostics " + new Date().toISOString() + " ===");
    lines.push("URL: " + window.location.href);
    lines.push(
      "Bridge: "
        + (cap ? "yes" : "no")
        + " platform="
        + (cap && cap.getPlatform ? cap.getPlatform() : "none")
        + " nativePromise="
        + (cap && typeof cap.nativePromise === "function" ? "yes" : "no"),
    );
    var plugins = ["BloodstoneLocalNode", "BloodstoneDevicePool", "BloodstoneStratum", "BloodstoneChainMesh"];
    lines.push(
      "Plugins: "
        + plugins
          .map(function (p) {
            return p + "=" + (cap && cap.Plugins && cap.Plugins[p] ? "Y" : "n");
          })
          .join(" "),
    );
    var apk = await probeNative("BloodstoneDevicePool", "getAppVersion");
    if (apk.ok && apk.data) {
      lines.push("APK: " + (apk.data.versionName || "?") + " (code " + (apk.data.versionCode || "?") + ")");
    }
    var status = await probeNative("BloodstoneLocalNode", "getLocalNodeStatus");
    lines.push(
      "getLocalNodeStatus: "
        + (status.ok ? "OK " + (status.via || "") : "FAIL " + (status.error || "")),
    );
    if (status.ok && status.data) {
      var s = status.data;
      lines.push(
        "Node: running="
          + s.running
          + " nodeStarting="
          + s.nodeStarting
          + " bloodstonedAlive="
          + s.bloodstonedAlive
          + " startError="
          + (s.startError || "—"),
      );
    }
    if (!status.ok) {
      lines.push("[error] Native node unreachable — use bundled miner (localhost/offline-mine.html), install APK 1.3.44+.");
    }
    var text = lines.join("\n");
    var body = document.getElementById("node-diag-body");
    if (body) body.textContent = text;
    var wrap = document.getElementById("node-diagnostics-wrap");
    if (wrap) {
      wrap.hidden = false;
      if (wrap.tagName === "DETAILS") wrap.open = true;
    }
    diagLog("Built-in diagnostics ready", "success");
    return text;
  }

  async function runDiagnostics() {
    var btn = document.getElementById("btn-node-diagnostics");
    if (btn) btn.disabled = true;
    try {
      var mod = await loadDiagnosticsModule();
      if (mod && typeof mod.runNodeDiagnostics === "function") {
        return await mod.runNodeDiagnostics({ onLog: diagLog, silent: false });
      }
      return await runFallbackDiagnostics();
    } catch (err) {
      diagLog("Module load failed: " + (err && err.message ? err.message : err), "warn");
      return await runFallbackDiagnostics();
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function copyReport() {
    try {
      var mod = await loadDiagnosticsModule();
      if (mod && typeof mod.formatDiagnosticsReport === "function") {
        var text = mod.formatDiagnosticsReport();
        if (text && text !== "No diagnostics run yet.") {
          await navigator.clipboard.writeText(text);
          diagLog("Diagnostic report copied", "success");
          return;
        }
      }
    } catch (_) {
      /* fall through */
    }
    var body = document.getElementById("node-diag-body");
    var text = body && body.textContent ? body.textContent.trim() : "";
    if (!text) {
      diagLog("Run diagnostics first", "warn");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      diagLog("Diagnostic report copied", "success");
    } catch (_) {
      diagLog("Copy failed — select text in panel manually", "warn");
    }
  }

  function ensureDiagnosticsPanel() {
    if (document.getElementById("node-diagnostics-wrap")) return;
    var anchor =
      document.getElementById("bs-ota-sticky")
      || document.querySelector(".wrap")
      || document.querySelector("main.container")
      || document.body;
    if (!anchor) return;
    var panel = document.createElement("details");
    panel.className = "node-diagnostics-panel";
    panel.id = "node-diagnostics-wrap";
    panel.open = true;
    panel.innerHTML =
      '<summary class="node-diagnostics-summary">Node diagnostics <span class="muted small">(if stuck on Starting)</span></summary>'
      + '<p class="node-diag-summary-line" id="node-diag-summary">Tap Run to check bridge, APK, and bloodstoned status.</p>'
      + '<div class="btn-row node-diag-actions">'
      + '<button type="button" class="btn btn-small" id="btn-node-diagnostics">Run diagnostics</button>'
      + '<button type="button" class="btn btn-small btn-ghost" id="btn-node-diag-copy">Copy report</button>'
      + "</div>"
      + '<pre class="node-diag-body mono" id="node-diag-body" aria-label="Diagnostic report"></pre>';
    anchor.appendChild(panel);
  }

  function wireDiagnostics() {
    if (hooked) return;
    ensureDiagnosticsPanel();
    var runBtn = document.getElementById("btn-node-diagnostics");
    if (!runBtn || runBtn.dataset.diagBootHooked === "1") return;
    runBtn.dataset.diagBootHooked = "1";
    hooked = true;
    runBtn.addEventListener("click", function (event) {
      event.preventDefault();
      void runDiagnostics();
    });
    var copyBtn = document.getElementById("btn-node-diag-copy");
    if (copyBtn && copyBtn.dataset.diagBootHooked !== "1") {
      copyBtn.dataset.diagBootHooked = "1";
      copyBtn.addEventListener("click", function (event) {
        event.preventDefault();
        void copyReport();
      });
    }
    var wrap = document.getElementById("node-diagnostics-wrap");
    if (wrap) wrap.hidden = false;
  }

  function boot() {
    wireDiagnostics();
    setTimeout(wireDiagnostics, 500);
    setTimeout(wireDiagnostics, 2500);
    loadDiagnosticsModule()
      .then(function (mod) {
        if (mod && typeof mod.initNodeDiagnostics === "function") {
          mod.initNodeDiagnostics({ onLog: diagLog });
        }
      })
      .catch(function () {
        /* fallback wired above */
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.__bloodstoneRunNodeDiagnostics = runDiagnostics;
})();
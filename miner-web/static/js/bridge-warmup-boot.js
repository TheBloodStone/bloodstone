/**
 * Warm up Capacitor native bridge on Android — remote portal pages often load JS
 * before Bloodstone plugins register. Other boot scripts await __bloodstoneWaitForBridge().
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
  if (document.body?.dataset?.androidApp !== "1") {
    try {
      if (window.Capacitor?.getPlatform?.() !== "android") return;
    } catch (_) {
      return;
    }
  }

  var CORE_PLUGINS = [
    "BloodstoneDevicePool",
    "BloodstoneLocalNode",
    "BloodstoneStratum",
    "BloodstoneChainMesh",
  ];

  var state = {
    ready: false,
    platform: "none",
    nativePromise: false,
    plugins: {},
    lastProbe: "",
    readyAt: 0,
  };

  function normalizeInfo(raw) {
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

  function snapshotBridge() {
    var cap = window.Capacitor;
    if (!cap) return false;
    state.platform =
      typeof cap.getPlatform === "function" ? cap.getPlatform() : "unknown";
    state.nativePromise = typeof cap.nativePromise === "function";
    for (var i = 0; i < CORE_PLUGINS.length; i += 1) {
      var name = CORE_PLUGINS[i];
      state.plugins[name] = Boolean(cap.Plugins && cap.Plugins[name]);
    }
    return state.platform === "android" || state.nativePromise;
  }

  function probeOnce() {
    var cap = window.Capacitor;
    if (!cap) return Promise.resolve(false);
    snapshotBridge();
    if (state.nativePromise) {
      return cap
        .nativePromise("BloodstoneDevicePool", "getAppVersion", {})
        .then(function (info) {
          var data = normalizeInfo(info);
          if (data && data.versionName) {
            state.lastProbe = "getAppVersion:" + data.versionName;
            state.ready = true;
            state.readyAt = Date.now();
            document.body?.setAttribute("data-native-apk-version", String(data.versionName));
            return true;
          }
          return false;
        })
        .catch(function () {
          return false;
        });
    }
    var raw = cap.Plugins && cap.Plugins.BloodstoneDevicePool;
    if (raw && typeof raw.getAppVersion === "function") {
      return raw
        .getAppVersion()
        .then(function (info) {
          var data = normalizeInfo(info);
          if (data && data.versionName) {
            state.lastProbe = "plugin.getAppVersion:" + data.versionName;
            state.ready = true;
            state.readyAt = Date.now();
            document.body?.setAttribute("data-native-apk-version", String(data.versionName));
            return true;
          }
          return false;
        })
        .catch(function () {
          return false;
        });
    }
    if (state.plugins.BloodstoneDevicePool || state.plugins.BloodstoneLocalNode) {
      state.lastProbe = "plugin-registered";
      state.ready = true;
      state.readyAt = Date.now();
      return Promise.resolve(true);
    }
    return Promise.resolve(false);
  }

  function waitForBridge(maxMs) {
    maxMs = maxMs || 45000;
    if (state.ready) return Promise.resolve(state);
    var deadline = Date.now() + maxMs;
    return new Promise(function (resolve) {
      (function tick() {
        probeOnce().then(function (ok) {
          if (ok || state.ready) {
            resolve(state);
            return;
          }
          if (Date.now() >= deadline) {
            snapshotBridge();
            resolve(state);
            return;
          }
          setTimeout(tick, 150);
        });
      })();
    });
  }

  function boot() {
    snapshotBridge();
    void waitForBridge(60000).then(function () {
      if (state.ready) {
        try {
          window.dispatchEvent(new CustomEvent("bloodstone-bridge-ready", { detail: state }));
        } catch (_) {
          /* ignore */
        }
      }
    });
    setInterval(function () {
      if (!state.ready) void probeOnce();
    }, 5000);
  }

  window.__bloodstoneBridgeState = state;
  window.__bloodstoneWaitForBridge = waitForBridge;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
/**
 * Desktop Electron — preserve Capacitor preload bridge before Android warmup runs.
 */
(function () {
  function isDesktop() {
    try {
      return (
        window.__bloodstoneDesktopBridgeSealed === true
        || Boolean(window.__bloodstoneDesktop)
        || document.documentElement?.dataset?.desktopApp === "1"
        || document.body?.dataset?.desktopApp === "1"
        || window.Capacitor?.getPlatform?.() === "desktop"
      );
    } catch (_) {
      return false;
    }
  }

  if (!isDesktop()) return;

  function sealBridge() {
    var cap = window.Capacitor;
    if (!cap || typeof cap.nativePromise !== "function") return false;
    var state = {
      ready: true,
      platform: "desktop",
      nativePromise: true,
      plugins: {
        BloodstoneDevicePool: Boolean(cap.Plugins?.BloodstoneDevicePool),
        BloodstoneLocalNode: Boolean(cap.Plugins?.BloodstoneLocalNode),
        BloodstoneStratum: Boolean(cap.Plugins?.BloodstoneStratum),
        BloodstoneChainMesh: Boolean(cap.Plugins?.BloodstoneChainMesh),
      },
      lastProbe: "desktop-bridge-boot",
      readyAt: Date.now(),
    };
    window.__bloodstoneBridgeState = state;
    window.__bloodstoneWaitForBridge = function () {
      return Promise.resolve(state);
    };
    window.__bloodstoneDesktopBridgeSealed = true;
    try {
      window.dispatchEvent(
        new CustomEvent("bloodstone-bridge-ready", { detail: state }),
      );
    } catch (_) {
      /* ignore */
    }
    return true;
  }

  if (sealBridge()) return;

  var tries = 0;
  var timer = setInterval(function () {
    tries += 1;
    if (sealBridge() || tries >= 80) {
      clearInterval(timer);
      if (tries >= 80 && !window.__bloodstoneDesktopBridgeSealed) {
        var banner = document.getElementById("chain-sync-banner");
        if (banner) {
          banner.textContent =
            "Desktop native bridge missing — reinstall Bloodstone Miner desktop v1.3.80+ from Downloads";
          banner.className = "error";
        }
      }
    }
  }, 100);
})();
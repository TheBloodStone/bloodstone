const fs = require("fs");
const path = require("path");

const LEGACY_NODE_GUI_NAMES = new Set([
  "bloodstone-node-gui",
  "Bloodstone Node",
]);

function readPackageVersion() {
  try {
    const pkg = require("../../package.json");
    return pkg.version || "0.0.0";
  } catch (_) {
    return "0.0.0";
  }
}

function detectLegacyNodeGuiInstall() {
  if (process.platform !== "win32") {
    return false;
  }
  const localAppData = process.env.LOCALAPPDATA;
  if (!localAppData) {
    return false;
  }
  const programsRoot = path.join(localAppData, "Programs");
  if (!fs.existsSync(programsRoot)) {
    return false;
  }
  try {
    for (const entry of fs.readdirSync(programsRoot)) {
      if (LEGACY_NODE_GUI_NAMES.has(entry)) {
        return true;
      }
    }
  } catch (_) {
    return false;
  }
  return false;
}

function migrateLegacySettings(settings) {
  const next = { ...settings };
  let migrated = false;
  const guiVersion = readPackageVersion();

  if (!next.walletRpcPreference) {
    next.walletRpcPreference = "auto";
  }

  if (!next.walletGuiVersion) {
    const hadNodeGuiUse =
      !!next.firstRunComplete ||
      !!next.rpcProfile ||
      detectLegacyNodeGuiInstall();

    if (hadNodeGuiUse) {
      migrated = true;
      next.legacyNodeGuiMigrated = true;
      if (next.rpcProfile !== "vps") {
        next.walletRpcPreference = "local";
        if (!next.rpcProfile) {
          next.rpcProfile = "local";
        }
      }
      next.showLegacyMigrationNotice = true;
    }
    next.walletGuiVersion = guiVersion;
  } else if (next.walletGuiVersion !== guiVersion) {
    next.walletGuiVersion = guiVersion;
  }

  return { settings: next, migrated };
}

module.exports = {
  migrateLegacySettings,
  detectLegacyNodeGuiInstall,
  readPackageVersion,
};
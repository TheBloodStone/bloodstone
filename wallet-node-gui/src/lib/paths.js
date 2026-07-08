const path = require("path");
const fs = require("fs");
const os = require("os");

const APP_NAME = "Bloodstone";
const VPS_HOST = "64.188.22.190";
const SECONDARY_SEED = "192.119.82.145";
const DEFAULT_SEED = `${VPS_HOST}:17333`;
const DEFAULT_SEEDS = [DEFAULT_SEED, `${SECONDARY_SEED}:17333`];
const DEFAULT_RPC_PORT = 18332;
const DEFAULT_P2P_PORT = 17333;
const VPS_RPC_USER = "bloodstone";
const DEFAULT_WALLET_WEB_URL = "https://bloodstonewallet.mytunnel.org/wallet";
const NODE_CORE_VERSION = "0.7.5";
const DEFAULT_DOWNLOAD_ROOT = "https://bloodstonewallet.mytunnel.org";

const DAEMON_NAMES = ["bloodstoned.exe", "bloodstoned"];

const CLI_NAMES = ["bloodstone-cli.exe", "bloodstone-cli"];

function isWindows() {
  return process.platform === "win32";
}

function defaultDataDir() {
  if (isWindows()) {
    const base = process.env.APPDATA || path.join(os.homedir(), "AppData", "Roaming");
    return path.join(base, "Bloodstone");
  }
  return path.join(os.homedir(), ".bloodstone");
}

function localBinDir(dataDir) {
  return path.join(dataDir || defaultDataDir(), "bin");
}

function bundledBinDirs(resourcesPath) {
  const bin = path.join(resourcesPath, "bin");
  return [bin, path.join(bin, "win64"), path.join(resourcesPath, "bin", "win64")];
}

function resourceRoots() {
  const roots = [];
  if (process.resourcesPath) {
    roots.push(process.resourcesPath);
  }
  const execDir = path.dirname(process.execPath);
  roots.push(path.join(execDir, "resources"));
  roots.push(execDir);
  return [...new Set(roots)];
}

function firstExisting(candidates) {
  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

function daemonSearchPaths(resourcesPath, userBinPath, dataDir) {
  const candidates = [];
  if (userBinPath) {
    candidates.push(userBinPath);
  }
  if (dataDir) {
    for (const name of DAEMON_NAMES) {
      candidates.push(path.join(localBinDir(dataDir), name));
    }
  }
  for (const root of [resourcesPath, ...resourceRoots()]) {
    for (const bundled of bundledBinDirs(root)) {
      for (const name of DAEMON_NAMES) {
        candidates.push(path.join(bundled, name));
      }
    }
    for (const name of DAEMON_NAMES) {
      candidates.push(path.join(root, name));
    }
  }
  for (const name of DAEMON_NAMES) {
    candidates.push(path.join(process.cwd(), name));
    candidates.push(path.join(path.dirname(process.execPath), name));
    candidates.push(path.join(path.dirname(process.execPath), "resources", "bin", name));
  }
  return candidates;
}

function resolveDaemonPath(resourcesPath, userBinPath, dataDir) {
  return (
    firstExisting(daemonSearchPaths(resourcesPath, userBinPath, dataDir)) ||
    path.join(localBinDir(dataDir), DAEMON_NAMES[0])
  );
}

function resolveCliPath(daemonPath) {
  const dir = path.dirname(daemonPath);
  return firstExisting(CLI_NAMES.map((name) => path.join(dir, name))) || path.join(dir, CLI_NAMES[0]);
}

function hasBundledDaemon(resourcesPath) {
  return !!firstExisting(daemonSearchPaths(resourcesPath, ""));
}

module.exports = {
  APP_NAME,
  VPS_HOST,
  SECONDARY_SEED,
  DEFAULT_SEED,
  DEFAULT_SEEDS,
  DEFAULT_RPC_PORT,
  DEFAULT_P2P_PORT,
  VPS_RPC_USER,
  DEFAULT_WALLET_WEB_URL,
  NODE_CORE_VERSION,
  DEFAULT_DOWNLOAD_ROOT,
  DAEMON_NAMES,
  CLI_NAMES,
  isWindows,
  defaultDataDir,
  localBinDir,
  resolveDaemonPath,
  resolveCliPath,
  hasBundledDaemon,
};
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const {
  DEFAULT_SEED,
  DEFAULT_RPC_PORT,
  DEFAULT_P2P_PORT,
  VPS_RPC_USER,
  VPS_HOST,
  DEFAULT_WALLET_WEB_URL,
  NODE_CORE_VERSION,
  DEFAULT_DOWNLOAD_ROOT,
} = require("./paths");

const { migrateLegacySettings } = require("./settings-migrate");

const SETTINGS_FILE = "gui-settings.json";

function randomRpcPassword() {
  return crypto.randomBytes(24).toString("hex");
}

function loadVpsRpcDefaults() {
  const candidates = [
    path.join(__dirname, "..", "..", "resources", "vps-rpc.defaults.json"),
    path.join(process.resourcesPath || "", "vps-rpc.defaults.json"),
  ];
  for (const file of candidates) {
    if (file && fs.existsSync(file)) {
      try {
        return JSON.parse(fs.readFileSync(file, "utf8"));
      } catch (_) {
        /* ignore */
      }
    }
  }
  return null;
}

function captureLocalRpcCredentials(settings) {
  const confCreds = readConfCredentials(settings.dataDir);
  if (confCreds) {
    settings.localRpcUser = confCreds.rpcUser;
    settings.localRpcPassword = confCreds.rpcPassword;
    if (confCreds.rpcPort) {
      settings.localRpcPort = confCreds.rpcPort;
    }
  } else if (!settings.localRpcPassword) {
    const fromActiveProfile = settings.rpcProfile !== "vps";
    settings.localRpcUser =
      settings.localRpcUser ||
      (fromActiveProfile ? settings.rpcUser : null) ||
      VPS_RPC_USER;
    settings.localRpcPassword =
      settings.localRpcPassword ||
      (fromActiveProfile ? settings.rpcPassword : null) ||
      randomRpcPassword();
    settings.localRpcPort =
      settings.localRpcPort ||
      (fromActiveProfile ? settings.rpcPort : null) ||
      DEFAULT_RPC_PORT;
  }
  return settings;
}

function localConfCredentials(settings) {
  const confCreds = readConfCredentials(settings.dataDir);
  if (confCreds) {
    return confCreds;
  }
  return {
    rpcUser: settings.localRpcUser || settings.rpcUser || VPS_RPC_USER,
    rpcPassword: settings.localRpcPassword || settings.rpcPassword,
    rpcPort: settings.localRpcPort || settings.rpcPort || DEFAULT_RPC_PORT,
  };
}

/** Credentials for JSON-RPC. Local host always reads bloodstone.conf (source of truth). */
function activeRpcCredentials(settings) {
  const base = settings || {};
  const host = String(base.rpcHost || "127.0.0.1").trim().toLowerCase();
  if (host === "127.0.0.1" || host === "localhost" || host === "::1") {
    const local = localConfCredentials(captureLocalRpcCredentials({ ...base }));
    return {
      rpcHost: "127.0.0.1",
      rpcPort: local.rpcPort || DEFAULT_RPC_PORT,
      rpcUser: local.rpcUser,
      rpcPassword: local.rpcPassword,
      rpcProfile: base.rpcProfile || "local",
    };
  }
  return {
    rpcHost: base.rpcHost,
    rpcPort: base.rpcPort || DEFAULT_RPC_PORT,
    rpcUser: base.rpcUser || VPS_RPC_USER,
    rpcPassword: base.rpcPassword || "",
    rpcProfile: base.rpcProfile || "vps",
  };
}

function syncLocalRpcFromConf(settings) {
  const local = localConfCredentials(captureLocalRpcCredentials({ ...settings }));
  settings.localRpcUser = local.rpcUser;
  settings.localRpcPassword = local.rpcPassword;
  settings.localRpcPort = local.rpcPort || settings.localRpcPort || DEFAULT_RPC_PORT;
  if (settings.rpcProfile === "local") {
    settings.rpcUser = local.rpcUser;
    settings.rpcPassword = local.rpcPassword;
    settings.rpcPort = local.rpcPort || settings.rpcPort || DEFAULT_RPC_PORT;
    settings.rpcHost = "127.0.0.1";
  }
  return settings;
}

function defaultSettings(dataDir) {
  const rpcPassword = randomRpcPassword();
  return {
    dataDir,
    rpcProfile: "local",
    rpcHost: "127.0.0.1",
    rpcUser: VPS_RPC_USER,
    rpcPassword,
    localRpcUser: VPS_RPC_USER,
    localRpcPassword: rpcPassword,
    localRpcPort: DEFAULT_RPC_PORT,
    rpcPort: DEFAULT_RPC_PORT,
    p2pPort: DEFAULT_P2P_PORT,
    addnode: DEFAULT_SEED,
    allowMiningWhenNotConnected: true,
    daemonPath: "",
    minimizeToTray: true,
    startMinimized: false,
    firstRunComplete: false,
    walletWebUrl: DEFAULT_WALLET_WEB_URL,
    usersDbPath: "",
    walletRpcPreference: "auto",
    walletGuiVersion: "",
    legacyNodeGuiMigrated: false,
    showLegacyMigrationNotice: false,
    nodeCoreVersion: NODE_CORE_VERSION,
    downloadBaseUrl: DEFAULT_DOWNLOAD_ROOT,
  };
}

function applyVpsPreset(settings) {
  const preserved = captureLocalRpcCredentials({ ...settings });
  const vpsDefaults = loadVpsRpcDefaults();
  return {
    ...preserved,
    rpcProfile: "vps",
    walletRpcPreference: "vps",
    rpcHost: VPS_HOST,
    rpcUser: vpsDefaults?.rpcUser || VPS_RPC_USER,
    rpcPassword: vpsDefaults?.rpcPassword || preserved.rpcPassword || randomRpcPassword(),
    addnode: DEFAULT_SEED,
    rpcPort: vpsDefaults?.rpcPort || DEFAULT_RPC_PORT,
    p2pPort: DEFAULT_P2P_PORT,
  };
}

function applyLocalRpcPreset(settings) {
  const preserved = captureLocalRpcCredentials({ ...settings });
  const local = localConfCredentials(preserved);
  return {
    ...preserved,
    rpcProfile: "local",
    walletRpcPreference: "local",
    rpcHost: "127.0.0.1",
    rpcUser: local.rpcUser,
    rpcPassword: local.rpcPassword,
    rpcPort: local.rpcPort || DEFAULT_RPC_PORT,
  };
}

function publicSettings(settings) {
  if (!settings) {
    return settings;
  }
  const { rpcUser, rpcPassword, ...safe } = settings;
  return {
    ...safe,
    rpcConfigured: Boolean(rpcUser && rpcPassword),
    rpcProfile: settings.rpcProfile || "local",
  };
}

function settingsPath(dataDir) {
  return path.join(dataDir, SETTINGS_FILE);
}

function readConfCredentials(dataDir) {
  const confPath = path.join(dataDir, "bloodstone.conf");
  if (!fs.existsSync(confPath)) {
    return null;
  }
  const text = fs.readFileSync(confPath, "utf8");
  const rpcUser = text.match(/^rpcuser\s*=\s*(.+)$/m)?.[1]?.trim();
  const rpcPassword = text.match(/^rpcpassword\s*=\s*(.+)$/m)?.[1]?.trim();
  const rpcPort = text.match(/^rpcport\s*=\s*(\d+)$/m)?.[1];
  if (!rpcUser || !rpcPassword) {
    return null;
  }
  return {
    rpcUser,
    rpcPassword,
    rpcPort: rpcPort ? Number(rpcPort) : undefined,
  };
}

function loadSettings(dataDir) {
  const file = settingsPath(dataDir);
  let settings = defaultSettings(dataDir);
  if (fs.existsSync(file)) {
    try {
      const raw = JSON.parse(fs.readFileSync(file, "utf8"));
      settings = { ...settings, ...raw, dataDir };
    } catch (_) {
      /* use defaults */
    }
  }
  settings = syncLocalRpcFromConf(captureLocalRpcCredentials(settings));
  const outdatedNodeVersions = new Set(["0.6.8.9", "0.6.9.0", "0.6.9.1"]);
  if (!settings.nodeCoreVersion || outdatedNodeVersions.has(settings.nodeCoreVersion)) {
    settings.nodeCoreVersion = NODE_CORE_VERSION;
  }
  if (settings.rpcProfile === "local") {
    syncLocalRpcFromConf(settings);
  }
  const migration = migrateLegacySettings(settings);
  settings = migration.settings;
  if (migration.migrated) {
    saveSettings(settings);
  }
  return settings;
}

function saveSettings(settings) {
  const dir = settings.dataDir;
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(settingsPath(dir), JSON.stringify(settings, null, 2), "utf8");
}

function buildConfContent(settings) {
  const lines = [
    "# Bloodstone Node — generated by Bloodstone Node GUI",
    `rpcuser=${settings.rpcUser}`,
    `rpcpassword=${settings.rpcPassword}`,
    `rpcport=${settings.rpcPort}`,
    "rpcbind=127.0.0.1",
    "rpcallowip=127.0.0.1",
    `port=${settings.p2pPort}`,
    "chain=main",
    `addnode=${settings.addnode}`,
    `connect=${settings.addnode}`,
    "server=1",
    "txindex=1",
    "daemon=0",
    "listen=1",
    "bind=0.0.0.0",
    "dnsseed=1",
    "fixedseeds=0",
  ];
  if (settings.allowMiningWhenNotConnected) {
    lines.push("allowminingwhennotconnected=1");
  }
  lines.push("");
  return lines.join("\n");
}

function ensureConf(settings) {
  fs.mkdirSync(settings.dataDir, { recursive: true });
  const confPath = path.join(settings.dataDir, "bloodstone.conf");
  if (!fs.existsSync(confPath)) {
    fs.writeFileSync(confPath, buildConfContent(settings), "utf8");
  }
  return confPath;
}

function stripAutoWalletLines(dataDir) {
  const confPath = path.join(dataDir, "bloodstone.conf");
  if (!fs.existsSync(confPath)) {
    return { changed: false, removed: [] };
  }
  const lines = fs.readFileSync(confPath, "utf8").split(/\r?\n/);
  const removed = [];
  const kept = lines.filter((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      return true;
    }
    if (/^wallet\s*=/i.test(trimmed)) {
      removed.push(trimmed);
      return false;
    }
    return true;
  });
  if (!removed.length) {
    return { changed: false, removed };
  }
  fs.writeFileSync(confPath, `${kept.join("\n").replace(/\n*$/, "\n")}`, "utf8");
  return { changed: true, removed };
}

function writeConf(settings) {
  const confPath = path.join(settings.dataDir, "bloodstone.conf");
  fs.mkdirSync(settings.dataDir, { recursive: true });
  stripAutoWalletLines(settings.dataDir);
  const local = localConfCredentials(captureLocalRpcCredentials({ ...settings }));
  const forConf = {
    ...settings,
    rpcUser: local.rpcUser,
    rpcPassword: local.rpcPassword,
    rpcPort: local.rpcPort || settings.rpcPort || DEFAULT_RPC_PORT,
    localRpcUser: local.rpcUser,
    localRpcPassword: local.rpcPassword,
    localRpcPort: local.rpcPort || settings.rpcPort || DEFAULT_RPC_PORT,
  };
  fs.writeFileSync(confPath, buildConfContent(forConf), "utf8");
  return confPath;
}

module.exports = {
  loadSettings,
  saveSettings,
  ensureConf,
  writeConf,
  buildConfContent,
  readConfCredentials,
  defaultSettings,
  applyVpsPreset,
  applyLocalRpcPreset,
  activeRpcCredentials,
  captureLocalRpcCredentials,
  localConfCredentials,
  syncLocalRpcFromConf,
  publicSettings,
  stripAutoWalletLines,
};
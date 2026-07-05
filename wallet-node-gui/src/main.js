const {
  app,
  BrowserWindow,
  ipcMain,
  dialog,
  shell,
  Tray,
  Menu,
  nativeImage,
} = require("electron");
const path = require("path");
const fs = require("fs");
const { NodeManager } = require("./lib/node-manager");
const {
  loadSettings,
  saveSettings,
  writeConf,
  defaultSettings,
  applyVpsPreset,
  applyLocalRpcPreset,
  syncLocalRpcFromConf,
  publicSettings,
} = require("./lib/config");
const { defaultDataDir, hasBundledDaemon } = require("./lib/paths");
const {
  login,
  normalizeWalletWebUrl,
  setActiveWalletViaApi,
  giftStatusViaApi,
  giftListViaApi,
  giftCreateViaApi,
  giftRedeemViaApi,
  giftRevealViaApi,
  referralsDashboardViaApi,
  referralsLiveViaApi,
  referralsDiscordConnectViaApi,
} = require("./lib/auth");
const { WalletRpc } = require("./lib/wallet-rpc");
const {
  walletsForUser,
  walletNamesForUser,
  useVpsWalletRpc,
  requiresVpsRpc,
  activeWalletForUser,
  vpsRpcActive,
  prefersLocalNodeRpc,
  shouldAutoApplyVps,
} = require("./lib/wallet-policy");
const {
  makeVpsRpc,
  makeLocalRpc,
  listWalletsOn,
  listUserWalletsViaApi,
  importWalletFromVps,
} = require("./lib/wallet-importer");

let mainWindow = null;
let tray = null;
let nodeManager = null;
let walletRpc = null;
let settings = null;
let walletSession = null;
let walletSessionPassword = null;

const isDev = !app.isPackaged;

function resourcesPath() {
  if (isDev) {
    return path.join(__dirname, "..");
  }
  const candidates = [
    process.resourcesPath,
    path.join(path.dirname(process.execPath), "resources"),
    path.dirname(process.execPath),
  ];
  for (const candidate of candidates) {
    if (hasBundledDaemon(candidate)) {
      return candidate;
    }
  }
  return process.resourcesPath;
}

function iconPath() {
  const ico = path.join(__dirname, "..", "assets", "icon.png");
  if (fs.existsSync(ico)) {
    return ico;
  }
  return undefined;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 980,
    height: 700,
    minWidth: 820,
    minHeight: 560,
    title: "Bloodstone Wallet & Node",
    icon: iconPath(),
    backgroundColor: "#0f1419",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));

  mainWindow.on("close", (event) => {
    if (settings?.minimizeToTray && !app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
}

function createTray() {
  const icon = iconPath();
  if (!icon) {
    return;
  }
  tray = new Tray(nativeImage.createFromPath(icon));
  const contextMenu = Menu.buildFromTemplate([
    {
      label: "Show Bloodstone Wallet & Node",
      click: () => mainWindow?.show(),
    },
    {
      label: "Start Node",
      click: async () => {
        await nodeManager?.start();
      },
    },
    {
      label: "Stop Node",
      click: async () => {
        await nodeManager?.stop();
      },
    },
    { type: "separator" },
    {
      label: "Quit",
      click: () => {
        app.isQuitting = true;
        app.quit();
      },
    },
  ]);
  tray.setToolTip("Bloodstone Wallet & Node");
  tray.setContextMenu(contextMenu);
  tray.on("double-click", () => mainWindow?.show());
}

function initSettings() {
  const dataDir = defaultDataDir();
  settings = syncLocalRpcFromConf(loadSettings(dataDir));
  settings.walletWebUrl = normalizeWalletWebUrl(settings.walletWebUrl);
  nodeManager = new NodeManager(resourcesPath());
  nodeManager.configure(settings);
  walletRpc = new WalletRpc(() => settings);

  nodeManager.onLog((line) => {
    mainWindow?.webContents.send("node:log", line);
  });
  nodeManager.onStatus((status) => {
    mainWindow?.webContents.send("node:status", status);
  });
}

function registerIpc() {
  ipcMain.handle("settings:get", () => {
    const pub = publicSettings(settings);
    if (settings.showLegacyMigrationNotice) {
      pub.showLegacyMigrationNotice = true;
      settings.showLegacyMigrationNotice = false;
      saveSettings(settings);
    }
    return pub;
  });

  ipcMain.handle("settings:save", async (_evt, next) => {
    const { rpcUser, rpcPassword, rpcConfigured, ...safe } = next || {};
    if (!String(safe.walletWebUrl || "").trim()) {
      delete safe.walletWebUrl;
    }
    if (!String(safe.usersDbPath || "").trim()) {
      safe.usersDbPath = "";
    }
    if (safe.walletWebUrl) {
      safe.walletWebUrl = normalizeWalletWebUrl(safe.walletWebUrl);
    }
    settings = syncLocalRpcFromConf({ ...settings, ...safe });
    saveSettings(settings);
    writeConf(settings);
    nodeManager.configure(settings);
    return publicSettings(settings);
  });

  ipcMain.handle("settings:use-vps", async () => {
    settings = applyVpsPreset(settings);
    saveSettings(settings);
    nodeManager.configure(settings);
    return publicSettings(settings);
  });

  ipcMain.handle("settings:use-local-rpc", async () => {
    const wasRunning = nodeManager.isRunning();
    if (wasRunning) {
      await nodeManager.stop();
    }
    settings = syncLocalRpcFromConf(applyLocalRpcPreset(settings));
    saveSettings(settings);
    writeConf(settings);
    nodeManager.configure(settings);
    const pub = publicSettings(settings);
    pub.message = wasRunning
      ? "Switched to local node. The node was stopped — click Start Node to run with your local RPC settings."
      : "Switched to local node. Click Start Node when you are ready to sync on this PC.";
    return pub;
  });

  ipcMain.handle("settings:reset", async () => {
    const dataDir = settings.dataDir || defaultDataDir();
    settings = defaultSettings(dataDir);
    saveSettings(settings);
    writeConf(settings);
    nodeManager.configure(settings);
    return publicSettings(settings);
  });

  ipcMain.handle("node:start", async () => {
    try {
      return await nodeManager.start();
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });
  ipcMain.handle("node:stop", async () => {
    try {
      return await nodeManager.stop();
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });
  ipcMain.handle("node:status", async () => nodeManager.fetchStatus());
  ipcMain.handle("node:running", () => nodeManager.isRunning());
  ipcMain.handle("node:repair-sync", async () => {
    nodeManager.resetSyncRecovery();
    try {
      return await nodeManager.attemptSyncRecovery("manual repair", true);
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("node:reset-chain-data", async () => {
    const dataDir = settings?.dataDir || "your Bloodstone data folder";
    const genesisMismatch = nodeManager?.hasGenesisMismatch?.() ?? false;
    const choice = await dialog.showMessageBox(mainWindow, {
      type: "warning",
      buttons: ["Cancel", "Reset chain data"],
      defaultId: genesisMismatch ? 1 : 0,
      cancelId: 0,
      noLink: true,
      title: genesisMismatch ? "Fix genesis mismatch" : "Reset chain data",
      message: genesisMismatch
        ? "Remove old chain data and download the Bloodstone relaunch chain?"
        : "Delete local blockchain data and resync from the network?",
      detail: genesisMismatch
        ? `bloodstoned found chain data from the old SpaceXpanse network (or the wrong folder) in:\n${dataDir}\n\n` +
          "Reset removes blocks/, chainstate/, and indexes/ only. Wallets and bloodstone.conf are kept, then the node restarts on the correct genesis."
        : `This removes blocks, chainstate, indexes, and related cache files in:\n${dataDir}\n\n` +
          "Your wallets and bloodstone.conf are kept. The node will be stopped, data wiped, then restarted.",
    });
    if (choice.response !== 1) {
      return { ok: false, cancelled: true, message: "Reset cancelled" };
    }
    try {
      return await nodeManager.resetChainData({ restart: true });
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("dialog:pick-daemon", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: "Select bloodstoned.exe",
      properties: ["openFile"],
      filters: [{ name: "Bloodstone Node", extensions: ["exe"] }],
    });
    if (result.canceled || !result.filePaths.length) {
      return null;
    }
    return result.filePaths[0];
  });

  ipcMain.handle("dialog:pick-datadir", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: "Select data directory",
      properties: ["openDirectory", "createDirectory"],
    });
    if (result.canceled || !result.filePaths.length) {
      return null;
    }
    return result.filePaths[0];
  });

  ipcMain.handle("shell:open-datadir", async () => {
    await shell.openPath(settings.dataDir);
  });

  ipcMain.handle("shell:open-conf", async () => {
    for (const name of ["bloodstone.conf"]) {
      const conf = path.join(settings.dataDir, name);
      if (fs.existsSync(conf)) {
        await shell.openPath(conf);
        return;
      }
    }
    await shell.openPath(path.join(settings.dataDir, "bloodstone.conf"));
  });

  ipcMain.handle("dialog:pick-users-db", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: "Select users.db",
      properties: ["openFile"],
      filters: [{ name: "SQLite database", extensions: ["db", "sqlite", "sqlite3"] }],
    });
    if (result.canceled || !result.filePaths.length) {
      return null;
    }
    return result.filePaths[0];
  });

  ipcMain.handle("wallet:session", () => {
    if (!walletSession) {
      return null;
    }
    const available = walletNamesForUser(walletSession);
    return {
      ...walletSession,
      available_wallets: available,
      active_wallet: activeWalletForUser(walletSession),
    };
  });

  ipcMain.handle("wallet:login", async (_evt, { username, password }) => {
    try {
      settings.walletWebUrl = normalizeWalletWebUrl(settings.walletWebUrl);
      const result = await login(settings, username, password);
      if (!result.ok) {
        return result;
      }
      const available = walletNamesForUser(result.user);
      walletSessionPassword = password;
      walletSession = {
        ...result.user,
        active_wallet:
          result.user.primary_receive_wallet ||
          result.user.wallet_name ||
          available[0] ||
          null,
        available_wallets: available,
      };
      let vpsAutoApplied = false;
      let vpsWarning = null;
      if (
        useVpsWalletRpc(walletSession) &&
        shouldAutoApplyVps(settings) &&
        !vpsRpcActive(settings)
      ) {
        try {
          settings = applyVpsPreset(settings);
          saveSettings(settings);
          nodeManager.configure(settings);
          vpsAutoApplied = true;
        } catch (err) {
          vpsWarning =
            `Signed in, but could not switch to VPS RPC: ${err.message || err}. ` +
            "Open Settings → Use VPS, then refresh.";
        }
      }
      return {
        ok: true,
        user: walletSession,
        vpsAutoApplied,
        requiresVps: useVpsWalletRpc(walletSession),
        activeWallet: activeWalletForUser(walletSession),
        message:
          vpsWarning ||
          (vpsAutoApplied
            ? `Connected to VPS wallet "${activeWalletForUser(walletSession)}". (Web wallets are on the Bloodstone server.)`
            : undefined),
      };
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("wallet:switch", async (_evt, { walletName }) => {
    if (!walletSession) {
      return { ok: false, message: "Not signed in" };
    }
    const allowed = walletNamesForUser(walletSession);
    if (!walletName || !allowed.includes(walletName)) {
      return {
        ok: false,
        message: `Wallet "${walletName || ""}" is not linked to your account.`,
      };
    }
    if (
      useVpsWalletRpc(walletSession) &&
      !prefersLocalNodeRpc(settings) &&
      !vpsRpcActive(settings)
    ) {
      return {
        ok: false,
        needsVps: true,
        message:
          `Wallet "${walletName}" is on the Bloodstone VPS. ` +
          "Open Settings → Use VPS, then try again.",
      };
    }
    if (!settings.usersDbPath && settings.walletWebUrl && walletSessionPassword) {
      try {
        const apiResult = await setActiveWalletViaApi(
          settings.walletWebUrl,
          walletSession.username,
          walletSessionPassword,
          walletName
        );
        if (!apiResult.ok) {
          return apiResult;
        }
        if (apiResult.user) {
          walletSession = {
            ...walletSession,
            ...apiResult.user,
            active_wallet: apiResult.walletName || walletName,
            available_wallets: walletNamesForUser({
              ...walletSession,
              ...apiResult.user,
            }),
            primary_receive_wallet:
              apiResult.user.primary_receive_wallet || walletName,
            primary_receive_address:
              apiResult.address || apiResult.user.primary_receive_address || null,
          };
        }
      } catch (err) {
        return {
          ok: false,
          message: err.message || String(err),
        };
      }
    }
    try {
      await walletRpc.ensureWalletLoaded(walletName);
    } catch (err) {
      return {
        ok: false,
        message: err.message || String(err),
      };
    }
    walletSession = {
      ...walletSession,
      active_wallet: walletName,
      primary_receive_wallet: walletName,
      available_wallets: allowed,
    };
    return {
      ok: true,
      user: walletSession,
      activeWallet: walletName,
    };
  });

  ipcMain.handle("wallet:logout", async () => {
    if (walletSession?.wallet_name) {
      try {
        await walletRpc.lockWallet(walletSession.wallet_name);
      } catch (_) {
        /* ignore */
      }
    }
    walletSession = null;
    walletSessionPassword = null;
    return { ok: true };
  });

  ipcMain.handle("wallet:summary", async () => {
    if (!walletSession?.wallet_name) {
      return { ok: false, message: "Not signed in" };
    }
    if (
      useVpsWalletRpc(walletSession) &&
      !prefersLocalNodeRpc(settings) &&
      !vpsRpcActive(settings)
    ) {
      return {
        ok: false,
        needsVps: true,
        message:
          `Wallet "${activeWalletForUser(walletSession)}" is on the Bloodstone VPS. ` +
          "Open Settings → Use VPS, then sign in again.",
      };
    }
    try {
      const wallet = activeWalletForUser(walletSession);
      const summary = await walletRpc.walletSummary(wallet);
      return {
        ok: true,
        summary,
        user: walletSession,
        requiresVps: requiresVpsRpc(walletSession),
        rpcProfile: settings.rpcProfile,
      };
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("wallet:transactions", async (_evt, { count = 20, skip = 0 } = {}) => {
    if (!walletSession?.wallet_name) {
      return { ok: false, message: "Not signed in" };
    }
    try {
      const wallet = activeWalletForUser(walletSession);
      const txs = await walletRpc.listTransactions(wallet, count, skip);
      return { ok: true, transactions: txs };
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("wallet:addresses", async () => {
    if (!walletSession?.wallet_name) {
      return { ok: false, message: "Not signed in" };
    }
    try {
      const wallet = activeWalletForUser(walletSession);
      const addresses = await walletRpc.listAddresses(wallet);
      const primary =
        addresses[0]?.address ||
        walletSession.primary_receive_address ||
        null;
      return { ok: true, addresses, primary };
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("wallet:new-address", async () => {
    if (!walletSession?.wallet_name) {
      return { ok: false, message: "Not signed in" };
    }
    try {
      const wallet = activeWalletForUser(walletSession);
      const address = await walletRpc.getNewAddress(wallet);
      return { ok: true, address };
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("wallet:unlock", async (_evt, { passphrase, seconds = 1800 }) => {
    if (!walletSession?.wallet_name) {
      return { ok: false, message: "Not signed in" };
    }
    const phrase = String(passphrase || "").trim();
    if (!phrase) {
      return { ok: false, message: "Wallet passphrase is required." };
    }
    const wallets = walletsForUser(walletSession);
    const unlocked = [];
    const failures = [];
    for (const wallet of wallets) {
      try {
        await walletRpc.unlockWallet(wallet, phrase, seconds);
        unlocked.push(wallet);
      } catch (err) {
        const msg = err.message || String(err);
        failures.push(
          msg.toLowerCase().includes("incorrect")
            ? `${wallet}: wrong wallet passphrase (not your current login password if you changed it after wallet setup)`
            : `${wallet}: ${msg}`
        );
      }
    }
    if (!unlocked.length) {
      return { ok: false, message: failures.join("; ") || "Unlock failed." };
    }
    if (failures.length) {
      return {
        ok: true,
        message: `Unlocked ${unlocked.length} wallet(s); some failed: ${failures.join("; ")}`,
      };
    }
    return {
      ok: true,
      message: `Unlocked ${unlocked.length} wallet(s) for ${Math.round(seconds / 60)} minutes`,
    };
  });

  ipcMain.handle("wallet:send", async (_evt, { address, amount, comment = "", passphrase = "" }) => {
    if (!walletSession?.wallet_name) {
      return { ok: false, message: "Not signed in" };
    }
    try {
      const wallet = activeWalletForUser(walletSession);
      const txid = await walletRpc.sendToAddress(
        wallet,
        address,
        Number(amount),
        comment,
        passphrase
      );
      return { ok: true, txid };
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  function giftApiUnavailable() {
    if (settings.usersDbPath) {
      return {
        ok: false,
        message:
          "Gift codes use the Bloodstone web wallet API. Clear users.db path in Settings " +
          "and sign in with your web wallet URL instead.",
      };
    }
    if (!settings.walletWebUrl || !walletSessionPassword) {
      return { ok: false, message: "Sign in via the web wallet URL to use gift codes." };
    }
    return null;
  }

  ipcMain.handle("wallet:giftStatus", async () => {
    if (!walletSession?.username) {
      return { ok: false, message: "Not signed in" };
    }
    const blocked = giftApiUnavailable();
    if (blocked) {
      return blocked;
    }
    try {
      return await giftStatusViaApi(
        settings.walletWebUrl,
        walletSession.username,
        walletSessionPassword
      );
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("wallet:giftList", async () => {
    if (!walletSession?.username) {
      return { ok: false, message: "Not signed in" };
    }
    const blocked = giftApiUnavailable();
    if (blocked) {
      return blocked;
    }
    try {
      return await giftListViaApi(
        settings.walletWebUrl,
        walletSession.username,
        walletSessionPassword
      );
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("wallet:giftCreate", async (_evt, { amount, passphrase = "" }) => {
    if (!walletSession?.username) {
      return { ok: false, message: "Not signed in" };
    }
    const blocked = giftApiUnavailable();
    if (blocked) {
      return blocked;
    }
    try {
      return await giftCreateViaApi(
        settings.walletWebUrl,
        walletSession.username,
        walletSessionPassword,
        amount,
        passphrase
      );
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("wallet:giftRedeem", async (_evt, { code }) => {
    if (!walletSession?.username) {
      return { ok: false, message: "Not signed in" };
    }
    const blocked = giftApiUnavailable();
    if (blocked) {
      return blocked;
    }
    try {
      return await giftRedeemViaApi(
        settings.walletWebUrl,
        walletSession.username,
        walletSessionPassword,
        code
      );
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("wallet:giftReveal", async (_evt, { created_at: createdAt }) => {
    if (!walletSession?.username) {
      return { ok: false, message: "Not signed in" };
    }
    const blocked = giftApiUnavailable();
    if (blocked) {
      return blocked;
    }
    try {
      return await giftRevealViaApi(
        settings.walletWebUrl,
        walletSession.username,
        walletSessionPassword,
        createdAt
      );
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  function referralApiUnavailable() {
    if (settings.usersDbPath) {
      return {
        ok: false,
        message:
          "Referrals use the Bloodstone web wallet API. Clear users.db path in Settings " +
          "and sign in with your web wallet URL instead.",
      };
    }
    if (!settings.walletWebUrl || !walletSessionPassword) {
      return { ok: false, message: "Sign in via the web wallet URL to use referrals." };
    }
    return null;
  }

  ipcMain.handle("wallet:referralsDashboard", async () => {
    if (!walletSession?.username) {
      return { ok: false, message: "Not signed in" };
    }
    const blocked = referralApiUnavailable();
    if (blocked) {
      return blocked;
    }
    try {
      return await referralsDashboardViaApi(
        settings.walletWebUrl,
        walletSession.username,
        walletSessionPassword
      );
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("wallet:referralsLive", async () => {
    if (!walletSession?.username) {
      return { ok: false, message: "Not signed in" };
    }
    const blocked = referralApiUnavailable();
    if (blocked) {
      return blocked;
    }
    try {
      return await referralsLiveViaApi(
        settings.walletWebUrl,
        walletSession.username,
        walletSessionPassword
      );
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("wallet:referralsDiscordConnect", async () => {
    if (!walletSession?.username) {
      return { ok: false, message: "Not signed in" };
    }
    const blocked = referralApiUnavailable();
    if (blocked) {
      return blocked;
    }
    try {
      return await referralsDiscordConnectViaApi(
        settings.walletWebUrl,
        walletSession.username,
        walletSessionPassword
      );
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("shell:open-url", async (_evt, url) => {
    const target = String(url || "").trim();
    if (!target) {
      return { ok: false, message: "No URL provided." };
    }
    try {
      await shell.openExternal(target);
      return { ok: true };
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("rpc:call", async (_evt, { method, params = [], wallet = null }) => {
    try {
      const result = await walletRpc.rpc(method, params, wallet || null);
      return { ok: true, result };
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  async function localNodeReachable() {
    try {
      const localRpc = makeLocalRpc(() => settings);
      await localRpc.rpc("getblockchaininfo");
      return true;
    } catch (_) {
      return false;
    }
  }

  ipcMain.handle("wallet-import:local-ready", async () => {
    settings = syncLocalRpcFromConf(settings);
    const running = nodeManager?.isRunning() || false;
    const reachable = await localNodeReachable();
    return {
      ok: reachable,
      running,
      reachable,
      message: reachable
        ? "Local node is ready."
        : "Start your local node first (Node tab → Start Node).",
    };
  });

  ipcMain.handle("wallet-import:list-vps", async () => {
    if (!(await localNodeReachable())) {
      return {
        ok: false,
        needsLocalNode: true,
        message: "Start your local node first (Node tab → Start Node).",
      };
    }
    try {
      const vpsRpc = makeVpsRpc(() => settings);
      const wallets = await listWalletsOn(vpsRpc);
      return { ok: true, wallets };
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle("wallet-import:list-user", async (_evt, { username, password }) => {
    try {
      const wallets = await listUserWalletsViaApi(
        settings.walletWebUrl,
        username,
        password
      );
      return { ok: true, wallets };
    } catch (err) {
      return { ok: false, message: err.message || String(err) };
    }
  });

  ipcMain.handle(
    "wallet-import:run",
    async (_evt, { walletName, passphrase, username, password }) => {
      try {
        const result = await importWalletFromVps({
          getSettings: () => settings,
          walletName,
          passphrase,
          username,
          password,
          localNodeReachable: await localNodeReachable(),
        });
        return result;
      } catch (err) {
        return { ok: false, message: err.message || String(err) };
      }
    }
  );
}

app.whenReady().then(() => {
  initSettings();
  registerIpc();
  createWindow();
  createTray();
  nodeManager.beginMonitoring();

  if (!settings.startMinimized) {
    mainWindow.show();
  }
});

app.on("before-quit", async () => {
  app.isQuitting = true;
  if (walletSession?.wallet_name) {
    try {
      await walletRpc?.lockWallet(walletSession.wallet_name);
    } catch (_) {
      /* ignore */
    }
  }
  if (nodeManager?.isRunning()) {
    await nodeManager.stop();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    /* keep running in tray on Windows */
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
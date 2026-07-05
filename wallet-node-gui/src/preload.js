const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("bloodstone", {
  getSettings: () => ipcRenderer.invoke("settings:get"),
  saveSettings: (settings) => ipcRenderer.invoke("settings:save", settings),
  useVpsRpc: () => ipcRenderer.invoke("settings:use-vps"),
  useLocalRpc: () => ipcRenderer.invoke("settings:use-local-rpc"),
  resetSettings: () => ipcRenderer.invoke("settings:reset"),
  startNode: () => ipcRenderer.invoke("node:start"),
  stopNode: () => ipcRenderer.invoke("node:stop"),
  getStatus: () => ipcRenderer.invoke("node:status"),
  isRunning: () => ipcRenderer.invoke("node:running"),
  repairSync: () => ipcRenderer.invoke("node:repair-sync"),
  resetChainData: () => ipcRenderer.invoke("node:reset-chain-data"),
  pickDaemon: () => ipcRenderer.invoke("dialog:pick-daemon"),
  pickDataDir: () => ipcRenderer.invoke("dialog:pick-datadir"),
  pickUsersDb: () => ipcRenderer.invoke("dialog:pick-users-db"),
  openDataDir: () => ipcRenderer.invoke("shell:open-datadir"),
  openConf: () => ipcRenderer.invoke("shell:open-conf"),
  onLog: (callback) => {
    const handler = (_event, line) => callback(line);
    ipcRenderer.on("node:log", handler);
    return () => ipcRenderer.removeListener("node:log", handler);
  },
  onStatus: (callback) => {
    const handler = (_event, status) => callback(status);
    ipcRenderer.on("node:status", handler);
    return () => ipcRenderer.removeListener("node:status", handler);
  },
  walletSession: () => ipcRenderer.invoke("wallet:session"),
  walletLogin: (username, password) =>
    ipcRenderer.invoke("wallet:login", { username, password }),
  walletSwitch: (walletName) =>
    ipcRenderer.invoke("wallet:switch", { walletName }),
  walletLogout: () => ipcRenderer.invoke("wallet:logout"),
  walletSummary: () => ipcRenderer.invoke("wallet:summary"),
  walletTransactions: (opts) => ipcRenderer.invoke("wallet:transactions", opts),
  walletAddresses: () => ipcRenderer.invoke("wallet:addresses"),
  walletNewAddress: () => ipcRenderer.invoke("wallet:new-address"),
  walletUnlock: (passphrase, seconds) =>
    ipcRenderer.invoke("wallet:unlock", { passphrase, seconds }),
  walletSend: (payload) => ipcRenderer.invoke("wallet:send", payload),
  walletGiftStatus: () => ipcRenderer.invoke("wallet:giftStatus"),
  walletGiftList: () => ipcRenderer.invoke("wallet:giftList"),
  walletGiftCreate: (payload) => ipcRenderer.invoke("wallet:giftCreate", payload),
  walletGiftRedeem: (payload) => ipcRenderer.invoke("wallet:giftRedeem", payload),
  walletGiftReveal: (payload) => ipcRenderer.invoke("wallet:giftReveal", payload),
  walletReferralsDashboard: () => ipcRenderer.invoke("wallet:referralsDashboard"),
  walletReferralsLive: () => ipcRenderer.invoke("wallet:referralsLive"),
  walletReferralsDiscordConnect: () => ipcRenderer.invoke("wallet:referralsDiscordConnect"),
  openUrl: (url) => ipcRenderer.invoke("shell:open-url", url),
  rpcCall: (method, params, wallet) =>
    ipcRenderer.invoke("rpc:call", { method, params, wallet }),
  importLocalNodeReady: () => ipcRenderer.invoke("wallet-import:local-ready"),
  importListVpsWallets: () => ipcRenderer.invoke("wallet-import:list-vps"),
  importListUserWallets: (username, password) =>
    ipcRenderer.invoke("wallet-import:list-user", { username, password }),
  importWalletFromVps: (payload) => ipcRenderer.invoke("wallet-import:run", payload),
});
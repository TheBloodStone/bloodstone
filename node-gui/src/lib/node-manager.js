const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const http = require("http");
const { resolveDaemonPath, resolveCliPath } = require("./paths");
const {
  ensureConf,
  saveSettings,
  writeConf,
  readConfCredentials,
  localConfCredentials,
  captureLocalRpcCredentials,
} = require("./config");
const { ensureNodeBinary, isValidDaemon } = require("./node-downloader");

const BLOCK1_HASH =
  "072327c9b49c3ed05ba3a24b40579eed3c9efacb757d3f04c6632559e2ab7aa2";

/** Chain folders/files safe to delete for a clean resync (wallets + conf are kept). */
const CHAIN_RESET_DIRS = ["blocks", "chainstate", "indexes"];
const CHAIN_RESET_FILES = [
  "mempool.dat",
  "fee_estimates.dat",
  ".lock",
  "bloodstoned.pid",
  "debug.log",
];

class NodeManager {
  constructor(resourcesPath) {
    this.resourcesPath = resourcesPath;
    this.process = null;
    this.settings = null;
    this.logListeners = new Set();
    this.statusListeners = new Set();
    this._pollTimer = null;
    this._logTailTimer = null;
    this._logOffset = 0;
    this._lastGoodStatus = null;
    this._logHeight = null;
    this._rpcReachable = false;
    this._monitoring = false;
    this._syncRecoveryAttempted = false;
    this._syncRecoveryInProgress = false;
  }

  onLog(fn) {
    this.logListeners.add(fn);
    return () => this.logListeners.delete(fn);
  }

  onStatus(fn) {
    this.statusListeners.add(fn);
    return () => this.statusListeners.delete(fn);
  }

  _emitLog(line) {
    for (const fn of this.logListeners) {
      fn(line);
    }
  }

  _emitStatus(status) {
    for (const fn of this.statusListeners) {
      fn(status);
    }
  }

  configure(settings) {
    this.settings = { ...settings };
    const confCreds = readConfCredentials(this.settings.dataDir);
    if (confCreds) {
      Object.assign(this.settings, confCreds);
    }
    ensureConf(this.settings);
    this.daemonPath = resolveDaemonPath(
      this.resourcesPath,
      this.settings.daemonPath || "",
      this.settings.dataDir
    );
    this.cliPath = resolveCliPath(this.daemonPath);
  }

  isRunning() {
    return this.process !== null && !this.process.killed;
  }

  isNodeActive() {
    return this.isRunning() || this._rpcReachable;
  }

  beginMonitoring() {
    if (!this.settings || this._monitoring) {
      return;
    }
    this._monitoring = true;
    this._startPolling();
    this._startLogTail();
  }

  async start() {
    if (this.isRunning()) {
      return { ok: true, message: "Node already running" };
    }
    if (!this.settings) {
      return { ok: false, message: "Settings not configured" };
    }

    const ensured = await ensureNodeBinary({
      settings: this.settings,
      resourcesPath: this.resourcesPath,
      saveSettings,
      onLog: (line) => this._emitLog(line),
    });
    if (!ensured.ok) {
      return ensured;
    }
    if (ensured.daemonPath) {
      this.settings.daemonPath = ensured.daemonPath;
    }
    this.daemonPath = resolveDaemonPath(
      this.resourcesPath,
      this.settings.daemonPath || "",
      this.settings.dataDir
    );
    this.cliPath = resolveCliPath(this.daemonPath);

    if (!isValidDaemon(this.daemonPath)) {
      return {
        ok: false,
        message: `Node binary not found at ${this.daemonPath}. Open Settings and browse to bloodstoned.exe.`,
      };
    }

    try {
      fs.mkdirSync(this.settings.dataDir, { recursive: true });
    } catch (err) {
      return {
        ok: false,
        message: `Cannot create data directory ${this.settings.dataDir}: ${err.message}`,
      };
    }

    const confPath = ensureConf(this.settings);
    writeConf(this.settings);
    this.settings.firstRunComplete = true;
    saveSettings(this.settings);

    const args = [
      `-datadir=${this.settings.dataDir}`,
      `-conf=${confPath}`,
      "-printtoconsole",
    ];

    const daemonBase = path.basename(this.daemonPath).toLowerCase();
    if (daemonBase.includes("spacexpanse")) {
      this._emitLog(
        "[gui] WARNING: Legacy SpaceXpanse binary detected. Uninstall Bloodstone Node and install bloodstone-node-gui-0.6.9.1-win64.exe from the portal downloads page."
      );
    }

    this._emitLog(`[gui] Starting ${this.daemonPath}`);
    this._emitLog(`[gui] Data dir: ${this.settings.dataDir}`);
    this._emitLog(`[gui] Config: ${confPath}`);

    return new Promise((resolve) => {
      let settled = false;
      const finish = (result) => {
        if (settled) {
          return;
        }
        settled = true;
        resolve(result);
      };

      try {
        this.process = spawn(this.daemonPath, args, {
          cwd: path.dirname(this.daemonPath),
          windowsHide: true,
          stdio: ["ignore", "pipe", "pipe"],
        });
      } catch (err) {
        finish({ ok: false, message: `Failed to launch node: ${err.message}` });
        return;
      }

      this.process.stdout.on("data", (buf) => {
        String(buf)
          .split(/\r?\n/)
          .filter(Boolean)
          .forEach((line) => {
            if (/SpaceXpanse version/i.test(line)) {
              this._emitLog(
                "[gui] WARNING: Node reports SpaceXpanse branding — install the latest Bloodstone Node GUI (0.6.9.1) to replace spacexpansed.exe."
              );
            }
            this._emitLog(line);
          });
      });
      this.process.stderr.on("data", (buf) => {
        String(buf)
          .split(/\r?\n/)
          .filter(Boolean)
          .forEach((line) => this._emitLog(`[stderr] ${line}`));
      });

      this.process.on("error", (err) => {
        this._emitLog(`[gui] Launch error: ${err.message}`);
        this.process = null;
        this._emitStatus({ running: false, processManaged: false, rpcReachable: false });
        finish({
          ok: false,
          message: `Could not start bloodstoned (${err.message}). Check Windows Defender or pick the binary manually in Settings.`,
        });
      });

      this.process.on("exit", (code, signal) => {
        this._emitLog(`Node stopped (code=${code ?? "?"}, signal=${signal ?? "none"})`);
        this.process = null;
        this._rpcReachable = false;
        void this.fetchStatus().then((status) => this._emitStatus(status));
        if (!settled) {
          finish({
            ok: false,
            message: `Node exited immediately (code=${code ?? "?"}). Open the Logs tab for details.`,
          });
        }
      });

      const startedAt = Date.now();
      const waitForRpc = async () => {
        while (this.isRunning() && Date.now() - startedAt < 30000) {
          try {
            await this.rpc("getblockchaininfo");
            this.beginMonitoring();
            this._emitStatus({ running: true, processManaged: true, rpcReachable: true });
            finish({
              ok: true,
              message: `Node started — config saved to ${confPath}`,
            });
            return;
          } catch (_) {
            await new Promise((r) => setTimeout(r, 500));
          }
        }
        if (!this.isRunning()) {
          if (!settled) {
            finish({
              ok: false,
              message: "Node exited before it could start. Open the Logs tab for details.",
            });
          }
          return;
        }
        this.beginMonitoring();
        this._emitStatus({ running: true, processManaged: true });
        finish({
          ok: true,
          message: `Node process running — waiting for RPC (${confPath}). Check Logs if sync stays at 0%.`,
        });
      };
      setTimeout(() => {
        void waitForRpc();
      }, 800);
    });
  }

  async stop() {
    if (!this.isRunning()) {
      return { ok: true, message: "Node not running" };
    }
    try {
      await this.rpc("stop");
    } catch (_) {
      this.process.kill("SIGTERM");
    }
    return { ok: true, message: "Stop requested" };
  }

  _rpcUrl() {
    const local = localConfCredentials(
      captureLocalRpcCredentials({ ...this.settings })
    );
    return {
      host: "127.0.0.1",
      port: local.rpcPort || this.settings.rpcPort || 18332,
      auth: `${local.rpcUser}:${local.rpcPassword}`,
    };
  }

  rpc(method, params = []) {
    const { host, port, auth } = this._rpcUrl();
    const body = JSON.stringify({
      jsonrpc: "1.0",
      id: "bloodstone-gui",
      method,
      params,
    });
    const authHeader = Buffer.from(auth).toString("base64");

    return new Promise((resolve, reject) => {
      const req = http.request(
        {
          hostname: host,
          port,
          path: "/",
          method: "POST",
          headers: {
            "Content-Type": "text/plain",
            Authorization: `Basic ${authHeader}`,
            "Content-Length": Buffer.byteLength(body),
          },
          timeout: 15000,
        },
        (res) => {
          let data = "";
          res.on("data", (chunk) => {
            data += chunk;
          });
          res.on("end", () => {
            try {
              const parsed = JSON.parse(data);
              if (parsed.error) {
                reject(new Error(parsed.error.message || JSON.stringify(parsed.error)));
              } else {
                resolve(parsed.result);
              }
            } catch (err) {
              reject(err);
            }
          });
        }
      );
      req.on("error", reject);
      req.on("timeout", () => {
        req.destroy();
        reject(new Error("RPC timeout"));
      });
      req.write(body);
      req.end();
    });
  }

  _parseLogHeight() {
    if (!this.settings) {
      return null;
    }
    const logPath = this._debugLogPath();
    if (!fs.existsSync(logPath)) {
      return null;
    }
    try {
      const stat = fs.statSync(logPath);
      const readLen = Math.min(stat.size, 131072);
      const fd = fs.openSync(logPath, "r");
      const buf = Buffer.alloc(readLen);
      fs.readSync(fd, buf, 0, readLen, stat.size - readLen);
      fs.closeSync(fd);
      const matches = [...buf.toString("utf8").matchAll(/UpdateTip:.*?height=(\d+)/g)];
      if (!matches.length) {
        return null;
      }
      return Number(matches[matches.length - 1][1]);
    } catch (_) {
      return null;
    }
  }

  _statusFromRpc(info, peers, net) {
    const progress = info.verificationprogress ?? 0;
    return {
      running: this.isNodeActive(),
      processManaged: this.isRunning(),
      rpcReachable: true,
      blocks: info.blocks,
      headers: info.headers,
      chain: info.chain,
      bestBlockHash: info.bestblockhash,
      difficulty: info.difficulty,
      verificationProgress: progress,
      syncPercent: Math.round(progress * 10000) / 100,
      initialBlockDownload: info.initialblockdownload,
      connections: typeof peers === "number" ? peers : peers,
      subversion: net.subversion || "",
      networkActive: net.networkactive,
    };
  }

  _shouldAttemptSyncRecovery(status) {
    if (!status?.rpcReachable || !this.isNodeActive()) {
      return false;
    }
    const blocks = Number(status.blocks ?? 0);
    const headers = Number(status.headers ?? 0);
    return blocks === 0 && headers > 10 && Number(status.connections ?? 0) > 0;
  }

  resetSyncRecovery() {
    this._syncRecoveryAttempted = false;
  }

  async _ensureNodeStoppedForReset() {
    if (this._rpcReachable) {
      try {
        await this.rpc("stop");
      } catch (_) {
        /* node may already be stopped */
      }
    }
    if (this.isRunning()) {
      await this.stop();
    }

    const deadline = Date.now() + 15000;
    while (this.isRunning() && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 400));
    }
    return !this.isRunning();
  }

  async resetChainData({ restart = true } = {}) {
    if (!this.settings?.dataDir) {
      return { ok: false, message: "Data directory is not configured" };
    }

    const dataDir = this.settings.dataDir;
    this._emitLog(`[gui] Resetting chain data in ${dataDir} (wallets and config are kept)…`);

    const stopped = await this._ensureNodeStoppedForReset();
    if (!stopped) {
      return {
        ok: false,
        message:
          "Could not stop the node. Stop bloodstoned manually, then try Reset chain data again.",
      };
    }

    const removed = [];
    const errors = [];

    for (const dirName of CHAIN_RESET_DIRS) {
      const target = path.join(dataDir, dirName);
      if (!fs.existsSync(target)) {
        continue;
      }
      try {
        fs.rmSync(target, { recursive: true, force: true });
        removed.push(`${dirName}/`);
      } catch (err) {
        errors.push(`${dirName}: ${err.message}`);
      }
    }

    for (const fileName of CHAIN_RESET_FILES) {
      const target = path.join(dataDir, fileName);
      if (!fs.existsSync(target)) {
        continue;
      }
      try {
        fs.rmSync(target, { force: true });
        removed.push(fileName);
      } catch (err) {
        errors.push(`${fileName}: ${err.message}`);
      }
    }

    this._logOffset = 0;
    this._logHeight = null;
    this._lastGoodStatus = null;
    this._rpcReachable = false;
    this.resetSyncRecovery();

    if (errors.length) {
      return {
        ok: false,
        message: `Partial reset — could not remove: ${errors.join("; ")}`,
        removed,
      };
    }

    const summary =
      removed.length > 0
        ? `Removed ${removed.join(", ")}`
        : "No chain data folders were present (already clean)";

    this._emitLog(`[gui] ${summary}`);
    this._emitStatus({
      running: false,
      processManaged: false,
      rpcReachable: false,
      blocks: 0,
      headers: 0,
      syncError: null,
      syncRecovery: false,
    });

    if (!restart) {
      return {
        ok: true,
        message: `${summary}. Start the node to download the chain from scratch.`,
        removed,
        restarted: false,
      };
    }

    const startResult = await this.start();
    return {
      ok: startResult.ok,
      message: startResult.ok
        ? `${summary}. Node restarted — syncing from the network.`
        : `${summary}. Start the node manually to begin syncing.`,
      removed,
      restarted: startResult.ok,
    };
  }

  async attemptSyncRecovery(reason = "stuck at genesis", force = false) {
    if (
      !force &&
      (this._syncRecoveryAttempted || this._syncRecoveryInProgress || !this.settings)
    ) {
      return { ok: false, message: "Sync recovery already attempted or node not ready" };
    }
    if (!this._rpcReachable) {
      return { ok: false, message: "RPC not reachable" };
    }

    this._syncRecoveryInProgress = true;
    this._emitLog(
      `[gui] Block 1 sync recovery (${reason}) — clearing invalid flag via reconsiderblock…`
    );
    this._emitStatus({
      running: this.isNodeActive(),
      processManaged: this.isRunning(),
      syncRecovery: true,
      syncError:
        "Recovering sync: clearing a stale invalid flag on block 1. This can take a minute…",
      blocks: 0,
    });

    try {
      await this.rpc("reconsiderblock", [BLOCK1_HASH]);
      this._syncRecoveryAttempted = true;
      await new Promise((r) => setTimeout(r, 2500));
      const status = await this.fetchStatus();
      if (Number(status.blocks ?? 0) > 0) {
        this._emitLog(
          `[gui] Sync recovery succeeded — validated height is now ${status.blocks}.`
        );
        this._emitStatus({ ...status, syncRecovery: false, syncError: null });
        return { ok: true, message: `Sync resumed at height ${status.blocks}` };
      }
      this._emitStatus({
        ...status,
        syncRecovery: false,
        syncError:
          "Block 1 is still blocked after recovery. Use Reset chain data in Settings (keeps wallets), then start the node again.",
        blocks: 0,
      });
      return {
        ok: false,
        message:
          "reconsiderblock completed but chain height is still 0 — delete blocks and chainstate, then restart",
      };
    } catch (err) {
      this._syncRecoveryAttempted = true;
      this._emitLog(`[gui] Sync recovery failed: ${err.message}`);
      this._emitStatus({
        running: this.isNodeActive(),
        processManaged: this.isRunning(),
        syncRecovery: false,
        syncError:
          "Block 1 is marked invalid from a previous failed sync. Try Repair sync, or use Reset chain data in Settings.",
        blocks: 0,
      });
      return { ok: false, message: err.message };
    } finally {
      this._syncRecoveryInProgress = false;
    }
  }

  _maybeRecoverSync(status, reason) {
    if (
      this._syncRecoveryAttempted ||
      this._syncRecoveryInProgress ||
      !this._shouldAttemptSyncRecovery(status)
    ) {
      return;
    }
    void this.attemptSyncRecovery(reason);
  }

  async fetchStatus() {
    if (!this.settings) {
      return { running: false };
    }
    try {
      const [info, peers, net] = await Promise.all([
        this.rpc("getblockchaininfo"),
        this.rpc("getconnectioncount").catch(() => 0),
        this.rpc("getnetworkinfo").catch(() => ({})),
      ]);
      this._rpcReachable = true;
      const status = this._statusFromRpc(info, peers, net);
      this._lastGoodStatus = status;
      this._maybeRecoverSync(status, "headers ahead of validated blocks");
      return status;
    } catch (err) {
      this._rpcReachable = false;
      const logHeight = this._logHeight ?? this._parseLogHeight();
      const base = {
        running: this.isNodeActive(),
        processManaged: this.isRunning(),
        rpcReachable: false,
        error: err.message,
      };
      if (this._lastGoodStatus) {
        return {
          ...this._lastGoodStatus,
          ...base,
          blocks: this._lastGoodStatus.blocks,
        };
      }
      if (logHeight != null) {
        return {
          ...base,
          blocks: logHeight,
          headers: logHeight,
          logHeightFallback: true,
        };
      }
      return base;
    }
  }

  _startPolling() {
    if (this._pollTimer) {
      return;
    }
    const tick = async () => {
      const status = await this.fetchStatus();
      this._emitStatus(status);
    };
    tick();
    this._pollTimer = setInterval(tick, 4000);
  }

  _stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  }

  _stopLogTail() {
    if (this._logTailTimer) {
      clearInterval(this._logTailTimer);
      this._logTailTimer = null;
    }
  }

  _stopMonitoring() {
    this._stopPolling();
    this._stopLogTail();
    this._monitoring = false;
    this._rpcReachable = false;
    this._lastGoodStatus = null;
    this._logHeight = null;
  }

  _debugLogPath() {
    return path.join(this.settings.dataDir, "debug.log");
  }

  _startLogTail() {
    if (this._logTailTimer) {
      return;
    }
    this._logOffset = 0;
    this._logTailTimer = setInterval(() => {
      const logPath = this._debugLogPath();
      if (!fs.existsSync(logPath)) {
        return;
      }
      const stat = fs.statSync(logPath);
      if (stat.size < this._logOffset) {
        this._logOffset = 0;
      }
      if (stat.size === this._logOffset) {
        return;
      }
      const fd = fs.openSync(logPath, "r");
      const len = stat.size - this._logOffset;
      const buf = Buffer.alloc(len);
      fs.readSync(fd, buf, 0, len, this._logOffset);
      fs.closeSync(fd);
      this._logOffset = stat.size;
      const lines = buf.toString("utf8").split(/\r?\n/).filter(Boolean);
      let latestHeight = null;
      for (const line of lines) {
        const match = line.match(/UpdateTip:.*?height=(\d+)/);
        if (match) {
          latestHeight = Number(match[1]);
        }
        if (/SpaceXpanse version/i.test(line)) {
          this._emitStatus({
            running: this.isNodeActive(),
            processManaged: this.isRunning(),
            legacyBinary: true,
            syncError:
              "Legacy SpaceXpanse binary detected — uninstall and install Bloodstone Node GUI 0.6.9.1 from the portal.",
          });
        }
        if (/bad-cb-amount|coinbase pays too much/i.test(line)) {
          this._emitStatus({
            running: this.isNodeActive(),
            processManaged: this.isRunning(),
            syncError:
              "Block 1 validation failed (bad-cb-amount). Install Bloodstone Node GUI 0.6.9.1, then use Repair sync or Reset chain data in Settings.",
            blocks: 0,
          });
        }
        if (new RegExp(`${BLOCK1_HASH} is marked invalid`, "i").test(line)) {
          this._emitStatus({
            running: this.isNodeActive(),
            processManaged: this.isRunning(),
            syncError:
              "Block 1 is marked invalid from a previous failed sync. Attempting automatic recovery…",
            blocks: 0,
          });
          if (this._rpcReachable) {
            void this.attemptSyncRecovery("block 1 marked invalid");
          }
        }
        this._emitLog(`[log] ${line}`);
      }
      if (latestHeight != null && latestHeight !== this._logHeight) {
        this._logHeight = latestHeight;
        if (!this._rpcReachable) {
          void this.fetchStatus().then((status) => this._emitStatus(status));
        }
      }
    }, 2000);
  }
}

module.exports = { NodeManager };
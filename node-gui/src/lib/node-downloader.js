const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const https = require("https");
const path = require("path");
const { execFile } = require("child_process");
const { promisify } = require("util");

const execFileAsync = promisify(execFile);

const {
  NODE_CORE_VERSION,
  DEFAULT_DOWNLOAD_ROOT,
  DAEMON_NAMES,
  CLI_NAMES,
  isWindows,
  resolveDaemonPath,
  localBinDir,
} = require("./paths");

function isValidDaemon(filePath) {
  if (!filePath || !fs.existsSync(filePath)) {
    return false;
  }
  const base = path.basename(filePath).toLowerCase();
  if (base.includes("spacexpanse")) {
    return false;
  }
  return DAEMON_NAMES.some((name) => base === name.toLowerCase());
}

function findBinaryRecursive(rootDir, names, depth = 0) {
  if (!rootDir || !fs.existsSync(rootDir) || depth > 4) {
    return null;
  }
  for (const name of names) {
    const direct = path.join(rootDir, name);
    if (fs.existsSync(direct)) {
      return direct;
    }
  }
  let entries = [];
  try {
    entries = fs.readdirSync(rootDir, { withFileTypes: true });
  } catch (_) {
    return null;
  }
  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }
    const found = findBinaryRecursive(path.join(rootDir, entry.name), names, depth + 1);
    if (found) {
      return found;
    }
  }
  return null;
}

function downloadFile(urlString, destPath, onProgress) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlString);
    const lib = url.protocol === "https:" ? https : http;
    const req = lib.get(url, (res) => {
      if (
        res.statusCode >= 300 &&
        res.statusCode < 400 &&
        res.headers.location
      ) {
        res.resume();
        downloadFile(new URL(res.headers.location, url).toString(), destPath, onProgress)
          .then(resolve)
          .catch(reject);
        return;
      }
      if (res.statusCode !== 200) {
        res.resume();
        reject(new Error(`Download failed (HTTP ${res.statusCode}) for ${urlString}`));
        return;
      }
      const total = Number(res.headers["content-length"] || 0);
      let received = 0;
      const file = fs.createWriteStream(destPath);
      res.on("data", (chunk) => {
        received += chunk.length;
        if (onProgress && total > 0) {
          onProgress(Math.min(100, Math.round((received / total) * 100)));
        }
      });
      res.pipe(file);
      file.on("finish", () => file.close(() => resolve(destPath)));
      file.on("error", (err) => {
        fs.unlink(destPath, () => reject(err));
      });
    });
    req.on("error", reject);
    req.setTimeout(300000, () => {
      req.destroy();
      reject(new Error("Node download timed out"));
    });
  });
}

async function verifySha256(filePath, sidecarPath) {
  if (!fs.existsSync(sidecarPath)) {
    return true;
  }
  const expected = fs.readFileSync(sidecarPath, "utf8").trim().split(/\s+/)[0];
  if (!expected) {
    return true;
  }
  const hash = crypto.createHash("sha256");
  await new Promise((resolve, reject) => {
    const stream = fs.createReadStream(filePath);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("end", resolve);
    stream.on("error", reject);
  });
  return hash.digest("hex").toLowerCase() === expected.toLowerCase();
}

async function extractZipWindows(zipPath, destDir) {
  await fs.promises.mkdir(destDir, { recursive: true });
  const ps = [
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    `Expand-Archive -LiteralPath '${zipPath.replace(/'/g, "''")}' -DestinationPath '${destDir.replace(/'/g, "''")}' -Force`,
  ];
  await execFileAsync("powershell.exe", ps, { timeout: 180000, windowsHide: true });
}

async function extractZip(zipPath, destDir) {
  if (process.platform === "win32") {
    await extractZipWindows(zipPath, destDir);
    return;
  }
  await execFileAsync("unzip", ["-o", zipPath, "-d", destDir], { timeout: 180000 });
}

async function ensureNodeBinary({ settings, resourcesPath, saveSettings, onLog }) {
  const dataDir = settings?.dataDir;
  const userPath = settings?.daemonPath || "";
  let daemonPath = resolveDaemonPath(resourcesPath, userPath, dataDir);
  if (isValidDaemon(daemonPath)) {
    return { ok: true, daemonPath };
  }

  if (!isWindows()) {
    return {
      ok: false,
      message:
        "Node binary not found. On Windows the app downloads it automatically on first start.",
    };
  }

  const version = settings?.nodeCoreVersion || NODE_CORE_VERSION;
  const base = String(settings?.downloadBaseUrl || DEFAULT_DOWNLOAD_ROOT).replace(
    /\/+$/,
    ""
  );
  const zipName = `bloodstone-node-${version}-win64.zip`;
  const url = `${base}/downloads/${zipName}`;
  const installDir = localBinDir(dataDir);
  const targetDaemon = path.join(installDir, "bloodstoned.exe");
  const targetCli = path.join(installDir, "bloodstone-cli.exe");

  if (isValidDaemon(targetDaemon) && fs.existsSync(targetCli)) {
    settings.daemonPath = targetDaemon;
    saveSettings(settings);
    return { ok: true, daemonPath: targetDaemon };
  }

  const tempRoot = path.join(dataDir, "downloads");
  const zipPath = path.join(tempRoot, zipName);
  const extractDir = path.join(tempRoot, `extract-${version}`);

  try {
    onLog?.(`[gui] Node binary missing — downloading ${zipName} from portal…`);
    await fs.promises.mkdir(tempRoot, { recursive: true });
    if (fs.existsSync(extractDir)) {
      await fs.promises.rm(extractDir, { recursive: true, force: true });
    }
    await downloadFile(url, zipPath, (pct) => {
      if (pct % 20 === 0) {
        onLog?.(`[gui] Downloading node package… ${pct}%`);
      }
    });
    const shaOk = await verifySha256(zipPath, `${zipPath}.sha256`);
    if (!shaOk) {
      throw new Error("Downloaded node package failed SHA256 verification.");
    }
    onLog?.("[gui] Extracting node binaries…");
    await extractZip(zipPath, extractDir);
    const foundDaemon = findBinaryRecursive(extractDir, DAEMON_NAMES);
    const foundCli = findBinaryRecursive(extractDir, CLI_NAMES);
    if (!foundDaemon || !foundCli) {
      throw new Error(
        `Could not find bloodstoned.exe in ${zipName}. Try downloading manually from ${base}/downloads/`
      );
    }
    if (path.basename(foundDaemon).toLowerCase().includes("spacexpanse")) {
      throw new Error(
        "Downloaded package contains legacy SpaceXpanse binaries. Use bloodstone-node-0.7.5-win64.zip or newer."
      );
    }
    await fs.promises.mkdir(installDir, { recursive: true });
    await fs.promises.copyFile(foundDaemon, targetDaemon);
    await fs.promises.copyFile(foundCli, targetCli);
    settings.daemonPath = targetDaemon;
    settings.nodeCoreVersion = version;
    saveSettings(settings);
    onLog?.(`[gui] Installed node binaries to ${installDir}`);
    return { ok: true, daemonPath: targetDaemon, downloaded: true };
  } catch (err) {
    return {
      ok: false,
      message:
        `Could not download node binary: ${err.message || err}. ` +
        `Get ${zipName} from ${base}/downloads/ and set bloodstoned.exe in Settings.`,
    };
  }
}

module.exports = {
  ensureNodeBinary,
  isValidDaemon,
};
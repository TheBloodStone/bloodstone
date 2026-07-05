const fs = require("fs");
const path = require("path");

/** Bloodstone mainnet relaunch (Jun 2026). */
const EXPECTED_GENESIS_HASH =
  "df04225074039e630dad825b24818a695462bd19cd585131a0568f50e9bf71d0";

const GENESIS_MISMATCH_RE =
  /Incorrect or no genesis block found|Wrong datadir for network/i;

const GENESIS_MISMATCH_MESSAGE =
  "Your chain data is from the old SpaceXpanse network (before the June 2026 Bloodstone relaunch), " +
  "or the data folder in Settings points at the wrong network. " +
  "Click Reset chain data below — wallet files and bloodstone.conf are kept. " +
  `Expected genesis: ${EXPECTED_GENESIS_HASH.slice(0, 16)}…`;

function lineIndicatesGenesisMismatch(line) {
  return GENESIS_MISMATCH_RE.test(String(line || ""));
}

function scanTextForGenesisMismatch(text) {
  if (!text) {
    return false;
  }
  return String(text)
    .split(/\r?\n/)
    .some(lineIndicatesGenesisMismatch);
}

function scanDebugLogForGenesisMismatch(dataDir, maxBytes = 256 * 1024) {
  if (!dataDir) {
    return false;
  }
  const logPath = path.join(dataDir, "debug.log");
  if (!fs.existsSync(logPath)) {
    return false;
  }
  try {
    const stat = fs.statSync(logPath);
    const start = Math.max(0, stat.size - maxBytes);
    const len = stat.size - start;
    const buf = Buffer.alloc(len);
    const fd = fs.openSync(logPath, "r");
    fs.readSync(fd, buf, 0, len, start);
    fs.closeSync(fd);
    return scanTextForGenesisMismatch(buf.toString("utf8"));
  } catch (_) {
    return false;
  }
}

function hasLegacyChainFolders(dataDir) {
  if (!dataDir) {
    return false;
  }
  return ["blocks", "chainstate"].some((name) =>
    fs.existsSync(path.join(dataDir, name))
  );
}

function genesisMismatchStatus(extra = {}) {
  return {
    genesisMismatch: true,
    syncError: GENESIS_MISMATCH_MESSAGE,
    running: false,
    processManaged: false,
    rpcReachable: false,
    blocks: 0,
    ...extra,
  };
}

module.exports = {
  EXPECTED_GENESIS_HASH,
  GENESIS_MISMATCH_MESSAGE,
  lineIndicatesGenesisMismatch,
  scanTextForGenesisMismatch,
  scanDebugLogForGenesisMismatch,
  hasLegacyChainFolders,
  genesisMismatchStatus,
};
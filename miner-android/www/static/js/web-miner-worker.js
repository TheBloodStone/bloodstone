import {
  blockHashDisplayHex,
  buildHeaderTemplate,
  buildSha256dHeader,
  hashMeetsTarget,
  hashMeetsTargetDisplay,
} from "./mining-math.js";
import { staticUrl } from "./miner-paths.js";

let running = false;
let loopGeneration = 0;
let hashModule = null;
let hashFn = null;
let staticPrefix = "";
let job = null;
let target = 0n;
let hashes = 0;
let hashErrors = 0;
let lastReport = Date.now();
let workerId = 0;
let threadCount = 1;
let algo = "neoscrypt-xaya";
let shareEmitMinMs = 60000;
let lastShareEmitAt = 0;
let inPtr = 0;
let outPtr = 0;
let scratchHeader = null;

async function loadNeoscrypt() {
  const modUrl = staticUrl("/static/lib/neoscrypt.js");
  const createModule =
    (await import(/* @vite-ignore */ modUrl)).default || globalThis.createNeoscryptModule;
  hashModule = await createModule({
    locateFile: (path) => staticUrl(`/static/lib/${path}`),
  });
  hashFn = hashModule.cwrap("neoscrypt_stratum_hash", "number", ["number", "number", "number"]);
}

async function loadYespower() {
  const modUrl = staticUrl("/static/lib/yespower.js");
  const createModule =
    (await import(/* @vite-ignore */ modUrl)).default || globalThis.createYespowerModule;
  hashModule = await createModule({
    locateFile: (path) => staticUrl(`/static/lib/${path}`),
  });
  hashFn = hashModule.cwrap("yespower_stratum_hash", "number", ["number", "number", "number"]);
}

function initHashBuffers() {
  if (!inPtr) {
    inPtr = hashModule._malloc(80);
    outPtr = hashModule._malloc(65);
    scratchHeader = new Uint8Array(80);
  }
}

function readHashHex(heap, ptr) {
  let hex = "";
  for (let i = 0; i < 64; i += 1) {
    const ch = heap[ptr + i];
    if (ch === 0) break;
    hex += String.fromCharCode(ch);
  }
  return /^[0-9a-f]{64}$/i.test(hex) ? hex.toLowerCase() : null;
}

function hashHeaderSync(header) {
  hashModule.HEAPU8.set(header, inPtr);
  const rc = hashFn(inPtr, outPtr, 65);
  if (rc !== 0) {
    return null;
  }
  return readHashHex(hashModule.HEAPU8, outPtr);
}

function reportHashrate() {
  const now = Date.now();
  const elapsed = (now - lastReport) / 1000;
  if (elapsed <= 0) return;
  self.postMessage({ type: "hashrate", hps: hashes / elapsed, workerId });
  hashes = 0;
  lastReport = now;
}

function applyJob(nextJob, targetHex) {
  if (algo === "sha256d") {
    if (!nextJob?.coinb1 || !nextJob?.coinb2 || !nextJob?.prevhash || !nextJob?.nbits || !nextJob?.ntime) {
      return "Invalid SHA256d job from pool";
    }
    job = { ...nextJob, targetHex: String(targetHex).padStart(64, "0") };
    return null;
  }
  if (!nextJob?.headerPrefix || !nextJob?.nbits || !nextJob?.ntime) {
    return "Invalid job payload from pool";
  }
  let nextTarget;
  try {
    nextTarget = BigInt(`0x${String(targetHex).padStart(64, "0")}`);
  } catch (err) {
    return `Invalid pool target: ${err.message}`;
  }
  job = nextJob;
  target = nextTarget;
  return null;
}

function startMiningLoop() {
  loopGeneration += 1;
  const generation = loopGeneration;
  running = true;
  lastReport = Date.now();
  hashes = 0;
  hashErrors = 0;
  mineBatch(generation);
}

function mineSha256dBatch(generation) {
  if (!running || generation !== loopGeneration || !job) return;

  let extranonce2 = workerId;
  let nonce = workerId;
  const stride = Math.max(1, threadCount);
  const batchDeadline = Date.now() + 250;
  const targetHex = job.targetHex || "";

  try {
    while (
      running &&
      generation === loopGeneration &&
      job &&
      Date.now() < batchDeadline
    ) {
      const en2 = extranonce2.toString(16).padStart(8, "0");
      const nonceEnd = nonce + 32 * stride;

      for (; nonce < nonceEnd && running && generation === loopGeneration; nonce += stride) {
        const header = buildSha256dHeader(job, en2, job.ntime, nonce);
        const hashHex = blockHashDisplayHex(header);
        hashes += 1;
        if (!hashHex) {
          hashErrors += 1;
          continue;
        }
        if (hashMeetsTargetDisplay(hashHex, targetHex)) {
          if (workerId !== 0) continue;
          const now = Date.now();
          if (!lastShareEmitAt || now - lastShareEmitAt >= shareEmitMinMs) {
            lastShareEmitAt = now;
            self.postMessage({
              type: "share",
              jobId: job.jobId,
              extranonce2: en2,
              ntime: job.ntime,
              nonce: nonce.toString(16).padStart(8, "0"),
              hash: hashHex,
              version: job.version || "01000000",
            });
          }
        }
      }

      extranonce2 += stride;
    }
  } catch (err) {
    if (generation === loopGeneration) {
      running = false;
      loopGeneration += 1;
      self.postMessage({
        type: "error",
        workerId,
        message: err?.message || String(err),
      });
    }
    return;
  }

  if (generation !== loopGeneration || !running || !job) {
    return;
  }

  if (Date.now() - lastReport >= 1000) {
    reportHashrate();
  }

  setTimeout(() => mineSha256dBatch(generation), 0);
}

function mineBatch(generation) {
  if (!running || generation !== loopGeneration || !job) return;
  if (algo === "sha256d") {
    mineSha256dBatch(generation);
    return;
  }

  let extranonce2 = workerId;
  let nonce = workerId;
  const stride = Math.max(1, threadCount);
  const batchDeadline = Date.now() + 250;

  try {
    while (
      running &&
      generation === loopGeneration &&
      job &&
      Date.now() < batchDeadline
    ) {
      const en2 = extranonce2.toString(16).padStart(4, "0");
      const template = buildHeaderTemplate(job, en2, job.ntime);
      const nonceEnd = nonce + 64 * stride;

      for (; nonce < nonceEnd && running && generation === loopGeneration; nonce += stride) {
        template.view.setUint32(76, nonce >>> 0, true);
        scratchHeader.set(template.fake);
        const hashHex = hashHeaderSync(scratchHeader);
        hashes += 1;
        if (!hashHex) {
          hashErrors += 1;
          continue;
        }
        if (hashMeetsTarget(hashHex, target)) {
          if (workerId !== 0) continue;
          const now = Date.now();
          if (!lastShareEmitAt || now - lastShareEmitAt >= shareEmitMinMs) {
            lastShareEmitAt = now;
            self.postMessage({
              type: "share",
              jobId: job.jobId,
              extranonce2: en2,
              ntime: job.ntime,
              nonce: nonce.toString(16).padStart(8, "0"),
              hash: hashHex,
            });
          }
        }
      }

      extranonce2 += stride;
    }
  } catch (err) {
    if (generation === loopGeneration) {
      running = false;
      loopGeneration += 1;
      self.postMessage({
        type: "error",
        workerId,
        message: err?.message || String(err),
      });
    }
    return;
  }

  if (generation !== loopGeneration || !running || !job) {
    return;
  }

  if (Date.now() - lastReport >= 1000) {
    reportHashrate();
  }

  setTimeout(() => mineBatch(generation), 0);
}

self.onmessage = async (event) => {
  const msg = event.data;
  if (msg.type === "init") {
    workerId = msg.workerId || 0;
    threadCount = Math.max(1, Number(msg.threadCount) || 1);
    shareEmitMinMs = Math.max(5000, Number(msg.shareEmitMinMs) || 60000);
    lastShareEmitAt = 0;
    try {
      algo = msg.algo || "neoscrypt-xaya";
      staticPrefix = msg.staticPrefix || "";
      self.__bloodstoneStaticPrefix = staticPrefix;
      if (algo === "sha256d") {
        /* pure JS double-SHA256 — no WASM */
      } else if (algo === "yespower") {
        await loadYespower();
        initHashBuffers();
      } else {
        await loadNeoscrypt();
        initHashBuffers();
      }
      self.postMessage({ type: "ready", workerId });
    } catch (err) {
      self.postMessage({
        type: "error",
        workerId,
        message: err?.message || String(err),
      });
    }
    return;
  }

  if (msg.type === "start" || msg.type === "job") {
    const err = applyJob(msg.job, msg.targetHex);
    if (err) {
      self.postMessage({ type: "error", workerId, message: err });
      return;
    }
    if (msg.type === "start" || (msg.running && !running)) {
      startMiningLoop();
    }
    return;
  }

  if (msg.type === "stop") {
    loopGeneration += 1;
    running = false;
    job = null;
    reportHashrate();
    return;
  }

  if (msg.type === "ping") {
    self.postMessage({ type: "pong", workerId });
  }
};
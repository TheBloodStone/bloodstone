/* Shared mining helpers for Bloodstone browser miner. */

export const DIFF1_TARGET = 0x00000000ffff00000000000000000000000000000000000000000000000000n;

export const POOL_DIFF_SCALE = {
  "neoscrypt-xaya": 65536,
  neoscrypt: 65536,
  yespower: 65536,
};

export function hexToBytes(hex) {
  const clean = hex.replace(/\s+/g, "");
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i += 1) {
    out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

export function bytesToHex(bytes) {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function swapGetwork(bytes) {
  const out = new Uint8Array(bytes);
  for (let i = 0; i < out.length; i += 4) {
    const t0 = out[i];
    const t1 = out[i + 1];
    out[i] = out[i + 3];
    out[i + 3] = t0;
    out[i + 1] = out[i + 2];
    out[i + 2] = t1;
  }
  return out;
}

export function swapGetworkInPlace(bytes) {
  for (let i = 0; i < bytes.length; i += 4) {
    const t0 = bytes[i];
    const t1 = bytes[i + 1];
    bytes[i] = bytes[i + 3];
    bytes[i + 3] = t0;
    bytes[i + 1] = bytes[i + 2];
    bytes[i + 2] = t1;
  }
  return bytes;
}

const K256 = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

function rotr(x, n) {
  return (x >>> n) | (x << (32 - n));
}

function sha256Block(state, block) {
  const w = new Uint32Array(64);
  for (let i = 0; i < 16; i += 1) {
    w[i] = (
      (block[i * 4] << 24)
      | (block[i * 4 + 1] << 16)
      | (block[i * 4 + 2] << 8)
      | block[i * 4 + 3]
    ) >>> 0;
  }
  for (let i = 16; i < 64; i += 1) {
    const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
    const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
    w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
  }

  let a = state[0];
  let b = state[1];
  let c = state[2];
  let d = state[3];
  let e = state[4];
  let f = state[5];
  let g = state[6];
  let h = state[7];

  for (let i = 0; i < 64; i += 1) {
    const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
    const ch = (e & f) ^ (~e & g);
    const t1 = (h + S1 + ch + K256[i] + w[i]) >>> 0;
    const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
    const maj = (a & b) ^ (a & c) ^ (b & c);
    const t2 = (S0 + maj) >>> 0;
    h = g;
    g = f;
    f = e;
    e = (d + t1) >>> 0;
    d = c;
    c = b;
    b = a;
    a = (t1 + t2) >>> 0;
  }

  state[0] = (state[0] + a) >>> 0;
  state[1] = (state[1] + b) >>> 0;
  state[2] = (state[2] + c) >>> 0;
  state[3] = (state[3] + d) >>> 0;
  state[4] = (state[4] + e) >>> 0;
  state[5] = (state[5] + f) >>> 0;
  state[6] = (state[6] + g) >>> 0;
  state[7] = (state[7] + h) >>> 0;
}

export function sha256(bytes) {
  const bitLen = bytes.length * 8;
  const padLen = ((bytes.length + 9 + 63) & ~63);
  const padded = new Uint8Array(padLen);
  padded.set(bytes);
  padded[bytes.length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(padLen - 4, bitLen >>> 0, false);
  view.setUint32(padLen - 8, Math.floor(bitLen / 0x100000000), false);

  const state = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);
  for (let offset = 0; offset < padLen; offset += 64) {
    sha256Block(state, padded.subarray(offset, offset + 64));
  }

  const out = new Uint8Array(32);
  const outView = new DataView(out.buffer);
  for (let i = 0; i < 8; i += 1) {
    outView.setUint32(i * 4, state[i], false);
  }
  return out;
}

export function doubleSha256(bytes) {
  return sha256(sha256(bytes));
}

export function extranonceBytes(hexStr, size = 2) {
  const padded = String(hexStr).replace(/\s+/g, "").toLowerCase().padStart(size * 2, "0");
  const bytes = hexToBytes(padded);
  return bytes.slice(-size);
}

/** Match cpuminer-opt / Bitcoin stratum: hex2bin then le32dec. */
export function stratumWordFromHex(hexStr) {
  const bytes = hexToBytes(String(hexStr).replace(/\s+/g, "").toLowerCase().padStart(8, "0").slice(-8));
  return (
    bytes[0]
    | (bytes[1] << 8)
    | (bytes[2] << 16)
    | ((bytes[3] << 24) >>> 0)
  );
}

export function buildHeaderTemplate(job, extranonce2, ntimeHex) {
  const en1 = extranonceBytes(job.extranonce1, 2);
  const en2 = extranonceBytes(extranonce2, 2);
  const prefix = hexToBytes(job.headerPrefix);
  const real = new Uint8Array(prefix.length + 2 + 2);
  real.set(prefix, 0);
  real.set(en1, prefix.length);
  real.set(en2, prefix.length + 2);

  const fake = new Uint8Array(80);
  const view = new DataView(fake.buffer);
  view.setUint32(0, 0, true);
  view.setUint32(68, stratumWordFromHex(ntimeHex), true);
  view.setUint32(72, stratumWordFromHex(job.nbits), true);
  view.setUint32(76, 0, true);
  fake.set(doubleSha256(real), 36);
  return { fake, view };
}

export function swappedHeaderForNonce(template, nonce, scratch) {
  template.view.setUint32(76, nonce >>> 0, true);
  scratch.set(template.fake);
  return swapGetworkInPlace(scratch);
}

export function buildFakeHeader(job, extranonce2, ntimeHex, nonce) {
  const { fake, view } = buildHeaderTemplate(job, extranonce2, ntimeHex);
  view.setUint32(76, nonce >>> 0, true);
  return fake;
}

export function difficultyToTarget(difficulty) {
  if (difficulty <= 0) {
    return DIFF1_TARGET;
  }
  const scaled = BigInt(Math.floor(difficulty * 1e12));
  const denom = BigInt(Math.floor(1e12));
  return DIFF1_TARGET * denom / scaled;
}

export function stratumDifficultyToTarget(stratumDiff, algo) {
  const scale = POOL_DIFF_SCALE[algo] || 65536;
  if (!(stratumDiff > 0)) {
    return DIFF1_TARGET;
  }
  // target = DIFF1 * scale / stratumDiff (integer math avoids float drift)
  const scaleBig = BigInt(scale);
  const stratumScaled = BigInt(Math.round(Number(stratumDiff) * 1_000_000_000_000));
  if (stratumScaled <= 0n) {
    return DIFF1_TARGET;
  }
  return (DIFF1_TARGET * scaleBig * 1_000_000_000_000n) / stratumScaled;
}

export function targetFromHex(hex) {
  const clean = String(hex || "").replace(/\s+/g, "").toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(clean)) {
    throw new Error("invalid target hex");
  }
  return BigInt(`0x${clean}`);
}

export function hashMeetsTarget(hashHex, targetBigInt) {
  const value = BigInt("0x" + hashHex);
  return value <= targetBigInt;
}

export function formatHashrate(hps) {
  if (hps >= 1e6) return `${(hps / 1e6).toFixed(2)} MH/s`;
  if (hps >= 1e3) return `${(hps / 1e3).toFixed(2)} kH/s`;
  return `${hps.toFixed(2)} H/s`;
}
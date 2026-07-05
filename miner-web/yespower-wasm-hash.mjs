#!/usr/bin/env node
/**
 * Compute yespower PoW hash the same way the browser WASM worker does (legacy swapped-work path).
 * Usage: node yespower-wasm-hash.mjs <160-char canonical header hex>
 */
import { pathToFileURL } from "url";

const hex = (process.argv[2] || "").trim().toLowerCase();
if (!/^[0-9a-f]{160}$/.test(hex)) {
  process.stderr.write("usage: yespower-wasm-hash.mjs <160-char header hex>\n");
  process.exit(2);
}

const libDir = "/root/bloodstone-miner-web/static/lib";
// yespower.js uses import.meta; Node cannot load it as .js — use .mjs copy.
const mod = await import(pathToFileURL(`${libDir}/yespower.mjs`).href);
const createModule = mod.default;
const Module = await createModule({
  locateFile: (p) => `${libDir}/${p}`,
});
const hashFn = Module.cwrap("yespower_stratum_hash", "number", ["number", "number", "number"]);
const inPtr = Module._malloc(80);
const outPtr = Module._malloc(65);

function swapGetwork(buf) {
  for (let i = 0; i < buf.length; i += 4) {
    const t0 = buf[i];
    const t1 = buf[i + 1];
    buf[i] = buf[i + 3];
    buf[i + 3] = t0;
    buf[i + 1] = buf[i + 2];
    buf[i + 2] = t1;
  }
}

const canonical = new Uint8Array(80);
for (let i = 0; i < 80; i++) {
  canonical[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
}
const swapped = new Uint8Array(canonical);
swapGetwork(swapped);

Module.HEAPU8.set(swapped, inPtr);
const rc = hashFn(inPtr, outPtr, 65);
if (rc !== 0) {
  process.stderr.write(`yespower_stratum_hash failed: ${rc}\n`);
  process.exit(4);
}
let out = "";
for (let i = 0; i < 64; i++) out += String.fromCharCode(Module.HEAPU8[outPtr + i]);
process.stdout.write(out);
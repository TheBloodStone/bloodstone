/**
 * TLS 1.3 client crypto (RFC 8446) for BSM4 mesh handshake — browser-native flight 2.
 */

const CIPHER_TLS_AES_128_GCM_SHA256 = 0x1301;
const CIPHER_TLS_AES_256_GCM_SHA384 = 0x1302;

const CIPHER_CFG = {
  [CIPHER_TLS_AES_128_GCM_SHA256]: { hashLen: 32, keyLen: 16, ivLen: 12, hash: "SHA-256" },
  [CIPHER_TLS_AES_256_GCM_SHA384]: { hashLen: 48, keyLen: 32, ivLen: 12, hash: "SHA-384" },
};

async function digest(hashName, data) {
  const buf = data instanceof ArrayBuffer ? data : data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
  return new Uint8Array(await crypto.subtle.digest(hashName, buf));
}

async function hmac(hashName, key, data) {
  const cryptoKey = await crypto.subtle.importKey("raw", key, { name: "HMAC", hash: hashName }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", cryptoKey, data));
}

async function hkdfExtract(hashName, salt, ikm) {
  const n = hashName === "SHA-384" ? 48 : 32;
  const zero = new Uint8Array(n);
  const s = salt?.length ? salt : zero;
  const i = ikm?.length ? ikm : zero;
  return hmac(hashName, s, i);
}

async function hkdfExpandLabel(hashName, secret, label, context, length) {
  const fullLabel = new TextEncoder().encode(`tls13 ${label}`);
  const info = new Uint8Array(2 + 1 + fullLabel.length + 1 + (context?.length || 0));
  info[0] = (length >> 8) & 0xff;
  info[1] = length & 0xff;
  info[2] = fullLabel.length;
  info.set(fullLabel, 3);
  info[3 + fullLabel.length] = context?.length || 0;
  if (context?.length) info.set(context, 4 + fullLabel.length);
  let out = new Uint8Array(0);
  let t = new Uint8Array(0);
  let counter = 1;
  while (out.length < length) {
    const input = new Uint8Array(t.length + info.length + 1);
    input.set(t, 0);
    input.set(info, t.length);
    input[input.length - 1] = counter;
    t = await hmac(hashName, secret, input);
    const merged = new Uint8Array(out.length + t.length);
    merged.set(out, 0);
    merged.set(t, out.length);
    out = merged;
    counter += 1;
  }
  return out.subarray(0, length);
}

async function deriveSecret(hashName, secret, label, messages) {
  const ctx = await digest(hashName, messages);
  const n = hashName === "SHA-384" ? 48 : 32;
  return hkdfExpandLabel(hashName, secret, label, ctx, n);
}

async function trafficKeys(hashName, secret, label, messages, cfg) {
  const hs = await deriveSecret(hashName, secret, label, messages);
  const key = await hkdfExpandLabel(hashName, hs, "key", new Uint8Array(0), cfg.keyLen);
  const iv = await hkdfExpandLabel(hashName, hs, "iv", new Uint8Array(0), cfg.ivLen);
  return { key, iv };
}

function makeNonce(iv, seq) {
  const nonce = new Uint8Array(12);
  nonce.set(iv.subarray(0, 4), 0);
  const seqBytes = new Uint8Array(8);
  const view = new DataView(seqBytes.buffer);
  view.setBigUint64(0, BigInt(seq));
  for (let i = 0; i < 8; i += 1) nonce[4 + i] = iv[4 + i] ^ seqBytes[i];
  return nonce;
}

async function aeadDecrypt(cfg, key, iv, seq, ciphertext, recordHeader) {
  const cryptoKey = await crypto.subtle.importKey("raw", key, { name: "AES-GCM" }, false, ["decrypt"]);
  const nonce = makeNonce(iv, seq);
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce, additionalData: recordHeader }, cryptoKey, ciphertext);
  return new Uint8Array(plain);
}

async function aeadEncrypt(cfg, key, iv, seq, plaintext, recordHeader) {
  const cryptoKey = await crypto.subtle.importKey("raw", key, { name: "AES-GCM" }, false, ["encrypt"]);
  const nonce = makeNonce(iv, seq);
  const cipher = await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce, additionalData: recordHeader }, cryptoKey, plaintext);
  return new Uint8Array(cipher);
}

function concatBytes(...parts) {
  const total = parts.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(total);
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
}

function handshakeMessageFromRecord(record) {
  return record.subarray(5);
}

export function parseTlsRecords(bytes) {
  const records = [];
  let pos = 0;
  while (pos + 5 <= bytes.length) {
    const len = (bytes[pos + 3] << 8) | bytes[pos + 4];
    const end = pos + 5 + len;
    if (end > bytes.length) break;
    records.push(bytes.subarray(pos, end));
    pos = end;
  }
  return records;
}

export function tlsStreamComplete(bytes) {
  const recs = parseTlsRecords(bytes);
  const consumed = recs.reduce((n, r) => n + r.length, 0);
  return recs.length > 0 && consumed === bytes.length;
}

export function parseServerHello(serverFlight) {
  for (const rec of parseTlsRecords(serverFlight)) {
    if (rec[0] !== 0x16 || rec.length < 6 || rec[5] !== 0x02) continue;
    const body = rec.subarray(5);
    const hsLen = (body[1] << 16) | (body[2] << 8) | body[3];
    const hs = body.subarray(4, 4 + hsLen);
    let pos = 2;
    const serverRandom = hs.subarray(pos, pos + 32);
    pos += 32;
    const sidLen = hs[pos++];
    pos += sidLen;
    const cipher = (hs[pos] << 8) | hs[pos + 1];
    pos += 2;
    pos += 1;
    const extLen = (hs[pos] << 8) | hs[pos + 1];
    pos += 2;
    const extEnd = pos + extLen;
    let serverPublicKey = null;
    while (pos + 4 <= extEnd) {
      const extType = (hs[pos] << 8) | hs[pos + 1];
      const eLen = (hs[pos + 2] << 8) | hs[pos + 3];
      pos += 4;
      const ext = hs.subarray(pos, pos + eLen);
      pos += eLen;
      if (extType === 0x0033 && ext.length >= 4) {
        const kLen = (ext[2] << 8) | ext[3];
        if (ext.length >= 4 + kLen) serverPublicKey = ext.subarray(4, 4 + kLen);
      }
    }
    if (!serverPublicKey) return null;
    return { record: rec, serverRandom, cipher, serverPublicKey };
  }
  return null;
}

export function flightHasAlert(bytes) {
  return parseTlsRecords(bytes).some((r) => r[0] === 0x15);
}

export async function generateX25519Keypair() {
  const privateKey = await crypto.subtle.generateKey({ name: "X25519", namedCurve: "X25519" }, true, ["deriveBits"]);
  const publicKeyRaw = new Uint8Array(await crypto.subtle.exportKey("raw", privateKey.publicKey));
  const privateKeyRaw = new Uint8Array(await crypto.subtle.exportKey("pkcs8", privateKey));
  return { privateKey, publicKeyRaw, privateKeyHandle: privateKey };
}

export function patchClientHelloRandom(record, clientRandom) {
  const out = new Uint8Array(record);
  out.set(clientRandom, 11);
  return out;
}

export function patchClientHelloKeyShare(record, publicKey) {
  const needle = new Uint8Array([0x00, 0x1d, 0x00, 0x20]);
  for (let i = 0; i <= record.length - needle.length - publicKey.length; i += 1) {
    let ok = true;
    for (let j = 0; j < needle.length; j += 1) {
      if (record[i + j] !== needle[j]) ok = false;
    }
    if (!ok) continue;
    const out = new Uint8Array(record);
    out.set(publicKey, i + needle.length);
    return out;
  }
  throw new Error("ClientHello missing X25519 key_share");
}

async function decryptServerHandshakes({ hashName, cfg, clientHello, serverHelloRecord, serverFlight, handshakeSecret }) {
  const transcript = concatBytes(handshakeMessageFromRecord(clientHello), handshakeMessageFromRecord(serverHelloRecord));
  const { key, iv } = await trafficKeys(hashName, handshakeSecret, "s hs traffic", transcript, cfg);
  const parts = [];
  let seq = 0;
  for (const rec of parseTlsRecords(serverFlight)) {
    if (rec[0] !== 0x17) continue;
    const inner = await aeadDecrypt(cfg, key, iv, seq, rec.subarray(5), rec.subarray(0, 5));
    seq += 1;
    if (inner[inner.length - 1] !== 0x16) continue;
    const hsPlain = inner.subarray(0, inner.length - 1);
    let pos = 0;
    while (pos + 4 <= hsPlain.length) {
      const msgLen = (hsPlain[pos + 1] << 16) | (hsPlain[pos + 2] << 8) | hsPlain[pos + 3];
      parts.push(hsPlain.subarray(pos, pos + 4 + msgLen));
      pos += 4 + msgLen;
    }
  }
  return concatBytes(transcript, ...parts);
}

export async function buildClientFlight2({ clientHelloRecord, serverFlight, privateKey }) {
  const sh = parseServerHello(serverFlight);
  if (!sh?.serverPublicKey) throw new Error("ServerHello missing key_share");
  const cfg = CIPHER_CFG[sh.cipher];
  if (!cfg) throw new Error(`unsupported cipher 0x${sh.cipher.toString(16)}`);
  const hashName = cfg.hash;

  const serverPub = await crypto.subtle.importKey("raw", sh.serverPublicKey, { name: "X25519", namedCurve: "X25519" }, false, []);
  const sharedBits = await crypto.subtle.deriveBits({ name: "X25519", public: serverPub }, privateKey, 256);
  const shared = new Uint8Array(sharedBits);

  const earlySecret = await hkdfExtract(hashName, new Uint8Array(0), new Uint8Array(0));
  const derived = await hkdfExpandLabel(hashName, earlySecret, "derived", await digest(hashName, new Uint8Array(0)), cfg.hashLen);
  const handshakeSecret = await hkdfExtract(hashName, derived, shared);
  const transcriptToSh = concatBytes(handshakeMessageFromRecord(clientHelloRecord), handshakeMessageFromRecord(sh.record));
  const transcriptFull = await decryptServerHandshakes({
    hashName,
    cfg,
    clientHello: clientHelloRecord,
    serverHelloRecord: sh.record,
    serverFlight,
    handshakeSecret,
  });

  const { key: cKey, iv: cIv } = await trafficKeys(hashName, handshakeSecret, "c hs traffic", transcriptToSh, cfg);
  const cHsSecret = await deriveSecret(hashName, handshakeSecret, "c hs traffic", transcriptToSh);
  const finishedKey = await hkdfExpandLabel(hashName, cHsSecret, "finished", new Uint8Array(0), cfg.hashLen);
  const verifyData = await hmac(hashName, finishedKey, await digest(hashName, transcriptFull));

  const finishedHs = concatBytes(new Uint8Array([0x14, 0, 0, verifyData.length]), verifyData);
  const finishedInner = concatBytes(finishedHs, new Uint8Array([0x16]));
  const ciphertextLen = finishedInner.length + 16;
  const header = new Uint8Array([0x17, 0x03, 0x03, (ciphertextLen >> 8) & 0xff, ciphertextLen & 0xff]);
  const ciphertext = await aeadEncrypt(cfg, cKey, cIv, 0, finishedInner, header);
  const finishedRecord = concatBytes(header, ciphertext);
  const ccsRecord = new Uint8Array([0x14, 0x03, 0x03, 0x00, 0x01, 0x01]);
  const flight2 = concatBytes(ccsRecord, finishedRecord);

  return {
    flight2,
    cipher: sh.cipher,
    summary: `CCS + ClientFinished (${flight2.length} B) cipher=0x${sh.cipher.toString(16)}`,
  };
}

export async function encryptClientAppData({
  clientHelloRecord,
  serverFlight,
  privateKey,
  plaintext,
  seqOffset = 0,
}) {
  const sh = parseServerHello(serverFlight);
  if (!sh) throw new Error("ServerHello missing");
  const cfg = CIPHER_CFG[sh.cipher];
  if (!cfg) throw new Error(`unsupported cipher 0x${sh.cipher.toString(16)}`);
  const hashName = cfg.hash;

  const serverPub = await crypto.subtle.importKey("raw", sh.serverPublicKey, { name: "X25519", namedCurve: "X25519" }, false, []);
  const shared = new Uint8Array(await crypto.subtle.deriveBits({ name: "X25519", public: serverPub }, privateKey, 256));
  const earlySecret = await hkdfExtract(hashName, new Uint8Array(0), new Uint8Array(0));
  const derived = await hkdfExpandLabel(hashName, earlySecret, "derived", await digest(hashName, new Uint8Array(0)), cfg.hashLen);
  const handshakeSecret = await hkdfExtract(hashName, derived, shared);
  const transcriptFull = await decryptServerHandshakes({
    hashName,
    cfg,
    clientHello: clientHelloRecord,
    serverHelloRecord: sh.record,
    serverFlight,
    handshakeSecret,
  });
  const derivedEmpty = await deriveSecret(hashName, handshakeSecret, "derived", new Uint8Array(0));
  const masterSecret = await hkdfExtract(hashName, derivedEmpty, new Uint8Array(cfg.hashLen));
  const { key, iv } = await trafficKeys(hashName, masterSecret, "c ap traffic", transcriptFull, cfg);

  const plainBytes = typeof plaintext === "string" ? new TextEncoder().encode(plaintext) : plaintext;
  const inner = concatBytes(plainBytes, new Uint8Array([0x17]));
  const ciphertextLen = inner.length + 16;
  const header = new Uint8Array([0x17, 0x03, 0x03, (ciphertextLen >> 8) & 0xff, ciphertextLen & 0xff]);
  const ciphertext = await aeadEncrypt(cfg, key, iv, seqOffset, inner, header);
  return concatBytes(header, ciphertext);
}

export async function decryptServerAppData({
  clientHelloRecord,
  serverFlight,
  privateKey,
  appDataBytes,
  seqOffset = 0,
}) {
  const sh = parseServerHello(serverFlight);
  if (!sh) throw new Error("ServerHello missing");
  const cfg = CIPHER_CFG[sh.cipher];
  if (!cfg) throw new Error(`unsupported cipher 0x${sh.cipher.toString(16)}`);
  const hashName = cfg.hash;

  const serverPub = await crypto.subtle.importKey("raw", sh.serverPublicKey, { name: "X25519", namedCurve: "X25519" }, false, []);
  const shared = new Uint8Array(await crypto.subtle.deriveBits({ name: "X25519", public: serverPub }, privateKey, 256));
  const earlySecret = await hkdfExtract(hashName, new Uint8Array(0), new Uint8Array(0));
  const derived = await hkdfExpandLabel(hashName, earlySecret, "derived", await digest(hashName, new Uint8Array(0)), cfg.hashLen);
  const handshakeSecret = await hkdfExtract(hashName, derived, shared);
  const transcriptFull = await decryptServerHandshakes({
    hashName,
    cfg,
    clientHello: clientHelloRecord,
    serverHelloRecord: sh.record,
    serverFlight,
    handshakeSecret,
  });
  const derivedEmpty = await deriveSecret(hashName, handshakeSecret, "derived", new Uint8Array(0));
  const masterSecret = await hkdfExtract(hashName, derivedEmpty, new Uint8Array(cfg.hashLen));
  const { key, iv } = await trafficKeys(hashName, masterSecret, "s ap traffic", transcriptFull, cfg);

  const parts = [];
  let seq = seqOffset;
  let records = 0;
  let ticketRecords = 0;
  for (const rec of parseTlsRecords(appDataBytes)) {
    if (rec[0] !== 0x17) continue;
    const inner = await aeadDecrypt(cfg, key, iv, seq, rec.subarray(5), rec.subarray(0, 5));
    seq += 1;
    records += 1;
    const contentType = inner[inner.length - 1];
    if (contentType === 0x16) {
      ticketRecords += 1;
      continue;
    }
    if (contentType === 0x17) parts.push(inner.subarray(0, inner.length - 1));
  }
  const plaintext = concatBytes(...parts);
  const preview = new TextDecoder().decode(plaintext.subarray(0, 512));
  return {
    plaintext,
    preview,
    isHttp: preview.startsWith("HTTP/") || preview.startsWith("<"),
    records,
    ticketRecords,
    nextSeq: seq,
  };
}

export { CIPHER_TLS_AES_128_GCM_SHA256, CIPHER_TLS_AES_256_GCM_SHA384 };
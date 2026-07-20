var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);

// node_modules/@noble/secp256k1/index.js
var secp256k1_CURVE = Object.freeze({
  p: 0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffefffffc2fn,
  n: 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141n,
  h: 1n,
  a: 0n,
  b: 7n,
  Gx: 0x79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798n,
  Gy: 0x483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8n
});
var { p: P, n: N, Gx, Gy, b: _b } = secp256k1_CURVE;
var L = 32;
var L2 = 64;
var lengths = {
  publicKey: L + 1,
  publicKeyUncompressed: L2 + 1,
  signature: L2,
  // 48-byte keygen seed floor: 384 bits exceeds FIPS 186-5 Table A.2's
  // 352-bit recommendation for 256-bit prime curves.
  seed: L + L / 2
};
var err = (message = "", E = Error) => {
  const e = new E(message);
  const { captureStackTrace } = Error;
  if (typeof captureStackTrace === "function")
    captureStackTrace(e, err);
  throw e;
};
var isBytes = (a) => a instanceof Uint8Array || ArrayBuffer.isView(a) && a.constructor.name === "Uint8Array" && a.BYTES_PER_ELEMENT === 1;
var abytes = (value, length, title = "") => {
  const bytes = isBytes(value);
  const len = value?.length;
  const needsLen = length !== void 0;
  if (!bytes || needsLen && len !== length) {
    const prefix = title && `"${title}" `;
    const ofLen = needsLen ? ` of length ${length}` : "";
    const got = bytes ? `length=${len}` : `type=${typeof value}`;
    const msg = prefix + "expected Uint8Array" + ofLen + ", got " + got;
    return bytes ? err(msg, RangeError) : err(msg, TypeError);
  }
  return value;
};
var u8n = (len) => new Uint8Array(len);
var padh = (n, pad) => n.toString(16).padStart(pad, "0");
var bytesToHex = (b) => {
  let hex = "";
  for (const e of abytes(b))
    hex += padh(e, 2);
  return hex;
};
var C = { _0: 48, _9: 57, A: 65, F: 70, a: 97, f: 102 };
var _ch = (ch) => ch >= C._0 && ch <= C._9 ? ch - C._0 : ch >= C.A && ch <= C.F ? ch - (C.A - 10) : ch >= C.a && ch <= C.f ? ch - (C.a - 10) : void 0;
var hexToBytes = (hex) => {
  const e = "hex invalid";
  if (typeof hex !== "string")
    return err(e);
  const hl = hex.length;
  const al = hl / 2;
  if (hl % 2)
    return err(e);
  const array = u8n(al);
  for (let ai = 0, hi = 0; ai < al; ai++, hi += 2) {
    const n1 = _ch(hex.charCodeAt(hi));
    const n2 = _ch(hex.charCodeAt(hi + 1));
    if (n1 === void 0 || n2 === void 0)
      return err(e);
    array[ai] = n1 * 16 + n2;
  }
  return array;
};
var subtle = () => globalThis?.crypto?.subtle ?? err("crypto.subtle must be defined, consider polyfill");
var concatBytes = (...arrs) => {
  let len = 0;
  for (const a of arrs)
    len += abytes(a).length;
  const r = u8n(len);
  let pad = 0;
  for (const a of arrs)
    r.set(a, pad), pad += a.length;
  return r;
};
var randomBytes = (len = L) => (globalThis?.crypto).getRandomValues(u8n(len));
var big = BigInt;
var arange = (n, min, max, msg = "bad number: out of range") => {
  if (typeof n !== "bigint")
    return err(msg, TypeError);
  if (min <= n && n < max)
    return n;
  return err(msg, RangeError);
};
var M = (a, b = P) => {
  const r = a % b;
  return r >= 0n ? r : b + r;
};
var modN = (a) => M(a, N);
var invert = (num, md) => {
  if (num === 0n || md <= 0n)
    err("no inverse n=" + num + " mod=" + md);
  let a = M(num, md), b = md, x = 0n, y = 1n, u = 1n, v = 0n;
  while (a !== 0n) {
    const q = b / a, r = b % a;
    const m = x - u * q, n = y - v * q;
    b = a, a = r, x = u, y = v, u = m, v = n;
  }
  return b === 1n ? M(x, md) : err("no inverse");
};
var callHash = (name) => {
  const fn = hashes[name];
  if (typeof fn !== "function")
    err("hashes." + name + " not set");
  return fn;
};
var gh = (name, a, b) => abytes(callHash(name)(a, b), L, "digest");
var gha = (name, a, b) => Promise.resolve(callHash(name)(a, b)).then((r) => abytes(r, L, "digest"));
var apoint = (p) => p instanceof Point ? p : err("Point expected");
var koblitz = (x) => M(M(x * x) * x + _b);
var FpIsValid = (n) => arange(n, 0n, P);
var FpIsValidNot0 = (n) => arange(n, 1n, P);
var FnIsValidNot0 = (n) => arange(n, 1n, N);
var isEven = (y) => !(y & 1n);
var u8of = (n) => Uint8Array.of(n);
var getPrefix = (y) => u8of(isEven(y) ? 2 : 3);
var lift_x = (x) => {
  const c = koblitz(FpIsValidNot0(x));
  let r = 1n;
  for (let num = c, e = (P + 1n) / 4n; e > 0n; e >>= 1n) {
    if (e & 1n)
      r = r * num % P;
    num = num * num % P;
  }
  if (M(r * r) !== c)
    err("sqrt invalid");
  return isEven(r) ? r : M(-r);
};
var _Point = class _Point {
  constructor(X, Y, Z) {
    __publicField(this, "X");
    __publicField(this, "Y");
    __publicField(this, "Z");
    this.X = FpIsValid(X);
    this.Y = FpIsValidNot0(Y);
    this.Z = FpIsValid(Z);
    Object.freeze(this);
  }
  /** Returns the shared curve metadata object by reference.
   * It is readonly only at type level, and mutating it won't retarget arithmetic,
   * which already uses module-load snapshots. */
  static CURVE() {
    return secp256k1_CURVE;
  }
  /** Create 3d xyz point from 2d xy. (0, 0) => (0, 1, 0), not (0, 0, 1) */
  static fromAffine(ap) {
    const { x, y } = ap;
    return x === 0n && y === 0n ? I : new _Point(x, y, 1n);
  }
  /** Convert Uint8Array or hex string to Point. */
  static fromBytes(bytes) {
    abytes(bytes);
    const { publicKey: comp, publicKeyUncompressed: uncomp } = lengths;
    let p = void 0;
    const length = bytes.length;
    const head = bytes[0];
    const tail = bytes.subarray(1);
    const x = sliceBytesNumBE(tail, 0, L);
    if (length === comp && (head === 2 || head === 3)) {
      let y = lift_x(x);
      if (head === 3)
        y = M(-y);
      p = new _Point(x, y, 1n);
    }
    if (length === uncomp && head === 4)
      p = new _Point(x, sliceBytesNumBE(tail, L, L2), 1n);
    return p ? p.assertValidity() : err("bad point: not on curve");
  }
  static fromHex(hex) {
    return _Point.fromBytes(hexToBytes(hex));
  }
  get x() {
    return this.toAffine().x;
  }
  get y() {
    return this.toAffine().y;
  }
  /** Equality check: compare points P&Q. */
  equals(other) {
    const { X: X1, Y: Y1, Z: Z1 } = this;
    const { X: X2, Y: Y2, Z: Z2 } = apoint(other);
    const X1Z2 = M(X1 * Z2);
    const X2Z1 = M(X2 * Z1);
    const Y1Z2 = M(Y1 * Z2);
    const Y2Z1 = M(Y2 * Z1);
    return X1Z2 === X2Z1 && Y1Z2 === Y2Z1;
  }
  is0() {
    return this.equals(I);
  }
  /** Flip point over y coordinate. */
  negate() {
    return new _Point(this.X, M(-this.Y), this.Z);
  }
  /** Point doubling: P+P, complete formula. */
  double() {
    return this.add(this);
  }
  /**
   * Point addition: P+Q, complete, exception-free formula
   * (Renes-Costello-Batina, algo 1 of [2015/1060](https://eprint.iacr.org/2015/1060)).
   * Cost: `12M + 0S + 3*a + 3*b3 + 23add`.
   */
  // prettier-ignore
  add(other) {
    const { X: X1, Y: Y1, Z: Z1 } = this;
    const { X: X2, Y: Y2, Z: Z2 } = apoint(other);
    const a = 0n;
    const b = _b;
    let X3 = 0n, Y3 = 0n, Z3 = 0n;
    const b3 = M(b * 3n);
    let t0 = M(X1 * X2), t1 = M(Y1 * Y2), t2 = M(Z1 * Z2), t3 = M(X1 + Y1);
    let t4 = M(X2 + Y2);
    t3 = M(t3 * t4);
    t4 = M(t0 + t1);
    t3 = M(t3 - t4);
    t4 = M(X1 + Z1);
    let t5 = M(X2 + Z2);
    t4 = M(t4 * t5);
    t5 = M(t0 + t2);
    t4 = M(t4 - t5);
    t5 = M(Y1 + Z1);
    X3 = M(Y2 + Z2);
    t5 = M(t5 * X3);
    X3 = M(t1 + t2);
    t5 = M(t5 - X3);
    Z3 = M(a * t4);
    X3 = M(b3 * t2);
    Z3 = M(X3 + Z3);
    X3 = M(t1 - Z3);
    Z3 = M(t1 + Z3);
    Y3 = M(X3 * Z3);
    t1 = M(t0 + t0);
    t1 = M(t1 + t0);
    t2 = M(a * t2);
    t4 = M(b3 * t4);
    t1 = M(t1 + t2);
    t2 = M(t0 - t2);
    t2 = M(a * t2);
    t4 = M(t4 + t2);
    t0 = M(t1 * t4);
    Y3 = M(Y3 + t0);
    t0 = M(t5 * t4);
    X3 = M(t3 * X3);
    X3 = M(X3 - t0);
    t0 = M(t3 * t1);
    Z3 = M(t5 * Z3);
    Z3 = M(Z3 + t0);
    return new _Point(X3, Y3, Z3);
  }
  subtract(other) {
    return this.add(apoint(other).negate());
  }
  /**
   * Point-by-scalar multiplication. Scalar must be in range 1 <= n < CURVE.n.
   * Uses {@link wNAF} for base point.
   * Uses fake point to mitigate leakage shape in JS, not as a hard constant-time guarantee.
   * @param n scalar by which point is multiplied
   * @param safe safe mode guards against timing attacks; unsafe mode is faster
   */
  multiply(n, safe = true) {
    if (!safe && n === 0n)
      return I;
    FnIsValidNot0(n);
    if (n === 1n)
      return this;
    if (this.equals(G))
      return wNAF(n).p;
    let p = I;
    let f = G;
    for (let d = this; n > 0n; d = d.double(), n >>= 1n) {
      if (n & 1n)
        p = p.add(d);
      else if (safe)
        f = f.add(d);
    }
    return p;
  }
  multiplyUnsafe(scalar) {
    return this.multiply(scalar, false);
  }
  /** Convert point to 2d xy affine point. (X, Y, Z) ∋ (x=X/Z, y=Y/Z) */
  toAffine() {
    const { X: x, Y: y, Z: z } = this;
    if (this.equals(I))
      return { x: 0n, y: 0n };
    if (z === 1n)
      return { x, y };
    const iz = invert(z, P);
    if (M(z * iz) !== 1n)
      err("inverse invalid");
    return { x: M(x * iz), y: M(y * iz) };
  }
  /** Checks if the point is valid and on-curve. */
  assertValidity() {
    const { x, y } = this.toAffine();
    FpIsValidNot0(x);
    FpIsValidNot0(y);
    return M(y * y) === koblitz(x) ? this : err("bad point: not on curve");
  }
  /** Converts point to 33/65-byte Uint8Array. */
  toBytes(isCompressed = true) {
    const { x, y } = this.assertValidity().toAffine();
    const x32b = numTo32b(x);
    if (isCompressed)
      return concatBytes(getPrefix(y), x32b);
    return concatBytes(u8of(4), x32b, numTo32b(y));
  }
  toHex(isCompressed) {
    return bytesToHex(this.toBytes(isCompressed));
  }
};
__publicField(_Point, "BASE");
__publicField(_Point, "ZERO");
var Point = _Point;
var G = new Point(Gx, Gy, 1n);
var I = new Point(0n, 1n, 0n);
Point.BASE = G;
Point.ZERO = I;
var bytesToNumBE = (b) => big("0x" + (bytesToHex(b) || "0"));
var sliceBytesNumBE = (b, from, to) => bytesToNumBE(b.subarray(from, to));
var B256 = 2n ** 256n;
var numTo32b = (num) => hexToBytes(padh(arange(num, 0n, B256), L2));
var secretKeyToScalar = (secretKey) => {
  const num = bytesToNumBE(abytes(secretKey, L, "secret key"));
  return arange(num, 1n, N, "invalid secret key: outside of range");
};
var highS = (n) => n > N >> 1n;
var getPublicKey = (privKey, isCompressed = true) => {
  return G.multiply(secretKeyToScalar(privKey)).toBytes(isCompressed);
};
var assertRecoveryBit = (recovery) => [0, 1, 2, 3].includes(recovery) ? recovery : err("invalid recovery id");
var assertSigFormat = (format) => {
  if (format === SIG_DER)
    err('Signature format "der" is not supported: switch to noble-curves');
  if (format != null && format !== SIG_COMPACT && format !== SIG_RECOVERED)
    err("Signature format must be one of: compact, recovered, der");
};
var assertSigLength = (sig, format = SIG_COMPACT) => {
  assertSigFormat(format);
  const len = lengths.signature + Number(format === SIG_RECOVERED);
  if (sig.length !== len)
    err(`Signature format "${format}" expects Uint8Array with length ${len}`);
};
var Signature = class _Signature {
  constructor(r, s, recovery) {
    __publicField(this, "r");
    __publicField(this, "s");
    __publicField(this, "recovery");
    this.r = FnIsValidNot0(r);
    this.s = FnIsValidNot0(s);
    if (recovery != null)
      this.recovery = assertRecoveryBit(recovery);
    Object.freeze(this);
  }
  static fromBytes(b, format = SIG_COMPACT) {
    assertSigLength(b, format);
    let rec;
    if (format === SIG_RECOVERED) {
      rec = b[0];
      b = b.subarray(1);
    }
    const r = sliceBytesNumBE(b, 0, L);
    const s = sliceBytesNumBE(b, L, L2);
    return new _Signature(r, s, rec);
  }
  addRecoveryBit(bit) {
    return new _Signature(this.r, this.s, bit);
  }
  hasHighS() {
    return highS(this.s);
  }
  toBytes(format = SIG_COMPACT) {
    assertSigFormat(format);
    const { r, s, recovery } = this;
    const res = concatBytes(numTo32b(r), numTo32b(s));
    if (format === SIG_RECOVERED) {
      return concatBytes(u8of(assertRecoveryBit(recovery)), res);
    }
    return res;
  }
};
var bits2int = (bytes) => {
  if (bytes.length > 8192)
    err("input is too large");
  const delta = bytes.length * 8 - 256;
  const num = bytesToNumBE(bytes);
  return delta > 0 ? num >> big(delta) : num;
};
var bits2int_modN = (bytes) => modN(bits2int(abytes(bytes)));
var SIG_COMPACT = "compact";
var SIG_RECOVERED = "recovered";
var SIG_DER = "der";
var _sha = "SHA-256";
var hashes = {
  hmacSha256Async: async (key, message) => {
    const s = subtle();
    const name = "HMAC";
    const k = await s.importKey("raw", key, { name, hash: { name: _sha } }, false, ["sign"]);
    return u8n(await s.sign(name, k, message));
  },
  hmacSha256: void 0,
  sha256Async: async (msg) => u8n(await subtle().digest(_sha, msg)),
  sha256: void 0
};
var prepMsg = (msg, opts, async_) => {
  const message = abytes(msg, void 0, "message");
  if (!opts.prehash)
    return message;
  return async_ ? gha("sha256Async", message) : gh("sha256", message);
};
var NULL = /* @__PURE__ */ u8n(0);
var byte0 = /* @__PURE__ */ u8of(0);
var byte1 = /* @__PURE__ */ u8of(1);
var _maxDrbgIters = 1e3;
var _drbgErr = "drbg: tried max amount of iterations";
var hmacDrbg = (seed, pred) => {
  let v = u8n(L);
  let k = u8n(L);
  let i = 0;
  const reset = () => {
    v.fill(1);
    k.fill(0);
  };
  const h = (...b) => gh("hmacSha256", k, concatBytes(v, ...b));
  const reseed = (seed2 = NULL) => {
    k = h(byte0, seed2);
    v = h();
    if (seed2.length === 0)
      return;
    k = h(byte1, seed2);
    v = h();
  };
  const gen = () => {
    if (i++ >= _maxDrbgIters)
      err(_drbgErr);
    v = h();
    return v;
  };
  reset();
  reseed(seed);
  let res = void 0;
  while (!(res = pred(gen())))
    reseed();
  reset();
  return res;
};
var _sign = (messageHash, secretKey, opts, hmacDrbg2) => {
  let { lowS, extraEntropy } = opts;
  const int2octets = numTo32b;
  const h1i = bits2int_modN(messageHash);
  const h1o = int2octets(h1i);
  const d = secretKeyToScalar(secretKey);
  const seedArgs = [int2octets(d), h1o];
  if (extraEntropy != null && extraEntropy !== false) {
    const e = extraEntropy === true ? randomBytes(L) : extraEntropy;
    seedArgs.push(abytes(e, void 0, "extraEntropy"));
  }
  const seed = concatBytes(...seedArgs);
  const m = h1i;
  const k2sig = (kBytes) => {
    const k = bits2int(kBytes);
    if (!(1n <= k && k < N))
      return;
    const ik = invert(k, N);
    const q = G.multiply(k).toAffine();
    const r = modN(q.x);
    if (r === 0n)
      return;
    const s = modN(ik * modN(m + r * d));
    if (s === 0n)
      return;
    let recovery = (q.x === r ? 0 : 2) | Number(q.y & 1n);
    let normS = s;
    if (lowS && highS(s)) {
      normS = modN(-s);
      recovery ^= 1;
    }
    const sig = new Signature(r, normS, recovery);
    return sig.toBytes(opts.format);
  };
  return hmacDrbg2(seed, k2sig);
};
var setDefaults = (opts) => {
  return {
    lowS: opts.lowS ?? true,
    prehash: opts.prehash ?? true,
    format: opts.format ?? SIG_COMPACT,
    extraEntropy: opts.extraEntropy ?? false
  };
};
var sign = (message, secretKey, opts = {}) => {
  opts = setDefaults(opts);
  assertSigFormat(opts.format);
  const msg = prepMsg(message, opts, false);
  return _sign(msg, secretKey, opts, hmacDrbg);
};
var W = 8;
var scalarBits = 256;
var pwindows = Math.ceil(scalarBits / W) + 1;
var pwindowSize = 2 ** (W - 1);
var precompute = () => {
  const points = [];
  let p = G;
  let b = p;
  for (let w = 0; w < pwindows; w++) {
    b = p;
    points.push(b);
    for (let i = 1; i < pwindowSize; i++) {
      b = b.add(p);
      points.push(b);
    }
    p = b.double();
  }
  return points;
};
var Gpows = void 0;
var ctneg = (cnd, p) => {
  const n = p.negate();
  return cnd ? n : p;
};
var wNAF = (n) => {
  const comp = Gpows || (Gpows = precompute());
  let p = I;
  let f = G;
  const pow_2_w = 2 ** W;
  const maxNum = pow_2_w;
  const mask = big(pow_2_w - 1);
  const shiftBy = big(W);
  for (let w = 0; w < pwindows; w++) {
    let wbits = Number(n & mask);
    n >>= shiftBy;
    if (wbits > pwindowSize) {
      wbits -= maxNum;
      n += 1n;
    }
    const off = w * pwindowSize;
    const offF = off;
    const offP = off + Math.abs(wbits) - 1;
    const isEven2 = w % 2 !== 0;
    const isNeg = wbits < 0;
    if (wbits === 0) {
      f = f.add(ctneg(isEven2, comp[offF]));
    } else {
      p = p.add(ctneg(isNeg, comp[offP]));
    }
  }
  if (n !== 0n)
    err("invalid wnaf");
  return { p, f };
};

// node_modules/@noble/hashes/esm/utils.js
function isBytes2(a) {
  return a instanceof Uint8Array || ArrayBuffer.isView(a) && a.constructor.name === "Uint8Array";
}
function anumber(n) {
  if (!Number.isSafeInteger(n) || n < 0)
    throw new Error("positive integer expected, got " + n);
}
function abytes2(b, ...lengths2) {
  if (!isBytes2(b))
    throw new Error("Uint8Array expected");
  if (lengths2.length > 0 && !lengths2.includes(b.length))
    throw new Error("Uint8Array expected of length " + lengths2 + ", got length=" + b.length);
}
function ahash(h) {
  if (typeof h !== "function" || typeof h.create !== "function")
    throw new Error("Hash should be wrapped by utils.createHasher");
  anumber(h.outputLen);
  anumber(h.blockLen);
}
function aexists(instance, checkFinished = true) {
  if (instance.destroyed)
    throw new Error("Hash instance has been destroyed");
  if (checkFinished && instance.finished)
    throw new Error("Hash#digest() has already been called");
}
function aoutput(out, instance) {
  abytes2(out);
  const min = instance.outputLen;
  if (out.length < min) {
    throw new Error("digestInto() expects output buffer of length at least " + min);
  }
}
function clean(...arrays) {
  for (let i = 0; i < arrays.length; i++) {
    arrays[i].fill(0);
  }
}
function createView(arr) {
  return new DataView(arr.buffer, arr.byteOffset, arr.byteLength);
}
function rotr(word, shift) {
  return word << 32 - shift | word >>> shift;
}
function rotl(word, shift) {
  return word << shift | word >>> 32 - shift >>> 0;
}
function utf8ToBytes(str) {
  if (typeof str !== "string")
    throw new Error("string expected");
  return new Uint8Array(new TextEncoder().encode(str));
}
function toBytes(data) {
  if (typeof data === "string")
    data = utf8ToBytes(data);
  abytes2(data);
  return data;
}
var Hash = class {
};
function createHasher(hashCons) {
  const hashC = (msg) => hashCons().update(toBytes(msg)).digest();
  const tmp = hashCons();
  hashC.outputLen = tmp.outputLen;
  hashC.blockLen = tmp.blockLen;
  hashC.create = () => hashCons();
  return hashC;
}

// node_modules/@noble/hashes/esm/_md.js
function setBigUint64(view, byteOffset, value, isLE) {
  if (typeof view.setBigUint64 === "function")
    return view.setBigUint64(byteOffset, value, isLE);
  const _32n = BigInt(32);
  const _u32_max = BigInt(4294967295);
  const wh = Number(value >> _32n & _u32_max);
  const wl = Number(value & _u32_max);
  const h = isLE ? 4 : 0;
  const l = isLE ? 0 : 4;
  view.setUint32(byteOffset + h, wh, isLE);
  view.setUint32(byteOffset + l, wl, isLE);
}
function Chi(a, b, c) {
  return a & b ^ ~a & c;
}
function Maj(a, b, c) {
  return a & b ^ a & c ^ b & c;
}
var HashMD = class extends Hash {
  constructor(blockLen, outputLen, padOffset, isLE) {
    super();
    this.finished = false;
    this.length = 0;
    this.pos = 0;
    this.destroyed = false;
    this.blockLen = blockLen;
    this.outputLen = outputLen;
    this.padOffset = padOffset;
    this.isLE = isLE;
    this.buffer = new Uint8Array(blockLen);
    this.view = createView(this.buffer);
  }
  update(data) {
    aexists(this);
    data = toBytes(data);
    abytes2(data);
    const { view, buffer, blockLen } = this;
    const len = data.length;
    for (let pos = 0; pos < len; ) {
      const take = Math.min(blockLen - this.pos, len - pos);
      if (take === blockLen) {
        const dataView = createView(data);
        for (; blockLen <= len - pos; pos += blockLen)
          this.process(dataView, pos);
        continue;
      }
      buffer.set(data.subarray(pos, pos + take), this.pos);
      this.pos += take;
      pos += take;
      if (this.pos === blockLen) {
        this.process(view, 0);
        this.pos = 0;
      }
    }
    this.length += data.length;
    this.roundClean();
    return this;
  }
  digestInto(out) {
    aexists(this);
    aoutput(out, this);
    this.finished = true;
    const { buffer, view, blockLen, isLE } = this;
    let { pos } = this;
    buffer[pos++] = 128;
    clean(this.buffer.subarray(pos));
    if (this.padOffset > blockLen - pos) {
      this.process(view, 0);
      pos = 0;
    }
    for (let i = pos; i < blockLen; i++)
      buffer[i] = 0;
    setBigUint64(view, blockLen - 8, BigInt(this.length * 8), isLE);
    this.process(view, 0);
    const oview = createView(out);
    const len = this.outputLen;
    if (len % 4)
      throw new Error("_sha2: outputLen should be aligned to 32bit");
    const outLen = len / 4;
    const state = this.get();
    if (outLen > state.length)
      throw new Error("_sha2: outputLen bigger than state");
    for (let i = 0; i < outLen; i++)
      oview.setUint32(4 * i, state[i], isLE);
  }
  digest() {
    const { buffer, outputLen } = this;
    this.digestInto(buffer);
    const res = buffer.slice(0, outputLen);
    this.destroy();
    return res;
  }
  _cloneInto(to) {
    to || (to = new this.constructor());
    to.set(...this.get());
    const { blockLen, buffer, length, finished, destroyed, pos } = this;
    to.destroyed = destroyed;
    to.finished = finished;
    to.length = length;
    to.pos = pos;
    if (length % blockLen)
      to.buffer.set(buffer);
    return to;
  }
  clone() {
    return this._cloneInto();
  }
};
var SHA256_IV = /* @__PURE__ */ Uint32Array.from([
  1779033703,
  3144134277,
  1013904242,
  2773480762,
  1359893119,
  2600822924,
  528734635,
  1541459225
]);

// node_modules/@noble/hashes/esm/sha2.js
var SHA256_K = /* @__PURE__ */ Uint32Array.from([
  1116352408,
  1899447441,
  3049323471,
  3921009573,
  961987163,
  1508970993,
  2453635748,
  2870763221,
  3624381080,
  310598401,
  607225278,
  1426881987,
  1925078388,
  2162078206,
  2614888103,
  3248222580,
  3835390401,
  4022224774,
  264347078,
  604807628,
  770255983,
  1249150122,
  1555081692,
  1996064986,
  2554220882,
  2821834349,
  2952996808,
  3210313671,
  3336571891,
  3584528711,
  113926993,
  338241895,
  666307205,
  773529912,
  1294757372,
  1396182291,
  1695183700,
  1986661051,
  2177026350,
  2456956037,
  2730485921,
  2820302411,
  3259730800,
  3345764771,
  3516065817,
  3600352804,
  4094571909,
  275423344,
  430227734,
  506948616,
  659060556,
  883997877,
  958139571,
  1322822218,
  1537002063,
  1747873779,
  1955562222,
  2024104815,
  2227730452,
  2361852424,
  2428436474,
  2756734187,
  3204031479,
  3329325298
]);
var SHA256_W = /* @__PURE__ */ new Uint32Array(64);
var SHA256 = class extends HashMD {
  constructor(outputLen = 32) {
    super(64, outputLen, 8, false);
    this.A = SHA256_IV[0] | 0;
    this.B = SHA256_IV[1] | 0;
    this.C = SHA256_IV[2] | 0;
    this.D = SHA256_IV[3] | 0;
    this.E = SHA256_IV[4] | 0;
    this.F = SHA256_IV[5] | 0;
    this.G = SHA256_IV[6] | 0;
    this.H = SHA256_IV[7] | 0;
  }
  get() {
    const { A, B, C: C2, D, E, F, G: G2, H } = this;
    return [A, B, C2, D, E, F, G2, H];
  }
  // prettier-ignore
  set(A, B, C2, D, E, F, G2, H) {
    this.A = A | 0;
    this.B = B | 0;
    this.C = C2 | 0;
    this.D = D | 0;
    this.E = E | 0;
    this.F = F | 0;
    this.G = G2 | 0;
    this.H = H | 0;
  }
  process(view, offset) {
    for (let i = 0; i < 16; i++, offset += 4)
      SHA256_W[i] = view.getUint32(offset, false);
    for (let i = 16; i < 64; i++) {
      const W15 = SHA256_W[i - 15];
      const W2 = SHA256_W[i - 2];
      const s0 = rotr(W15, 7) ^ rotr(W15, 18) ^ W15 >>> 3;
      const s1 = rotr(W2, 17) ^ rotr(W2, 19) ^ W2 >>> 10;
      SHA256_W[i] = s1 + SHA256_W[i - 7] + s0 + SHA256_W[i - 16] | 0;
    }
    let { A, B, C: C2, D, E, F, G: G2, H } = this;
    for (let i = 0; i < 64; i++) {
      const sigma1 = rotr(E, 6) ^ rotr(E, 11) ^ rotr(E, 25);
      const T1 = H + sigma1 + Chi(E, F, G2) + SHA256_K[i] + SHA256_W[i] | 0;
      const sigma0 = rotr(A, 2) ^ rotr(A, 13) ^ rotr(A, 22);
      const T2 = sigma0 + Maj(A, B, C2) | 0;
      H = G2;
      G2 = F;
      F = E;
      E = D + T1 | 0;
      D = C2;
      C2 = B;
      B = A;
      A = T1 + T2 | 0;
    }
    A = A + this.A | 0;
    B = B + this.B | 0;
    C2 = C2 + this.C | 0;
    D = D + this.D | 0;
    E = E + this.E | 0;
    F = F + this.F | 0;
    G2 = G2 + this.G | 0;
    H = H + this.H | 0;
    this.set(A, B, C2, D, E, F, G2, H);
  }
  roundClean() {
    clean(SHA256_W);
  }
  destroy() {
    this.set(0, 0, 0, 0, 0, 0, 0, 0);
    clean(this.buffer);
  }
};
var sha256 = /* @__PURE__ */ createHasher(() => new SHA256());

// node_modules/@noble/hashes/esm/sha256.js
var sha2562 = sha256;

// node_modules/@noble/hashes/esm/legacy.js
var Rho160 = /* @__PURE__ */ Uint8Array.from([
  7,
  4,
  13,
  1,
  10,
  6,
  15,
  3,
  12,
  0,
  9,
  5,
  2,
  14,
  11,
  8
]);
var Id160 = /* @__PURE__ */ (() => Uint8Array.from(new Array(16).fill(0).map((_, i) => i)))();
var Pi160 = /* @__PURE__ */ (() => Id160.map((i) => (9 * i + 5) % 16))();
var idxLR = /* @__PURE__ */ (() => {
  const L3 = [Id160];
  const R = [Pi160];
  const res = [L3, R];
  for (let i = 0; i < 4; i++)
    for (let j of res)
      j.push(j[i].map((k) => Rho160[k]));
  return res;
})();
var idxL = /* @__PURE__ */ (() => idxLR[0])();
var idxR = /* @__PURE__ */ (() => idxLR[1])();
var shifts160 = /* @__PURE__ */ [
  [11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8],
  [12, 13, 11, 15, 6, 9, 9, 7, 12, 15, 11, 13, 7, 8, 7, 7],
  [13, 15, 14, 11, 7, 7, 6, 8, 13, 14, 13, 12, 5, 5, 6, 9],
  [14, 11, 12, 14, 8, 6, 5, 5, 15, 12, 15, 14, 9, 9, 8, 6],
  [15, 12, 13, 13, 9, 5, 8, 6, 14, 11, 12, 11, 8, 6, 5, 5]
].map((i) => Uint8Array.from(i));
var shiftsL160 = /* @__PURE__ */ idxL.map((idx, i) => idx.map((j) => shifts160[i][j]));
var shiftsR160 = /* @__PURE__ */ idxR.map((idx, i) => idx.map((j) => shifts160[i][j]));
var Kl160 = /* @__PURE__ */ Uint32Array.from([
  0,
  1518500249,
  1859775393,
  2400959708,
  2840853838
]);
var Kr160 = /* @__PURE__ */ Uint32Array.from([
  1352829926,
  1548603684,
  1836072691,
  2053994217,
  0
]);
function ripemd_f(group, x, y, z) {
  if (group === 0)
    return x ^ y ^ z;
  if (group === 1)
    return x & y | ~x & z;
  if (group === 2)
    return (x | ~y) ^ z;
  if (group === 3)
    return x & z | y & ~z;
  return x ^ (y | ~z);
}
var BUF_160 = /* @__PURE__ */ new Uint32Array(16);
var RIPEMD160 = class extends HashMD {
  constructor() {
    super(64, 20, 8, true);
    this.h0 = 1732584193 | 0;
    this.h1 = 4023233417 | 0;
    this.h2 = 2562383102 | 0;
    this.h3 = 271733878 | 0;
    this.h4 = 3285377520 | 0;
  }
  get() {
    const { h0, h1, h2, h3, h4 } = this;
    return [h0, h1, h2, h3, h4];
  }
  set(h0, h1, h2, h3, h4) {
    this.h0 = h0 | 0;
    this.h1 = h1 | 0;
    this.h2 = h2 | 0;
    this.h3 = h3 | 0;
    this.h4 = h4 | 0;
  }
  process(view, offset) {
    for (let i = 0; i < 16; i++, offset += 4)
      BUF_160[i] = view.getUint32(offset, true);
    let al = this.h0 | 0, ar = al, bl = this.h1 | 0, br = bl, cl = this.h2 | 0, cr = cl, dl = this.h3 | 0, dr = dl, el = this.h4 | 0, er = el;
    for (let group = 0; group < 5; group++) {
      const rGroup = 4 - group;
      const hbl = Kl160[group], hbr = Kr160[group];
      const rl = idxL[group], rr = idxR[group];
      const sl = shiftsL160[group], sr = shiftsR160[group];
      for (let i = 0; i < 16; i++) {
        const tl = rotl(al + ripemd_f(group, bl, cl, dl) + BUF_160[rl[i]] + hbl, sl[i]) + el | 0;
        al = el, el = dl, dl = rotl(cl, 10) | 0, cl = bl, bl = tl;
      }
      for (let i = 0; i < 16; i++) {
        const tr = rotl(ar + ripemd_f(rGroup, br, cr, dr) + BUF_160[rr[i]] + hbr, sr[i]) + er | 0;
        ar = er, er = dr, dr = rotl(cr, 10) | 0, cr = br, br = tr;
      }
    }
    this.set(this.h1 + cl + dr | 0, this.h2 + dl + er | 0, this.h3 + el + ar | 0, this.h4 + al + br | 0, this.h0 + bl + cr | 0);
  }
  roundClean() {
    clean(BUF_160);
  }
  destroy() {
    this.destroyed = true;
    clean(this.buffer);
    this.set(0, 0, 0, 0, 0);
  }
};
var ripemd160 = /* @__PURE__ */ createHasher(() => new RIPEMD160());

// node_modules/@noble/hashes/esm/ripemd160.js
var ripemd1602 = ripemd160;

// node_modules/@noble/hashes/esm/hmac.js
var HMAC = class extends Hash {
  constructor(hash, _key) {
    super();
    this.finished = false;
    this.destroyed = false;
    ahash(hash);
    const key = toBytes(_key);
    this.iHash = hash.create();
    if (typeof this.iHash.update !== "function")
      throw new Error("Expected instance of class which extends utils.Hash");
    this.blockLen = this.iHash.blockLen;
    this.outputLen = this.iHash.outputLen;
    const blockLen = this.blockLen;
    const pad = new Uint8Array(blockLen);
    pad.set(key.length > blockLen ? hash.create().update(key).digest() : key);
    for (let i = 0; i < pad.length; i++)
      pad[i] ^= 54;
    this.iHash.update(pad);
    this.oHash = hash.create();
    for (let i = 0; i < pad.length; i++)
      pad[i] ^= 54 ^ 92;
    this.oHash.update(pad);
    clean(pad);
  }
  update(buf) {
    aexists(this);
    this.iHash.update(buf);
    return this;
  }
  digestInto(out) {
    aexists(this);
    abytes2(out, this.outputLen);
    this.finished = true;
    this.iHash.digestInto(out);
    this.oHash.update(out);
    this.oHash.digestInto(out);
    this.destroy();
  }
  digest() {
    const out = new Uint8Array(this.oHash.outputLen);
    this.digestInto(out);
    return out;
  }
  _cloneInto(to) {
    to || (to = Object.create(Object.getPrototypeOf(this), {}));
    const { oHash, iHash, finished, destroyed, blockLen, outputLen } = this;
    to = to;
    to.finished = finished;
    to.destroyed = destroyed;
    to.blockLen = blockLen;
    to.outputLen = outputLen;
    to.oHash = oHash._cloneInto(to.oHash);
    to.iHash = iHash._cloneInto(to.iHash);
    return to;
  }
  clone() {
    return this._cloneInto();
  }
  destroy() {
    this.destroyed = true;
    this.oHash.destroy();
    this.iHash.destroy();
  }
};
var hmac = (hash, key, message) => new HMAC(hash, key).update(message).digest();
hmac.create = (hash, key) => new HMAC(hash, key);

// tools/stone-tx-entry.mjs
hashes.sha256 = (msg) => sha2562(msg);
hashes.hmacSha256 = (key, msg) => hmac(sha2562, key, msg);
var STONE_PUBKEY_ADDRESS = 63;
var STONE_SECRET_KEY = 191;
var COIN = 100000000n;
var DUST_SATS = 546n;
var DEFAULT_FEE_SATS = 10000n;
var B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function bytesToHex2(b) {
  let s = "";
  for (const x of b) s += x.toString(16).padStart(2, "0");
  return s;
}
function hexToBytes2(hex) {
  const h = String(hex || "").replace(/\s/g, "");
  if (h.length % 2) throw new Error("invalid hex");
  const out = new Uint8Array(h.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(h.slice(i * 2, i * 2 + 2), 16);
  return out;
}
function concatBytes2(...arrs) {
  let n = 0;
  for (const a of arrs) n += a.length;
  const out = new Uint8Array(n);
  let o = 0;
  for (const a of arrs) {
    out.set(a, o);
    o += a.length;
  }
  return out;
}
function hash256(data) {
  return sha2562(sha2562(data));
}
function base58Encode(bytes) {
  let zeros = 0;
  while (zeros < bytes.length && bytes[zeros] === 0) zeros += 1;
  const digits = [0];
  for (let i = zeros; i < bytes.length; i++) {
    let carry = bytes[i];
    for (let j = 0; j < digits.length; j++) {
      carry += digits[j] << 8;
      digits[j] = carry % 58;
      carry = carry / 58 | 0;
    }
    while (carry > 0) {
      digits.push(carry % 58);
      carry = carry / 58 | 0;
    }
  }
  let str = "1".repeat(zeros);
  for (let i = digits.length - 1; i >= 0; i--) str += B58[digits[i]];
  return str;
}
function base58Decode(str) {
  const bytes = [0];
  for (let i = 0; i < str.length; i++) {
    const v = B58.indexOf(str[i]);
    if (v < 0) throw new Error("Invalid base58 character");
    let carry = v;
    for (let j = 0; j < bytes.length; j++) {
      carry += bytes[j] * 58;
      bytes[j] = carry & 255;
      carry >>= 8;
    }
    while (carry > 0) {
      bytes.push(carry & 255);
      carry >>= 8;
    }
  }
  let zeros = 0;
  while (zeros < str.length && str[zeros] === "1") zeros += 1;
  const out = new Uint8Array(zeros + bytes.length);
  for (let i = 0; i < bytes.length; i++) out[out.length - 1 - i] = bytes[i];
  return out;
}
function base58CheckEncode(payload) {
  const checksum = hash256(payload).slice(0, 4);
  return base58Encode(concatBytes2(payload, checksum));
}
function base58CheckDecode(str) {
  const full = base58Decode(str);
  if (full.length < 5) throw new Error("Invalid base58check");
  const payload = full.slice(0, full.length - 4);
  const checksum = full.slice(full.length - 4);
  const expect = hash256(payload).slice(0, 4);
  for (let i = 0; i < 4; i++) {
    if (checksum[i] !== expect[i]) throw new Error("Invalid checksum");
  }
  return payload;
}
function isValidStoneAddress(address) {
  try {
    const s = String(address || "").trim();
    if (!s || s[0] !== "S") return false;
    const payload = base58CheckDecode(s);
    return payload.length === 21 && payload[0] === STONE_PUBKEY_ADDRESS;
  } catch (_) {
    return false;
  }
}
function decodeWif(wif) {
  const payload = base58CheckDecode(String(wif || "").trim());
  if (payload[0] !== STONE_SECRET_KEY && payload[0] !== 128) {
    throw new Error(`Not a Bloodstone WIF key (version ${payload[0]})`);
  }
  const compressed = payload.length === 34 && payload[33] === 1;
  if (payload.length !== 33 && payload.length !== 34) {
    throw new Error("Invalid WIF length");
  }
  const priv = payload.slice(1, 33);
  const pub = getPublicKey(priv, compressed);
  const h160 = ripemd1602(sha2562(pub));
  const addrPayload = new Uint8Array(1 + h160.length);
  addrPayload[0] = STONE_PUBKEY_ADDRESS;
  addrPayload.set(h160, 1);
  const address = base58CheckEncode(addrPayload);
  return {
    privateKey: priv,
    publicKey: pub,
    compressed,
    address,
    publicKeyHex: bytesToHex2(pub)
  };
}
function addressToHash160(address) {
  const payload = base58CheckDecode(String(address || "").trim());
  if (payload.length !== 21 || payload[0] !== STONE_PUBKEY_ADDRESS) {
    throw new Error("Invalid STONE address");
  }
  return payload.slice(1);
}
function p2pkhScript(hash160) {
  return concatBytes2(
    new Uint8Array([118, 169, 20]),
    hash160,
    new Uint8Array([136, 172])
  );
}
function writeVarInt(n) {
  if (n < 253) return new Uint8Array([n]);
  if (n <= 65535) {
    const b = new Uint8Array(3);
    b[0] = 253;
    b[1] = n & 255;
    b[2] = n >> 8 & 255;
    return b;
  }
  if (n <= 4294967295) {
    const b = new Uint8Array(5);
    b[0] = 254;
    const v = n >>> 0;
    b[1] = v & 255;
    b[2] = v >>> 8 & 255;
    b[3] = v >>> 16 & 255;
    b[4] = v >>> 24 & 255;
    return b;
  }
  throw new Error("varint too large");
}
function writeUint32LE(n) {
  const b = new Uint8Array(4);
  const v = n >>> 0;
  b[0] = v & 255;
  b[1] = v >>> 8 & 255;
  b[2] = v >>> 16 & 255;
  b[3] = v >>> 24 & 255;
  return b;
}
function writeUint64LE(n) {
  const v = typeof n === "bigint" ? n : BigInt(n);
  const b = new Uint8Array(8);
  let x = v;
  for (let i = 0; i < 8; i++) {
    b[i] = Number(x & 0xffn);
    x >>= 8n;
  }
  return b;
}
function writeSlice(data) {
  return concatBytes2(writeVarInt(data.length), data);
}
function reverseHexTxid(txid) {
  const raw = hexToBytes2(txid);
  if (raw.length !== 32) throw new Error("txid must be 32 bytes");
  return raw.reverse();
}
function encodeTx(version, inputs, outputs, locktime) {
  const parts = [writeUint32LE(version), writeVarInt(inputs.length)];
  for (const inp of inputs) {
    parts.push(inp.txidLE);
    parts.push(writeUint32LE(inp.vout));
    parts.push(writeSlice(inp.script));
    parts.push(writeUint32LE(inp.sequence));
  }
  parts.push(writeVarInt(outputs.length));
  for (const out of outputs) {
    parts.push(writeUint64LE(out.value));
    parts.push(writeSlice(out.script));
  }
  parts.push(writeUint32LE(locktime));
  return concatBytes2(...parts);
}
function compactToDer(compact) {
  if (!(compact instanceof Uint8Array) || compact.length !== 64) {
    throw new Error("compact signature must be 64 bytes");
  }
  let r = compact.slice(0, 32);
  let s = compact.slice(32);
  while (r.length > 1 && r[0] === 0 && (r[1] & 128) === 0) r = r.slice(1);
  while (s.length > 1 && s[0] === 0 && (s[1] & 128) === 0) s = s.slice(1);
  if (r[0] & 128) r = concatBytes2(new Uint8Array([0]), r);
  if (s[0] & 128) s = concatBytes2(new Uint8Array([0]), s);
  const body = concatBytes2(
    new Uint8Array([2, r.length]),
    r,
    new Uint8Array([2, s.length]),
    s
  );
  return concatBytes2(new Uint8Array([48, body.length]), body);
}
function selectCoins(utxos, targetSats) {
  const sorted = [...utxos].sort((a, b) => Number(BigInt(b.satoshis) - BigInt(a.satoshis)));
  const chosen = [];
  let total = 0n;
  for (const u of sorted) {
    const sat = BigInt(u.satoshis || 0);
    if (sat <= 0n) continue;
    chosen.push(u);
    total += sat;
    if (total >= targetSats) break;
  }
  if (total < targetSats) {
    throw new Error(
      `Insufficient funds: need ${(Number(targetSats) / 1e8).toFixed(8)} STONE, have ${(Number(total) / 1e8).toFixed(8)}`
    );
  }
  return { chosen, total };
}
async function buildSignedSendTx(opts) {
  const wif = opts?.wif;
  const toAddress = String(opts?.toAddress || "").trim();
  const amountStone = Number(opts?.amountStone);
  const feeStone = opts?.feeStone != null ? Number(opts.feeStone) : Number(DEFAULT_FEE_SATS) / 1e8;
  const utxos = Array.isArray(opts?.utxos) ? opts.utxos : [];
  if (!wif) throw new Error("WIF required");
  if (!isValidStoneAddress(toAddress)) throw new Error("Invalid destination address");
  if (!Number.isFinite(amountStone) || amountStone <= 0) throw new Error("Amount must be positive");
  if (!Number.isFinite(feeStone) || feeStone < 0) throw new Error("Invalid fee");
  if (!utxos.length) throw new Error("No UTXOs available \u2014 fund this address first");
  const key = decodeWif(wif);
  const changeAddress = String(opts?.changeAddress || key.address).trim();
  if (!isValidStoneAddress(changeAddress)) throw new Error("Invalid change address");
  const amountSats = BigInt(Math.round(amountStone * 1e8));
  const feeSats = BigInt(Math.round(feeStone * 1e8));
  if (amountSats < DUST_SATS) throw new Error("Amount is below dust limit");
  const need = amountSats + feeSats;
  const { chosen, total } = selectCoins(utxos, need);
  const changeSats = total - need;
  const destScript = p2pkhScript(addressToHash160(toAddress));
  const outputs = [{ value: amountSats, script: destScript }];
  if (changeSats >= DUST_SATS) {
    outputs.push({
      value: changeSats,
      script: p2pkhScript(addressToHash160(changeAddress))
    });
  } else if (changeSats > 0n) {
  }
  const unsignedInputs = chosen.map((u) => {
    let script;
    if (u.scriptPubKey && String(u.scriptPubKey).length >= 50) {
      script = hexToBytes2(u.scriptPubKey);
    } else {
      script = p2pkhScript(addressToHash160(key.address));
    }
    return {
      txidLE: reverseHexTxid(u.txid),
      vout: Number(u.vout) || 0,
      script,
      sequence: 4294967295,
      prevScript: script
    };
  });
  const SIGHASH_ALL = 1;
  const signedInputs = [];
  for (let i = 0; i < unsignedInputs.length; i++) {
    const inputsForSighash = unsignedInputs.map((inp, j) => ({
      txidLE: inp.txidLE,
      vout: inp.vout,
      script: j === i ? inp.prevScript : new Uint8Array(0),
      sequence: inp.sequence
    }));
    const preimage = concatBytes2(
      encodeTx(1, inputsForSighash, outputs, 0),
      writeUint32LE(SIGHASH_ALL)
    );
    const digest = hash256(preimage);
    const compact = sign(digest, key.privateKey, { prehash: false });
    const der = compactToDer(
      compact instanceof Uint8Array ? compact : compact.toBytes("compact")
    );
    const sigWithType = concatBytes2(der, new Uint8Array([SIGHASH_ALL]));
    const scriptSig = concatBytes2(writeSlice(sigWithType), writeSlice(key.publicKey));
    signedInputs.push({
      txidLE: unsignedInputs[i].txidLE,
      vout: unsignedInputs[i].vout,
      script: scriptSig,
      sequence: unsignedInputs[i].sequence
    });
  }
  const raw = encodeTx(1, signedInputs, outputs, 0);
  const txid = bytesToHex2(hash256(raw).reverse());
  key.privateKey.fill(0);
  return {
    hex: bytesToHex2(raw),
    txid,
    feeStone: feeStone + (changeSats > 0n && changeSats < DUST_SATS ? Number(changeSats) / 1e8 : 0),
    amountStone,
    fromAddress: key.address,
    toAddress,
    inputs: chosen.length,
    changeStone: changeSats >= DUST_SATS ? Number(changeSats) / 1e8 : 0
  };
}
export {
  COIN,
  DEFAULT_FEE_SATS,
  DUST_SATS,
  STONE_PUBKEY_ADDRESS,
  STONE_SECRET_KEY,
  addressToHash160,
  buildSignedSendTx,
  bytesToHex2 as bytesToHex,
  decodeWif,
  hash256,
  hexToBytes2 as hexToBytes,
  isValidStoneAddress,
  p2pkhScript
};
/*! Bundled license information:

@noble/secp256k1/index.js:
  (*! noble-secp256k1 - MIT License (c) 2019 Paul Miller (paulmillr.com) *)

@noble/hashes/esm/utils.js:
  (*! noble-hashes - MIT License (c) 2022 Paul Miller (paulmillr.com) *)
*/

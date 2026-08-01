# WP0 skeptic run — easy instructions (anyone, any laptop)

**Goal:** Prove the Fork Lab burn address is **keyless** without trusting our VPS.  
**Time:** ~2 minutes. **Needs:** Python 3 only (no install of Bloodstone, no wallet, no login).

---

## What “pass” looks like

You run one command and see:

```text
SELFTEST OK
```

and exit code **0**. Then the published addresses re-verify as OK.

---

## Steps (copy-paste)

### 1. Download the standalone verifier

```bash
mkdir -p /tmp/wp0-skeptic && cd /tmp/wp0-skeptic
curl -fsSL -O https://bloodstone.rocks/downloads/fork_lab_burn.py
curl -fsSL -O https://bloodstone.rocks/downloads/fork-lab-burn-vectors.json
```

Optional: also open the short doc  
https://bloodstone.rocks/downloads/Bloodstone-Fork-Lab-Burn-WP0.md

### 2. Run the self-test (this is the skeptic run)

```bash
python3 fork_lab_burn.py selftest
echo "exit code: $?"
```

**Pass:** prints `SELFTEST OK` and `exit code: 0`.  
**Fail:** prints `SELFTEST FAIL` — stop and report to ops (do not use the burn address).

### 3. Double-check the two official addresses

```bash
# Canonical global burn (tag 0x01)
python3 fork_lab_burn.py verify ShGX17JqtmvKaqTUdKufpS3hqmVsyp3mA3 --canonical

# Sample draft vector (tag 0x02)
python3 fork_lab_burn.py verify SkQJDpZGhjJptscpCnGcMXnx1YP7JqPS7H \
  --draft-id wp0-acceptance-draft-001
```

Both should print JSON with `"ok": true`.

### 4. (Optional) Confirm vectors file matches

```bash
python3 fork_lab_burn.py vectors | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['canonical']['address'])"
# Expect: ShGX17JqtmvKaqTUdKufpS3hqmVsyp3mA3
```

---

## What you just proved

- The `S…` burn address is **Base58Check version 63** (STONE).  
- The 20-byte payload equals **Hash160(material)** under the **locked** layout — it is a hash commitment, **not** `Hash160(pubkey)`.  
- So there is **no private key** to find for that address (keyless by construction).  
- Old “smoke” addresses (`ScTQ4vuj…`, `SaVP5mNi…`) must **fail** verify — they used a naive layout.

You did **not** need our server, wallet RPC, or secrets.

---

## Send this back when done (Discord paste)

```text
WP0 skeptic run
Machine: <laptop OS>
Command: python3 fork_lab_burn.py selftest
Result: SELFTEST OK / FAIL
Exit code: 0 / not-0
Canonical verify: ok true/false
Draft verify: ok true/false
```

---

## Windows (PowerShell)

```powershell
mkdir $env:TEMP\wp0-skeptic -Force; cd $env:TEMP\wp0-skeptic
Invoke-WebRequest -Uri https://bloodstone.rocks/downloads/fork_lab_burn.py -OutFile fork_lab_burn.py
python fork_lab_burn.py selftest
```

(Use a normal Python 3 install from python.org if `python` is missing.)

---

*WP0 · scheme `bloodstone/fork-lab/burn/v1-layout` · RFQ v1.5 §3a*

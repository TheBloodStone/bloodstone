# Security Audit Remediation — 0.36.1-beta

**Target:** bloodstone-pi-fleet-convergence / `chain_mesh`  
**Base:** 0.36.0-beta audit follow-up (L-01, L-02, C-03, Open Item 7)  
**Date:** 2026-07-10  

---

## Section A: Answers to Open Items

1. **Authentication strategy**  
   Convergence is a **trusted LAN / fleet mesh** with soft trust, not a public multi-tenant API. Production must set `CHAIN_MESH_API_TOKEN` (or publish token) with `CHAIN_MESH_REQUIRE_WRITE_AUTH=1`. Optional stronger proof: set `CHAIN_MESH_REQUIRE_OWNERSHIP_PROOF=1` and `CHAIN_MESH_OWNERSHIP_MODE=token|message` (HMAC message proof experimental).

2. **Environment variables**  
   - `CHAIN_MESH_API_TOKEN` / `CHAIN_MESH_PUBLISH_TOKEN` — required for writes when auth enforced.  
   - `DTN_TLS_VERIFY=1` (default).  
   - Optional: `CHAIN_MESH_REQUIRE_OWNERSHIP_PROOF`, `CHAIN_MESH_OWNERSHIP_MODE`, `CHAIN_MESH_OWNERSHIP_HMAC_SECRET`.

3. **Blurt integration**  
   Posting authority is trusted from Blurt RPC / registry rows; no local posting-key verification. Acceptable on trusted coordinators. Higher assurance: verify Blurt transaction signatures before binding; interim control remains write token + optional ownership HMAC.

4. **RPC credentials**  
   `bloodstone.conf` mode `600` is standard for Bitcoin-family daemons on a locked host. Do not log RPC URLs (masking applied). Prefer localhost-only RPC.

5. **Peer registration**  
   Restricted to private IPs + token (LAN open register off by default). Open internet registration remains disabled.

6. **Database storage**  
   `blurt_account` / `stone_address` are public identifiers; no app-level encryption required. Protect DB file permissions and backups.

7. **`blurt_author` → `blurt_account`**  
   Confirmed: the field is a **Blurt account name** (e.g. `megadrive`), never a private key.  
   **Plan executed:**
   - Python identifiers / SQL columns / JSON preferred key: `blurt_account`.  
   - HTTP/payload still accepts deprecated `blurt_author` and `author`.  
   - SQLite migration `migrate_blurt_author_columns()` renames columns on `init_db()` when old name present.  
   - Docs/comments updated; version **0.36.1-beta**.

---

## Section B: Security Patches

### B.1 L-01 — Verbose errors → `public_error`

| Area | Change |
|------|--------|
| `chain_mesh/security.py` | Stronger `public_error` (masks secrets, TypeError/KeyError, single-line cap) |
| `bloodstone-miner-web/app.py` | `_safe_err` / `_api_error`; bulk replace of `jsonify(... str(exc) ...)` |
| `bloodstone-portal/app.py` | Same pattern |
| Multiple `chain_mesh/*` modules | Client-facing `"error": str(exc)` → `public_error(exc)` |

### B.2 L-02 — Per-target forward idempotency

| Area | Change |
|------|--------|
| `chain_mesh/dtn_sync.py` | Table `dtn_forward_deliveries (bundle_id, target_url)` |
| `flush_forward_queue` | Skip targets already delivered; claim row (`delivering`); record delivery before marking queue `delivered`; `skipped_idempotent` in result |

### B.3 C-03 — Ownership proof (optional)

| Area | Change |
|------|--------|
| `security.verify_stone_ownership_proof` | Optional gate when `CHAIN_MESH_REQUIRE_OWNERSHIP_PROOF=1` |
| Tenant bind / agent register | Call ownership proof after write token |

Default remains token-based LAN trust (no breaking change).

### B.4 Open Item 7 — rename

Bulk rename `blurt_author` → `blurt_account` in `chain_mesh` sources + dual-key payload acceptance + DB migration helper.

---

## Section C: Version Bump

| File | Old | New |
|------|-----|-----|
| `chain_mesh/VERSION` | 0.36.0-beta | **0.36.1-beta** |
| `ops/bloodstone-pi-fleet/VERSION` | 0.36.0-beta | **0.36.1-beta** |
| `chain_mesh/__init__.py` fallback | 0.36.0-beta | **0.36.1-beta** |
| `ops/bloodstone-pi-fleet/version.py` fallback | 0.36.0-beta | **0.36.1-beta** |

---

## Section D: Integration Notes

- **No new pip dependencies.**  
- **Non-breaking defaults:** ownership proof off; dual JSON keys accepted.  
- **Soft deprecation:** clients should send `blurt_account`; `blurt_author` still works.  
- **Restart:** `systemctl restart bloodstone-miner-web bloodstone-portal`  

### Manual checks

```bash
python3 -c "import chain_mesh; assert chain_mesh.__version__=='0.36.1-beta'"
# dual key
python3 -c "from chain_mesh.security import normalize_blurt_account as n; assert n(payload={'blurt_author':'@X'})=='x'"
# flush returns skipped_idempotent key
python3 -c "from chain_mesh.dtn_sync import flush_forward_queue; print(flush_forward_queue(force=True, limit=1).keys())"
```

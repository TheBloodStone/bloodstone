# Security Audit Remediation — 2026-07-10

**Target:** bloodstone-pi-fleet-convergence / `chain_mesh` + portal DTN surfaces  
**Source audit:** DeepSeek-V3 style report (C-01…L-02)  
**Status:** Code patches applied on this VPS (see Section A).  

---

## Section A: Security Patches

### New module: `chain_mesh/security.py`

Central helpers:

| Helper | Purpose |
|--------|---------|
| `validate_url_ssrf(url, mode=…)` | SSRF guard (`lan_only` / `block_internal` / `public_egress`) |
| `validate_ip_literal(dst)` | Ping/ICMP IP-only validation |
| `require_write_token` / `require_publish_token` | Write auth + `hmac.compare_digest` |
| `validate_register_source` | Restrict `source` enum |
| `rate_limit(key, max_calls, window_sec)` | In-process rate limiting |
| `mask_secrets_in_text` | Redact `user:pass@` in log strings |
| `public_error` | Client-safe error messages |

Env knobs (see Section C).

---

### A.1 C-01 — SSRF peer registration

**Files:** `chain_mesh/api.py` (`convergence_dtn_peer_register_payload`), `chain_mesh/dtn_sync.py` (`register_dtn_peer`)

**Change summary:**

1. Require write token (or LAN open register for `local`/`mdns`/`lan`/`heartbeat` sources only).  
2. `validate_url_ssrf(..., mode="lan_only")` — host must resolve to **private RFC1918/ULA** (loopback allowed via `CHAIN_MESH_ALLOW_LOOPBACK_REGISTER=1`).  
3. Restrict `source` to trusted set.  
4. Rate limit: 20/min.

```python
# FILE: chain_mesh/api.py — convergence_dtn_peer_register_payload
def convergence_dtn_peer_register_payload(payload):
    rate_limit("dtn-peer-register", max_calls=20, window_sec=60)
    source = validate_register_source(str(payload.get("source") or "manual"))
    require_write_token(payload, allow_lan_open=(source in ("local", "mdns", "lan", "heartbeat")))
    base_url = validate_url_ssrf(str(payload.get("base_url") or ""), mode="lan_only")
    return dtn.register_dtn_peer(base_url=base_url, ..., source=source)
```

`register_dtn_peer` also re-validates `base_url` (defense in depth).

---

### A.2 C-02 — SSRF AI provider registration

**Files:** `chain_mesh/api.py` (`convergence_ai_register_payload`), `chain_mesh/ai_routing.py` (`register_local_provider`)

**Change summary:**

1. Write token required (LAN open only for `local`/`mdns`/`lan`/`coordinator`).  
2. Each of `inference_url` / `health_url` / `callback_url` run through `validate_url_ssrf(..., mode="lan_only")`.  
3. Rate limit: 20/min.  
4. Local provider auto-register validates default LAN endpoints.

---

### A.3 C-03 — Write auth on high-risk endpoints

**Files:** `chain_mesh/api.py`

| Endpoint helper | Auth |
|-----------------|------|
| `convergence_agent_register_payload` | `require_write_token` + rate limit |
| `convergence_compute_job_submit_payload` | `require_write_token` + rate limit |
| `convergence_tenant_bind_payload` | `require_write_token` + rate limit |
| `convergence_tenant_broadcast_payload` | `require_write_token` + rate limit |
| Asset metadata / partner publish | `require_publish_token` (constant-time) |

**Not solved fully:** cryptographic proof that caller owns `stone_address` / Blurt posting authority (see Open Item 1 & 3). Token gate is the practical interim control.

---

### A.4 C-04 — XSS in convergence embed

**Files:**

- `chain_mesh/blog_manifest.py` — `condenser_embed_html` now `html.escape`s URL and mime.  
- `chain_mesh/condenser_embed.py` — ignores untrusted `embed_html` from items; provenance badge uses escaped text only (no raw `badge_html`).  

**Template note:** `templates/convergence_embed.html` still uses `{{ page_html|safe }}` because the HTML is now built entirely server-side with escaping. Do **not** pass external HTML into `standalone_page_html`.

---

### A.5 H-01 — TLS verification default

**File:** `chain_mesh/dtn_tls.py`

```diff
-DTN_TLS_VERIFY = os.environ.get("DTN_TLS_VERIFY", "0").strip() in ("1", "true", "yes")
+DTN_TLS_VERIFY = os.environ.get("DTN_TLS_VERIFY", "1").strip() in ("1", "true", "yes")
-DTN_TLS_FALLBACK_HTTP = os.environ.get("DTN_TLS_FALLBACK_HTTP", "1")...
+DTN_TLS_FALLBACK_HTTP = os.environ.get("DTN_TLS_FALLBACK_HTTP", "0")...
```

Lab/self-signed without CA: set `DTN_TLS_VERIFY=0` and/or `DTN_TLS_CA_FILE=/path/to/ca.pem`.

---

### A.6 H-02 — Internet gateway SSRF

**File:** `chain_mesh/ip_gateway.py` — `_web_fetch`

- Validates `dst_ip` as IP literal.  
- Port allowlist (`GATEWAY_HTTP_PORTS` / `GATEWAY_HTTPS_PORTS` ∪ 80/443/8080/8443).  
- `validate_url_ssrf(..., mode="block_internal")` blocks loopback, link-local, **metadata 169.254.169.254**, and private IPs.  
- Sanitizes `Host` header (no credentials/path).

---

### A.7 H-03 — TLS proxy bind

**File:** `bloodstone-dtn-tls-proxy.py`

```diff
+BIND_HOST = os.environ.get("DTN_TLS_BIND", "127.0.0.1").strip() or "127.0.0.1"
-with socketserver.ThreadingTCPServer(("", PORT), _ProxyHandler) as httpd:
+with socketserver.ThreadingTCPServer((BIND_HOST, PORT), _ProxyHandler) as httpd:
```

Trusted LAN exposure: `DTN_TLS_BIND=0.0.0.0` + firewall.

---

### A.8 H-04 — Publish token constant-time + required

**Files:** `chain_mesh/partner.py`, `chain_mesh/api.py` (asset metadata), `chain_mesh/security.py`

- Replaces `token != PUBLISH_TOKEN` with `hmac.compare_digest`.  
- Empty `PUBLISH_TOKEN` + `CHAIN_MESH_REQUIRE_WRITE_AUTH=1` → **reject** publish (no open publish).

---

### A.9 M-01 — Ping input validation

**File:** `chain_mesh/ip_gateway.py` — `_icmp_ping`

Uses `validate_ip_literal(dst)` before `subprocess.run(["ping", ...])` (list form already; IP-only blocks injection).

---

### A.10 M-02 — RPC credentials in exceptions

**File:** `bloodstone-portal/app.py` — `rpc()`

Masks `://user:password@` in exception messages via `_mask_rpc_secrets`.

---

### A.11 M-03 — Rate limiting

In-process `rate_limit()` on:

- DTN peer register, AI register  
- Agent register, compute job submit  
- Tenant bind/broadcast  
- DTN export (10/min per node_id)

**Note:** Not Flask-Limiter; process-local. For multi-worker gunicorn, prefer nginx `limit_req` (already used on portal) or Redis-backed limiter later.

```bash
# Optional if you adopt Flask-Limiter later:
# pip install 'Flask-Limiter>=3,<4'
```

---

### A.12 L-01 / L-02

- **L-01:** Prefer `public_error(exc)` at HTTP boundary (helpers ready); ValueError/PermissionError messages capped. Full traces remain server logs only when using gunicorn defaults.  
- **L-02:** `flush_forward_queue` already marks `delivered` only after a successful push to **one** target, then breaks (at-least-once to one peer). Full per-target idempotency remains a follow-up.

---

## Section B: Open Items Clarifications

1. **Authentication strategy**  
   Convergence was built as a **LAN / fleet mesh with soft trust**, not a public multi-tenant API. Network isolation (bind, firewall, reverse proxy) was the original control. **Action:** set `CHAIN_MESH_API_TOKEN` (or `CHAIN_MESH_PUBLISH_TOKEN`) on every production coordinator and pass `api_token` / `X-Api-Token` on writes; keep public internet away from portal bind.

2. **Environment variables (mandatory in production)**  
   - **`CHAIN_MESH_API_TOKEN` or `CHAIN_MESH_PUBLISH_TOKEN`** — mandatory (writes fail if missing when `CHAIN_MESH_REQUIRE_WRITE_AUTH=1`).  
   - **`DTN_TLS_VERIFY=1`** — mandatory (now default); set `DTN_TLS_CA_FILE` for self-signed LAN CAs.  
   - **`AI_GOSSIP_SIGNING_KEY`** — strongly recommended if gossip signing is enabled; without it unsigned gossip remains beta-permissive.  
   Startup check: refuse to start write-capable services if API/publish token empty and `REQUIRE_WRITE_AUTH=1`.

3. **Blurt integration**  
   Local code trusts Blurt `custom_json` / registry rows and does **not** re-verify posting keys. Confirmation is effectively deferred to Blurt RPC / prior sync. **Action:** require Blurt RPC `get_transaction` + posting authority check before tenant bind / quota grants; short-term gate binds behind `require_write_token`.

4. **RPC credentials**  
   Plaintext `bloodstone.conf` is normal for Bitcoin-family daemons on a **locked-down host**. **Action:** `chmod 600` conf, never log RPC URLs (masked), prefer env-only secrets on new installs, never expose RPC outside localhost.

5. **Peer registration**  
   Intended for **same-LAN fleet** (mDNS/heartbeat), not the open internet. **Action:** now enforced as private-IP-only URLs + token (or `CHAIN_MESH_LAN_OPEN_REGISTER=1` only on air-gapped LAN).

6. **Database storage of `blurt_author` / `stone_address`**  
   Treated as **public or semi-public identifiers** (like blockchain addresses / social handles), not secrets. **Action:** no app-level encryption required for those fields; protect DB file permissions and backups; encrypt disk if host is multi-tenant.

---

## Section C: Integration Notes

### New code

- `chain_mesh/security.py` (no new pip packages required for core fixes)

### Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `CHAIN_MESH_API_TOKEN` / `BLOODSTONE_API_TOKEN` | empty → fall back to publish token | Write API secret |
| `CHAIN_MESH_PUBLISH_TOKEN` | empty | Asset/partner publish secret |
| `CHAIN_MESH_REQUIRE_WRITE_AUTH` | **`1`** | Reject writes if no token configured |
| `CHAIN_MESH_LAN_OPEN_REGISTER` | `0` | Allow unauthenticated LAN register with private URLs only |
| `CHAIN_MESH_ALLOW_LOOPBACK_REGISTER` | `1` | Allow `127.0.0.1` for local AI/DTN |
| `DTN_TLS_VERIFY` | **`1`** (was 0) | Verify peer TLS |
| `DTN_TLS_FALLBACK_HTTP` | **`0`** (was 1) | HTTP fallback after TLS fail |
| `DTN_TLS_CA_FILE` | empty | CA bundle for LAN TLS |
| `DTN_TLS_BIND` | **`127.0.0.1`** (was all interfaces) | TLS proxy listen address |

### Breaking configuration changes

1. **Write endpoints** reject without token when auth is required and no token is set.  
2. **DTN TLS verify on** may break self-signed LAN peers until CA is distributed or lab sets `DTN_TLS_VERIFY=0`.  
3. **TLS proxy** no longer listens on `0.0.0.0` by default — set `DTN_TLS_BIND=0.0.0.0` for LAN HTTPS if firewall-controlled.  
4. **Peer/AI registration** rejects public internet URLs (SSRF).  

### Client call example

```bash
curl -sS -X POST https://coordinator/api/convergence/dtn/peers/register \
  -H 'Content-Type: application/json' \
  -H 'X-Api-Token: YOUR_TOKEN' \
  -d '{"base_url":"http://192.168.1.50:8887","node_id":"pi-shed","source":"manual"}'
```

### Restart services after deploy

```bash
systemctl restart bloodstone-portal bloodstone-miner-web 2>/dev/null || true
# if running DTN TLS proxy:
# systemctl restart bloodstone-dtn-tls  # or your unit name
```

### Optional dependency (future)

```bash
pip install 'Flask-Limiter>=3,<4'   # multi-worker rate limits; not required for in-process limiter
```

---

## Verification smoke tests (operator)

```bash
python3 -c "from chain_mesh.security import validate_url_ssrf; validate_url_ssrf('http://192.168.0.1:8887', mode='lan_only'); print('ok')"
# Expect failure:
python3 -c "from chain_mesh.security import validate_url_ssrf; validate_url_ssrf('http://169.254.169.254/', mode='block_internal')"
```

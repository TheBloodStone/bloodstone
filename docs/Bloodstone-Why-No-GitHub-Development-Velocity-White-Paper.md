# Bloodstone Development Velocity & Source Distribution

## Why We Do Not Maintain a Public GitHub — and What We Ship Instead

**Document version:** 1.0 · July 2026  
**Audience:** Partners, exchanges, integrators, and contributors who expect a traditional open-source repository  
**Coordinator:** https://bloodstonewallet.mytunnel.org

---

## Executive summary

Bloodstone does **not** maintain a single public GitHub repository that tracks every change across our production stack. That is a deliberate operational choice, not an accident.

We develop across **many interdependent surfaces** — Core node binaries, Windows Qt wallet, Android full-node + miner APK, web UI OTA bundles, pool VPS services, portal APIs, chain mesh assets, exchange node packages, and partner documentation — often shipping **multiple versioned artifacts per day**. Forcing each change through a public Git workflow (commit, push, PR, CI, release tag, changelog sync) would **slow that pipeline from hours to days** without improving what end users actually download.

Instead, Bloodstone publishes **verifiable artifacts**: versioned binaries with SHA-256 checksums, mesh-anchored documents and packages (BSM1), OTA web bundles, and a unified downloads portal. Upstream **SpaceXpanse / rod-core-wallet** remains the public C++ heritage reference; Bloodstone’s relaunch layer is distributed as **built releases and anchored assets**, not as a continuously mirrored monorepo.

This paper explains the trade-off honestly: what we gain, what we give up, and what a future snapshot publication model could look like.

---

## 1. The question partners ask

> “Where is your GitHub? How do we audit the code?”

Fair question. Most blockchain projects point to one repository and one release page. Bloodstone’s answer is more distributed:

| Expectation | Bloodstone today |
|-------------|------------------|
| One `git clone` builds everything | **No** — production spans Core C++, Java/Android, Python services, Electron GUIs, nginx portal, mesh tooling |
| Every fix has a public commit hash | **Partial** — C++ lineage traces to public SpaceXpanse sources; Bloodstone relaunch patches ship as **versioned binaries** |
| Releases lag development by one PR cycle | **No** — we optimize for **time-to-downloadable-artifact**, not time-to-green-CI-on-main |

We publish **what integrators need to run** (nodes, wallets, pool clients, API packs, white papers). We do not publish a live mirror of every intermediate edit across all VPS and device trees.

---

## 2. What we actually maintain (scope)

Bloodstone production is not one repository. On a typical week the active surface includes:

| Layer | Examples | Versioning style |
|-------|----------|------------------|
| **Core node** | `bloodstoned`, `bloodstone-cli`, Qt wallet | Semver (e.g. 0.7.2) |
| **Android** | Full node plugin, LAN pool coordinator, stratum | APK **1.3.84+** |
| **Web miner UI** | Capacitor OTA bundle | **1.3.129-web+** (independent from APK) |
| **Pool / portal** | Stratum VPS, unified portal, exchange listing API | Env-driven deploy |
| **Mesh / docs** | White papers, partner responses, exchange node tarballs | BSM1 mesh anchors + `/downloads/` |
| **Windows GUIs** | Qt core wallet, Electron wallet/node installers | Per-artifact semver |

A **single GitHub repo** cannot represent this without either:

1. **Monorepo chaos** — thousands of commits mixing unrelated surfaces, or  
2. **Multi-repo overhead** — dozens of repos each needing PR discipline, CI, and release coordination.

Both models assume development moves at **pull-request speed**. Bloodstone often moves at **OTA speed**.

---

## 3. Development at operational velocity

### 3.1 Parallel version streams

Bloodstone routinely ships **independent version lines** that must not block each other:

- Android APK can advance (**1.3.84**) while web OTA advances (**1.3.129-web**) while Core advances (**0.7.2**) — on the same day.
- A LAN pool coordinator fix in Java does not wait for a Windows Qt cross-compile to finish before users receive the web bundle routing update.
- Partner documents (Blurt responses, exchange packs) publish to mesh **within hours** of a technical decision.

GitHub-centric workflows optimize for **one canonical branch**. Bloodstone optimizes for **many publishable artifacts**.

### 3.2 The hidden cost of “just push to GitHub”

For each logical change, a traditional open-source pipeline adds:

| Step | Typical time cost | Bloodstone impact |
|------|-------------------|-------------------|
| Clean commit + message | 5–15 min | Context-switch away from live VPS / device testing |
| Push + wait for CI | 10–60 min | Blocks next experiment on same tree |
| PR review (even self-review hygiene) | 30 min – hours | Unacceptable when pool or OTA is down |
| Changelog / README / version bump sync | 15–45 min | Must touch multiple packages (portal, downloads index, mesh key) |
| GitHub Release asset upload | 15–30 min | **Duplicate** of work already done on `/downloads/` + mesh |
| Issue triage from partial public state | Ongoing | Users file bugs against stale `main` |

Conservatively, **each production fix costs 1–3 hours of Git overhead** if done “properly.” At our cadence (multiple fixes per day across surfaces), that is **5–15 hours per day** diverted from building and deploying — effectively **halving or thirding** engineering throughput.

> **We develop at the speed the network needs, not at the speed GitHub etiquette prefers.**

### 3.3 What “upload between versions” would mean in practice

If every shipped version required a full GitHub sync:

```
Fix stratum edge case → build APK → test on LAN → 
  git add/commit (android) → push → 
  bump web OTA → git add/commit (miner-web) → push → 
  update portal API version env → git add/commit (portal) → push → 
  rebuild exchange node tarball → git add/commit (ops) → push → 
  regenerate white paper → git add/commit (docs) → push → 
  create GitHub Release × N artifacts → 
  answer issues about commit abc123 vs binary def456
```

That is not version control — it is **release theatre**. The artifacts users need are already on:

- https://bloodstonewallet.mytunnel.org/downloads/
- Chain mesh (BSM1-anchored keys under `downloads/…`)
- Android OTA endpoint (web bundle)
- Pool coordinator API (`/api/exchange`, `/api/…`)

GitHub would be a **second publication layer** we must keep synchronized, with no user-facing benefit over checksum-verified downloads we already ship.

---

## 4. What we publish instead of a live repo

Bloodstone’s distribution model is **artifact-first, verify-second**:

### 4.1 Downloads portal

All primary binaries and documents land on the coordinator downloads host with **SHA-256 sidecars**:

- Core node / Qt wallet / exchange node packages  
- Android APK (`bloodstone-miner-android-latest.apk` symlink)  
- Partner white papers (MD + DOCX)  
- Fix scripts and integration packs  

Integrators verify integrity with published checksums — no `git clone` required.

### 4.2 Chain mesh anchors (BSM1)

Large or policy-important assets are **mesh-published** with:

- Content-addressed chunks (256 KiB)  
- Merkle root + file SHA-256  
- On-chain BSM1 anchor transaction  
- Stable `asset_key` (e.g. `downloads/bloodstone-exchange-node-0.7.0-linux-x86_64.tar.gz`)

This gives a **tamper-evident publication trail** without exposing every intermediate source edit.

### 4.3 OTA web bundles

The Android miner UI updates via **over-the-air web bundle** independent of APK store cycles. Users tap **Updates → Check for updates** and receive routing/UI fixes without reinstalling the native shell — a delivery path GitHub Releases cannot replicate.

### 4.4 API listing packs

Exchanges and partners consume **machine-readable listing packs** (`/api/exchange`, `/api/…`) tied to live infrastructure (ElectrumX, seeds, package filenames). The API is the contract — not a branch name.

### 4.5 Upstream C++ heritage

Bloodstone Core descends from the public **SpaceXpanse rod-core-wallet** lineage (Bitcoin Core architecture, multi-algo PoW, name/game RPC heritage). Partners auditing consensus-level C++ can start there. Bloodstone relaunch patches (genesis blob, STONE branding, subsidy scaling, LAN coordinator hooks) ship in **our built Core releases**, documented in release notes and white papers.

---

## 5. Trade-offs (honest)

### 5.1 What we gain

| Benefit | Explanation |
|---------|-------------|
| **Velocity** | Ship pool fix, OTA bundle, and doc update same day |
| **Operational focus** | Engineers test on live seeds/VPS/devices, not CI matrices |
| **Simpler partner story** | “Download this tarball, verify this SHA-256, call this API” |
| **Reduced attack surface** | No public CI tokens, no accidental secret commits, no fork confusion |
| **Multi-surface freedom** | APK, web, Core, portal versions evolve independently |

### 5.2 What we give up

| Cost | Explanation |
|------|-------------|
| **GitHub discoverability** | Developers cannot `git clone` Bloodstone’s full stack |
| **Community PR workflow** | External contributors lack a single obvious entry point |
| **Line-by-line audit trail** | Partners must trust binaries + docs + mesh anchors, not every diff |
| **Reputation signal** | Some listings penalize projects without active public repos |
| **Reproducible build recipes** | We publish checksums; full reproducible build docs are incomplete |

We accept these costs **for now** because shipping a relaunch network, pool, mesh, and mobile node path outweighs the branding benefit of a green GitHub activity chart.

---

## 6. How difficult would a full GitHub mirror be?

**Technically feasible. Operationally expensive.**

### 6.1 Repository strategies

| Approach | Difficulty | Problem |
|----------|------------|---------|
| **Single monorepo** | High setup, ongoing merge pain | Android + Python + C++ + docs in one tree → enormous clones, mixed commit noise |
| **Multi-repo (10–20)** | Medium setup, high process load | Each repo needs CI, releases, issue templates, version tags |
| **Periodic snapshots** | Low ongoing cost | Stale within days; users still cannot build latest production |
| **Read-only mirrors** | Medium automation | Must sanitize VPS secrets, paths, keys; still lags hours behind |

### 6.2 Estimated ongoing burden (if done “properly”)

Assuming we mirrored **only** production surfaces (not every experimental VPS script):

| Activity | Hours / week (estimate) |
|----------|-------------------------|
| Commit hygiene + push across repos | 8–15 h |
| CI maintenance (Linux + Windows + Android) | 5–10 h |
| Release tagging aligned with downloads | 3–5 h |
| Issue/PR triage on stale public code | 2–8 h |
| Secret scrubbing + conflict resolution | 2–5 h |
| **Total** | **20–43 h / week** |

That is **half to full time of one engineer** — solely to keep GitHub **as current as our downloads page already is**.

### 6.3 Why snapshots do not solve it

Quarterly “snapshot dumps” to GitHub satisfy checkbox audits but:

- Users clone code that **does not build** the live network without undisclosed VPS configs  
- Bug reports reference **old snapshots**  
- Partners still download binaries from `/downloads/` anyway  

Snapshots are **the worst of both worlds**: maintenance cost plus misleading impression of live sync.

---

## 7. Recommended path for integrators today

Until (unless) we publish a maintained source snapshot:

1. **Verify artifacts** — SHA-256 from `/downloads/*.sha256`  
2. **Read listing packs** — `https://bloodstonewallet.mytunnel.org/api/exchange`  
3. **Audit mesh anchors** — BSM1 txid + Merkle root for critical packages  
4. **Study upstream Core** — SpaceXpanse rod-core-wallet architecture for consensus context  
5. **Read white papers** — economics, mesh, LAN pool, infrastructure independence  
6. **Contact us** — for exchange or partner integration packs not yet on downloads  

This is how Bloodstone operates **today**, successfully, with live mainnet, pool, mesh, and mobile node paths.

---

## 8. Future options (not commitments)

We may, when velocity allows:

| Option | Description |
|--------|-------------|
| **Tagged Core snapshot repo** | Periodic export of `bloodstone-chain` at Core semver tags only |
| **Open docs + specs repo** | Markdown/API specs without VPS-only scripts |
| **Reproducible build guide** | Document how to verify Core binaries against a tag |
| **Contributor sandbox** | Separate repo for non-production experiments |

We will **not** promise real-time GitHub parity with VPS iteration. That promise would be dishonest.

---

## 9. Conclusion

Bloodstone chooses **artifact velocity** over **repository theatre**.

We develop at the speed our network, pool, and partners require — multiple version lines per day, OTA course corrections, mesh-published documents, and checksum-verified binaries. Maintaining a public GitHub that faithfully mirrors that work would consume **20–40+ engineer-hours per week** and **slow the delivery path users already rely on**, without replacing the downloads portal, mesh anchors, or API listing packs integrators actually use.

The public GitHub link on our portal points to **upstream heritage** (SpaceXpanse rod-core-wallet). Bloodstone’s relaunch layer is distributed as **built, verified, documented releases** — because that is what keeps STONE infrastructure moving at operational speed.

---

## Related documents

- [Development Journey White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Development-Journey-White-Paper.docx)
- [Infrastructure Independence White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Infrastructure-Independence-White-Paper.docx)
- [Chain Mesh Storage White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx)
- [LAN Pool Coordinator Guide](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-LAN-Pool-Coordinator-Guide.md)

---

*Bloodstone · Development velocity & source distribution · July 2026*
# AGENTS.md — Bloodstone Builder Operating Instructions

**Audience:** any AI agent performing build, code, or specification work on Bloodstone.
**Status:** persistent instructions. These survive across project phases. Phase-specific priorities live in the Roadmap, not here.
**Authority:** subordinate to the **Bloodstone Protocol Constitution** (current version in-repo). Where this file and the Constitution conflict, the Constitution governs.

---

## 0. How to read this file

These are durable operating rules, not a task list. They describe *how* to work on Bloodstone regardless of what is being built this month. When the project pivots — new phase, new component, new priorities — **this file stays; the Roadmap changes.** If a rule here ever seems to block correct work, stop and flag it rather than working around it.

Two documents govern everything and must be consulted, not remembered:

- **Constitution** — what Bloodstone is; the principles and prohibitions every change must satisfy.
- **Roadmap** — what is being built now and in what order.

Do not restate their contents from memory. Read them.

| Document | Agent-local path | Public |
|----------|------------------|--------|
| Constitution | `/root/Bloodstone-Protocol-Constitution.md` | https://bloodstone.rocks/downloads/Bloodstone-Protocol-Constitution.md |
| Roadmap | `/root/Bloodstone-Development-Roadmap.md` | https://bloodstone.rocks/downloads/Bloodstone-Development-Roadmap.md |

---

## 1. NON-NEGOTIABLES (never / always)

These exist because each was learned through a real, costly failure. None may be skipped for speed.

- **ALWAYS** verify after writing: follow every push / file write with a read-back to confirm it landed. Silent write failures have happened; a successful call is not proof of a successful write.
- **ALWAYS** do a full tree rebuild after any change to consensus parameters, deployment arrays, or `Consensus::Params`. Partial rebuilds have produced ABI-mismatched, segfaulting binaries. No exceptions.
- **ALWAYS** report test *results*, never test *intentions*. Paste actual console output. "The tests pass" is not evidence; the output is. A green run from a stale binary is not a green run.
- **ALWAYS** state real values: actual heights, tags, SHA256 hashes, dates, block times. Never placeholders in anything an operator, exchange, or reviewer will act on. A wrong hash can put the wrong binary into production.
- **NEVER** merge to `main` or cut a release from unreviewed work. Consensus-affecting changes merge only after adversarial review and sign-off (Constitution Art. V.1–V.2).
- **NEVER** bundle unrelated consensus changes in one PR. One change, one PR, one test surface, so a failure in one cannot corrupt another.
- **NEVER** begin implementation from a design with open conceptual questions (Constitution Art. V.1). If the spec has unresolved decisions, stop and surface them; do not invent answers.
- **NEVER** expand scope silently. Implement what is specified. If broader work seems necessary, flag it explicitly and wait (Constitution Art. V.6).

---

## 2. Source control and durability

- **GitHub is the source of truth and the durability backup.** The build host (VPS) also serves the portal, so a local build that is not pushed to GitHub exists in exactly one place and dies with the host. Pushing to GitHub is not a preference; it is the backup. "Built locally and put on the portal" is an **incomplete** release.
- **Local build ≠ published.** Every release artifact must reach GitHub *and* the portal, and the two must **match by SHA256**. If they do not match, the release is broken, not "mostly done."
- **Branch freely; merge carefully.** Push work-in-progress to branches as often as useful. `main` and release branches are gated (§1, §4).
- **Verify every push** with a read-back (§1). Do not assume a push landed because the command returned.
- **Commit messages state what changed and why**, referencing the RFC or Roadmap item where applicable.
- **Forgetting to push is the most common failure on this host.** When work is done locally, pushing to GitHub is part of "done," not a later step.

---

## 3. Links — match the link to its purpose

There is no single "best" link type. The correct link depends on **who is using it and for what**. Get this wrong in either direction and the link fails its job.

**3.1 — For reviewers and agents (something to *read and fetch*):**
- Use a **fetchable** link — **raw GitHub** when a repo exists.
- If the only source is a portal tarball with no repo yet (e.g. MFQ), say so explicitly: *"tarball is the audit source; no public repo yet."* Do not pretend a GitHub link exists.
- **Portal-hosted `.md` documents frequently serve as opaque binary and cannot be fetched by reviewers.** Fix the portal content-type so `.md` serves as text, or mirror reviewer-facing docs to a fetchable location (raw GitHub). A document a reviewer cannot open cannot be reviewed.

**3.2 — For end users (something to *download, verify, and run*):**
Provide **both** a GitHub release link **and** the portal link, plus verification metadata. Reasons:
- **GitHub release downloads add trust and pass antivirus.** Portal / custom-domain download links frequently trigger antivirus and browser warnings; a GitHub Releases link for the same artifact is widely trusted and reassures users the download is genuine.
- The portal link is the operator's own channel and carries the `-latest` alias; keep it, but never as the *only* link.
- **Never give a raw GitHub blob as an end-user download** — users cannot verify or run a raw source blob; that is a reviewer link, not a distribution link.

**3.3 — Required artifact format (the MFQ template — use for every Fork Lab download):**
Every distributed artifact ships with all of:
- **Versioned download link** (GitHub release **and** portal)
- **SHA256** of the versioned artifact
- **`-latest` alias** (portal), with the convention below
- **README** link (fetchable)
- **Release notes** link (fetchable)
- **Source of audit** stated explicitly — repo URL, or *"this tarball is the source, no repo yet"*

**3.4 — The `-latest` convention:**
- `-latest` is a moving pointer and therefore carries **no fixed hash**. Always state that `-latest` resolves to the current versioned release, and that the hash to verify against is the **versioned** artifact's SHA256 — never imply `-latest` itself has a stable checksum.

---

## 4. Release tagging

- **Tags mark releases, not commits.** Cut a release tag when a change reaches `main` through the gate — not on every push. Tagging every commit produces meaningless version noise and destroys the tag's value as a signal.
- **A release tag means "reviewed, built, and safe to run."** Operators and exchanges rely on tags to know which binary to trust. Never tag unreviewed or unbuilt work as a release.
- **A tagged release must exist on GitHub with its artifacts attached**, so the GitHub release link in §3.2 is real. A tag with no published artifacts is not a release.
- **Bump the version on each real release**, following the project's existing scheme (e.g. `vX.Y.Z`, with a suffix for a coordinated consensus event such as `-h1`). Record the release SHA256 alongside the tag.
- **A consensus-activating release is a coordinated event, not a routine tag.** Anything that changes consensus rules, activation heights, or network behaviour requires operator/exchange coordination *before* the tag is treated as live (§7).

---

## 5. Consensus safety

- **Consult the Constitution's compliance test (Article VII) for anything touching consensus** and answer it in the PR: ledger, state, measurement, proof class, value conservation, funding, parameters, actors, production impact, maturity, falsification target.
- **Full rebuild after consensus-param changes** (§1).
- **Never introduce account-style mutable per-entity state** (Constitution Art. I.4). If a design seems to need it, the pattern is commitment-and-verification, not stored balances.
- **Never let consensus measure the physical world** (Constitution Art. I.3). Consensus verifies attestations and mathematics only.
- **Keep changes minimal and non-programmable** (Constitution Art. I.5). No general-purpose covenant or scripting surface.
- **Grandfathering / activation heights:** when a new rule would reject existing history, it must be height-gated so historical blocks remain valid and IBD/reindex succeeds. Test reconstruction across the activation boundary explicitly.

---

## 6. Testing and evidence

- **Report results, not intentions** (§1).
- **One binary, both/all suites.** When a change touches multiple test suites, the reported green run must come from a single build carrying all fixes — never one suite from one binary and another from a different build.
- **Assertions must test something.** Tautological checks (always-true conditions) are defects, not passes. An assertion that cannot fail proves nothing.
- **Conservation and determinism are invariants, not spot-checks.** Where value is allocated or state is derived, assert exact conservation / identical reconstruction as a test, not an approximation.
- **Attack tests prove both sides:** that the rule fires when it should *and* does not fire when it should not (no false positives on honest input).
- **Ground truth over assumption** (Constitution Art. V.4): measure block times, difficulty behaviour, and parameters against the actual chain. Never propagate an assumed constant; if a number is a judgment figure, label it unvalidated.

---

## 7. Coordinated / production-affecting changes

- **Production stability outranks progress** (Constitution Art. IV.3). Never disrupt the running network for a build or a test. Prototypes run alongside production, never through it.
- **Consensus-activating changes require coordination before activation:** confirm node coverage across all template sources, miners, and any exchange; verify clocks/NTP where a time rule is involved; stand up a boundary watch; confirm identical tip hashes across independent nodes after the event.
- **Verify the network is one network** after any boundary: independent nodes must report the same block hash at the same height, not merely the same height.
- **An upgrade ACK names the version and hash**, never just "upgraded." Verify the reported binary against the published release.

---

## 8. Reporting and communication

- **State uncertainty honestly.** "This passed" and "this should pass" are different claims; distinguish them. If something is unverified, say so.
- **Separate what was done from what was designed.** A design description is not evidence of working code; a passing local test is not evidence of network behaviour.
- **Flag, don't absorb.** When something is out of scope, contradicts the Constitution, or depends on an unresolved decision, surface it rather than quietly resolving it.
- **Distinguish self-verifying from attested claims** (Constitution Art. II). When reporting on any contribution or reward mechanism, state which trust class applies.

---

## 9. Working with the review process

- **Design and criticism are separate roles** (Constitution Art. V.2). The builder implements and reports; adversarial review is a separate step and is expected. Do not treat review findings as adversarial hostility — they are the process working.
- **Convergence is not verification** (Constitution Art. V.3). Multiple agents agreeing is not proof. If several reviews align, the alignment itself should still be checked against the code and first principles.
- **A review that returns no findings is a valid result** (Constitution Art. V.5). Do not manufacture changes to appear responsive.
- **When corrected, fix the root, not the symptom.** Record the corrected understanding so the same class of error does not recur.

---

## 10. When in doubt

- If a rule here blocks correct work, **stop and flag it** — do not work around it.
- If the Constitution and a task conflict, **the Constitution wins** and the task is wrong.
- If a parameter, block time, or behaviour is assumed rather than measured, **measure it** before building on it.
- If a document cannot be fetched by a reviewer, **rehost it somewhere fetchable** before proceeding.

---

*AGENTS.md — persistent builder discipline for Bloodstone. Phase priorities live in the Roadmap; principles live in the Constitution; this file is how the work is done regardless of phase.*

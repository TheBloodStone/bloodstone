# Bloodstone Linux Node Installer & Release Security Audit

## Final Consolidated Remediation & Production Readiness Assessment

**Project:** Bloodstone Linux Node Package  
**Scope:** Installer Scripts, Bootstrap Process, Release Verification, Source Installation, Operational Security  
**Audit Date:** July 2026  
**Status:** **PASS – Production Ready (with recommended assurance enhancements)**

---

# Executive Summary

The Bloodstone Linux Node installer package has undergone multiple independent security reviews and an additional comprehensive audit against the current implementation.

The latest implementation demonstrates a significant security-first engineering approach and compares favourably with mature open-source cryptocurrency infrastructure projects.

The package incorporates modern shell hardening, secure configuration defaults, cryptographic release verification, checksum validation, bootstrap archive sanitisation, and least-privilege file handling.

Importantly, the current codebase resolves the operational vulnerabilities identified in earlier revisions.

No Critical or High severity vulnerabilities remain within the reviewed installer package.

The remaining recommendations focus on strengthening software supply-chain assurance, operational resilience, and long-term maintainability rather than correcting exploitable defects.

---

# Overall Assessment

| Category                | Rating       |
| ----------------------- | ------------ |
| Shell Security          | 9.5 / 10     |
| Supply Chain Security   | 9.0 / 10     |
| Linux Best Practices    | 9.0 / 10     |
| Operational Reliability | 9.0 / 10     |
| Documentation           | 9.0 / 10     |
| Production Readiness    | 9.0 / 10     |
| Overall                 | **9.1 / 10** |

Current status:

**Production Ready**

---

# Verified Strengths

## Shell Hardening

The installer consistently applies modern defensive Bash practices including:

* `set -euo pipefail`
* restricted `IFS`
* restrictive `umask 077`
* proper quoting
* use of secure temporary files
* robust error handling

This eliminates many common shell scripting vulnerabilities.

**Status:** Complete

---

## Secure Configuration Permissions

Configuration directories and RPC configuration files are created using restrictive permissions.

Verified protections include:

* configuration directory permissions (`700`)
* configuration file permissions (`600`)
* automatic tightening of permissions on existing installations

This prevents unintended disclosure of RPC credentials to other local users.

**Status:** Complete

---

## Secure RPC Credentials

The installer generates random RPC credentials rather than shipping predictable defaults.

This significantly improves default node security.

**Status:** Complete

---

## HTTPS Enforcement

Downloads are restricted to HTTPS transport where supported.

The installer enforces modern TLS and prevents protocol downgrade attacks.

Where available:

* HTTPS only
* TLS 1.2+
* secure curl options
* secure wget fallback

**Status:** Complete

---

## Release Verification

Binary releases are verified using:

* SHA-256 checksums
* optional OpenPGP verification

This provides strong protection against corrupted or tampered releases.

**Status:** Complete

---

## Bootstrap Archive Hardening

The bootstrap installation process demonstrates strong defensive engineering.

Verified protections include:

* SHA-256 validation
* path traversal detection
* rejection of symbolic links
* rejection of hard links
* ownership stripping
* permission stripping
* safe extraction flags

These measures substantially reduce the risk of archive-based privilege escalation.

**Status:** Complete

---

## Least Privilege

The installer operates with elevated privileges only where required.

Configuration ownership and permissions follow the principle of least privilege.

**Status:** Complete

---

## Source Installation

The package provides a documented source installation path for users preferring independently compiled binaries.

This improves transparency and trust.

**Status:** Complete

---

# Security Findings

## Critical

**None**

---

## High

**None**

---

## Medium

### 1. Source Builds Should Verify Signed Git Tags

Current source builds trust the selected Git reference.

For maximum supply-chain assurance the release process should move to signed immutable Git tags.

Recommended improvements:

* signed release tags
* `git verify-tag`
* optional `git verify-commit`

This closes the remaining trust gap for source installations.

**Priority:** High

---

### 2. Immutable Releases

Building directly from `main` reduces reproducibility.

Source installation should default to immutable release tags.

Examples:

* `v0.8.0`
* release branches
* pinned commit hashes

**Priority:** High

---

### 3. Seed Infrastructure Diversity

The installer currently provides sensible default seed nodes.

For long-term decentralisation the project should expand to:

* additional geographically diverse seed nodes
* independently operated infrastructure
* DNS seed support

This improves bootstrap resilience without changing the default user experience.

**Priority:** Medium

---

### 4. Build Metadata

Every release should include reproducible build metadata.

Recommended:

* Git commit
* Git tag
* compiler version
* Boost version
* OpenSSL version
* build architecture
* binary SHA-256
* build timestamp

Example:

```
BUILD-INFO.txt
```

This greatly improves debugging and release traceability.

**Priority:** Medium

---

# Low Severity Recommendations

## Installer Logging

Generate installation logs automatically.

Suggested outputs:

* install.log
* bootstrap.log

Useful for support and diagnostics.

---

## Existing Daemon Detection

The startup script should detect an already running daemon and avoid duplicate launches.

---

## Additional Architecture Support

Future releases may consider:

* RISC-V
* ARMv7

Current architecture detection is appropriate.

---

# Operational Hardening Recommendations

These recommendations improve operational robustness rather than address vulnerabilities.

---

## Hardened systemd Service

A first-party systemd unit is strongly recommended.

Suggested hardening:

* ProtectSystem=strict
* ProtectHome=true
* PrivateTmp=true
* NoNewPrivileges=true
* MemoryDenyWriteExecute=true
* RestrictAddressFamilies=
* Restart=on-failure
* RestartSec=
* WatchdogSec=

This represents the largest remaining operational improvement.

---

## Health Check Utility

Provide a lightweight operational utility.

Suggested command:

```
bloodstone-health
```

Checks:

* daemon status
* chain height
* peer count
* RPC responsiveness
* available disk space
* bootstrap status
* configuration validation

---

## Official Docker Image

Provide a minimal signed container image.

Recommended:

* reproducible builds
* immutable image digests
* minimal base image

---

# Software Supply Chain Recommendations

These recommendations increase confidence in released software.

---

## Signed Git Tags

Highest remaining priority.

Release tags should be cryptographically signed.

---

## Reproducible Builds

Ensure identical source always produces identical binaries.

Publish build metadata alongside every release.

---

## Software Bill of Materials (SBOM)

Publish an SPDX or CycloneDX SBOM for every release.

Benefits:

* dependency visibility
* vulnerability tracking
* enterprise compatibility

---

## Release Provenance

Consider adopting SLSA provenance for official releases.

This provides independently verifiable build provenance.

---

## Cosign Signatures

Future releases may additionally support Sigstore/Cosign verification alongside OpenPGP.

Not required today, but a strong long-term enhancement.

---

# Red Team Assessment

The reviewed installer presents a limited attack surface.

Realistic attack vectors are now primarily external to the installer itself.

Remaining theoretical attack paths include:

* compromise of GitHub repository before tagging
* compromise of signing keys
* compromise of bootstrap infrastructure
* operator misuse of verification bypass options

The current implementation already mitigates the majority of practical installer attacks through:

* checksum verification
* optional OpenPGP verification
* HTTPS enforcement
* archive sanitisation
* restrictive file permissions
* shell hardening

No practical command injection, privilege escalation, archive traversal, or credential disclosure vectors were identified in the reviewed installer.

---

# Overall Security Posture

The installer demonstrates:

✓ Secure shell engineering

✓ Strong release verification

✓ Safe bootstrap extraction

✓ Secure configuration defaults

✓ Principle of least privilege

✓ Modern TLS enforcement

✓ Defensive Bash practices

✓ Clear operational documentation

The remaining recommendations are focused on increasing assurance rather than remediating exploitable weaknesses.

---

# Final Verdict

## PASS – Production Ready

The Bloodstone Linux Node installer is suitable for public production deployment.

The installer exhibits a mature security posture that exceeds the quality commonly found in independent blockchain projects.

No Critical or High severity issues remain within the reviewed scope.

Future development should focus on:

1. Cryptographically signed Git tags for source installations.
2. Hardened first-party systemd service files.
3. Reproducible build metadata.
4. Expanded independent seed infrastructure.
5. SBOM generation and release provenance.

Collectively, these enhancements would elevate the project from an already well-engineered installer to one aligned with the operational and supply-chain practices of mature cryptocurrency infrastructure projects such as Bitcoin Core, Monero, and other long-established open-source ecosystems.

**Final Rating:** **9.1 / 10 – Production Ready**

---

## Bloodstone follow-up (operator notes)

Related remediation write-up: [Bloodstone-Node-0.7.6-Security-Audit-Remediation.md](Bloodstone-Node-0.7.6-Security-Audit-Remediation.md)

Installer surface under audit: `packages/linux-node/` (see monorepo `AUDITOR-MAP.md` / package `MANIFEST.md`).

Assurance enhancements shipped after this verdict (same package tree):

* Hardened `bloodstone-node.service` + `install-systemd.sh`
* `bloodstone-health` / `bloodstone-health.sh`
* Install logging under `$BLOODSTONE_DATADIR/logs/`
* Daemon already-running detection in `start-node.sh`
* Source install defaults to immutable tag (`v0.7.6-h1`) + optional `git verify-tag`
* `BUILD-INFO.txt` / expanded provenance on package and source builds

# Bloodstone PGP release signing

**Doc version:** 1.0 · 2026-07-21  

## Why

SHA-256 proves a file matches the checksum on the download server.  
**PGP** proves that checksum was produced by Bloodstone’s release key — so a compromised host cannot silently replace both the binary and the `.sha256` file.

## Public key

| Item | Value |
|------|--------|
| **Download** | https://bloodstone.rocks/downloads/bloodstone-release-key.asc |
| **Fingerprint** | `3267 95FA 0B4E 7C97 5276  AB9F F625 5B97 0D66 42AD` |
| **Key ID** | `F6255B970D6642AD` |
| **UIDs** | Bloodstone Release Signing &lt;releases@bloodstone.rocks&gt; · Bootstrap Signing (legacy uid) |

```bash
curl -fsSL https://bloodstone.rocks/downloads/bloodstone-release-key.asc | gpg --import
gpg --list-keys 326795FA0B4E7C975276AB9FF6255B970D6642AD
```

## Verify a release (user)

```bash
# From packages/linux-node or a tarball that includes verify-release.sh
./verify-release.sh bloodstone-node-0.7.6-linux-aarch64.tar.gz

# Strict (fail if no PGP):
BLOODSTONE_REQUIRE_PGP=1 ./verify-release.sh bloodstone-node-0.7.6-linux-aarch64.tar.gz
```

This checks:

1. `.sha256.asc` with the Bloodstone public key (**authenticity**)  
2. SHA-256 of the file against `.sha256` (**integrity**)

## Sign a release (maintainer / VPS)

Private key lives **only** under `GNUPGHOME=/root/.bloodstone/gnupg-bootstrap` (not in the web tree).

```bash
# After building an artifact + writing file.sha256:
/root/sign-bloodstone-release.sh /var/www/bloodstone/downloads/my-artifact.tar.gz
# produces my-artifact.tar.gz.sha256.asc
```

Publish: `file`, `file.sha256`, `file.sha256.asc`, and always `bloodstone-release-key.asc`.

## Trust model

| Layer | Protects against |
|-------|------------------|
| SHA-256 | Corruption / accidental mismatch |
| PGP on `.sha256` | Attacker who can rewrite downloads but **not** the private key |
| `install-from-source.sh` | You compile from the public monorepo yourself |

**Operational note:** Back up the private key offline. Do not put the private key on the public downloads worker.


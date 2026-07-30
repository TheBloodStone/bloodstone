# Ecosystem forks (monorepo)

Child coins of Bloodstone live under `forks/<ticker>/` so MFQ provenance and security patches share one audit surface.

| Directory | Ticker | AuxPoW chain id | Status |
|-----------|--------|-----------------|--------|
| [`lrgk/`](lrgk/) | LRGK | 1900 | Stub |
| [`azure/`](azure/) | AZURE | 1901 | Stub |

**Parent (STONE) core** remains under `core/` / `chain/` with AuxPoW chain id **1899**.

Future forks: add `forks/<ticker>/`, allocate chain id ≥ 1902, document in AUDITOR-MAP and MFQ manifest provenance.

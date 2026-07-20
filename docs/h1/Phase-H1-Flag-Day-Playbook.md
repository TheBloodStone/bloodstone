# Phase H1 — Flag-day playbook

**Status:** Height-gate **in tree** with **placeholder** mainnet *H* — **not** good-to-go  
**Path locked:** coordinated **flag-day** (not genesis relaunch)  
**Scope:** timewarp-only (H1). **Vault bit-5 is a separate later flag-day.**  
**Cexius:** thank them; **no private drop**; notify when public versioned build is live and safe to upgrade.

---

## Sequence to “good to go”

1. **Gate (placeholder *H*) + both-rule tests** ← current  
2. **Freeze *H*** (tip + notice days + margin)  
3. **Merge / tag / publish** binary + SHA256 + downloads index  
4. **Re-scan at tip** at freeze  
5. **Message Cexius** — good to go / upgrade from public channel before *H*

Do **not** tell Cexius “good to go” before steps 1–4.

---

## 0. Scan result (live mainnet)

See **[h1-nonretroactivity-scan-latest.md](h1-nonretroactivity-scan-latest.md)**.

| Finding | Ops meaning |
|---------|-------------|
| Window-min **741** early-chain | **Height-gate mandatory** — grandfather history |
| Future A/B = **0** | Future-stamp proxies clean; still gate MAX_FUTURE at *H* with window |
| Flag-day | Viable with activation height *H* |

---

## 1. Implementation notes

- Param: `consensus.nH1TimewarpActivationHeight`  
- Mainnet placeholder: `INT_MAX` until freeze  
- Helper: `CheckH1HeaderTimeRules` (validation + tests)  
- Named tests: see `Phase-H1-Grandfathering-Activation-Height.md`

---

## 2. Activation height *H* (freeze later — do not guess)

```text
H ≈ tip_at_announce + D × 960 + margin
margin_recommended ≥ 1 day ≈ 960 blocks
```

Cexius can upgrade quickly; still leave multi-day margin for operators.

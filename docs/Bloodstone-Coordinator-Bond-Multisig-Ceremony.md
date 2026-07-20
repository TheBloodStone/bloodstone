# Bloodstone Coordinator — Bond Escrow 2-of-3 Multisig Ceremony

**Document version:** 1.0 · July 2026  
**Status:** Plan generated — **not activated** for live deposits  
**Public plan:** https://bloodstonewallet.mytunnel.org/downloads/coordinator-bond-multisig-plan.json  
**Private redeem data:** `/root/.bloodstone/federation/bond-multisig-2of3.json` (ops only)  

---

## 1. Goal

Move `COORD_BOND_ESCROW_v1` from a single-wallet address to a **2-of-3** multisig so no single host compromise can unilaterally spend bonds.

---

## 2. Current state

| Item | Value |
|------|--------|
| Live escrow (active) | `SkUB1JZcJHWMBp78zVwZiMftGP6jN1SY2t` |
| Pending multisig address | See plan JSON `address` field (`sXvTS1Uu…` at generation) |
| Status | `generated_not_activated` |
| Keys | Three key-holder addresses in plan JSON; redeemScript held privately |

**Do not send production bonds to the multisig until ceremony complete and fee schedule updated.**

---

## 3. Ceremony steps

1. **Three key holders** identified (e.g. ops primary, ops secondary, offline cold).  
2. Each holder confirms control of one `key_addresses[]` entry (message sign or receive dust).  
3. Export / backup `redeemScript` to offline encrypted storage (3 copies).  
4. Publish updated fee schedule with:
   - `COORD_BOND_ESCROW_v1` = multisig address  
   - `previous_escrow` = old address (grace for in-flight txs)  
5. Bump `fee_schedule_version` if amounts/addresses change policy.  
6. `python3 /root/bloodstone_coordinator_federation.py publish`  
7. Announce 7-day grace on old escrow.  
8. Slash / refund spends require **2 signatures**.

---

## 4. Rollback

Keep old escrow funded until grace ends. If multisig import fails, revert fee schedule address field and re-publish.

---

## 5. Document history

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-07-11 | Ceremony written; address pre-generated |

---

*Bloodstone LLC · Bond multisig ceremony*

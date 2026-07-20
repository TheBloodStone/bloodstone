# Bloodstone Coordinator — G6 Readiness Checklist

**Document version:** 1.0 · July 2026  
**Public copy:** https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Coordinator-G6-Readiness-Checklist.md  
**Machine JSON:** https://bloodstonewallet.mytunnel.org/downloads/g6-readiness-checklist.json  

```bash
python3 /root/bloodstone_coordinator_federation.py g6-checklist
```

## Rule

**Do not** set `COORD_FEDERATION_OPEN_JOIN=1` or close G6 until:

1. Core checklist items are green (especially **second operator** and **multisig activated**), **and**  
2. Board/ops explicitly decides to open paid join.

Live open join is **off** even if G0–G5 are closed.

## Core items

| ID | Meaning |
|----|---------|
| G0–G5 | Prior gates closed |
| federation_v1 | G1+G2+G4 |
| multi_home | A+B status |
| roster_runbook | paid→include / lapsed→omit |
| payment_addresses | sub+bond live |
| invite_path | second-operator invite CLI |
| **o_min_multi_operator** | **≥2 distinct operator_id active** |
| **multisig_bond_activated** | escrow switched to 2-of-3 after ceremony |
| drills | T5/T8/T9/T10/T11 artifacts |
| open_join_env | intentional last step |

## Related

- [Second operator onboarding](Bloodstone-Coordinator-Second-Operator-Onboarding.md)  
- [Bond multisig ceremony](Bloodstone-Coordinator-Bond-Multisig-Ceremony.md)  
- [Fee plan](Bloodstone-Coordinator-Federation-Remediation-And-Membership-Fee.md)  

---

*Bloodstone LLC · G6 readiness*

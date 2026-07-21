# LRGK public peer (ops host)

**Document version:** 1.0  
**Date:** 2026-07-19  
**Status:** Live public P2P seed

---

## Endpoint

| Field | Value |
|-------|--------|
| **Host** | `64.188.22.190` |
| **P2P port** | **33685** (TCP) |
| **addnode** | `64.188.22.190:33685` |
| **RPC** | **Not public** (localhost only on the seed) |
| **Network** | LRGK main (magic `cab95753`) — **not** Bloodstone |

Same machine also runs Bloodstone services on **different** ports. LRGK uses its own magic, datadir, and P2P port so the networks never mix.

---

## Connect (Linux)

```bash
# In ~/.lrgk/lrgk.conf (or your datadir conf):
listen=1
port=33685
dnsseed=0
addnode=64.188.22.190:33685
# RPC stays private:
rpcbind=127.0.0.1
rpcallowip=127.0.0.1
```

Then:

```bash
lrgkd -datadir=$HOME/.lrgk -conf=$HOME/.lrgk/lrgk.conf
lrgk-cli -datadir=$HOME/.lrgk getconnectioncount
lrgk-cli -datadir=$HOME/.lrgk getpeerinfo
```

---

## Connect (Android APK)

- **v1.0.24+** ships `addnode=64.188.22.190:33685` automatically.
- Older builds: full-node only on-device (solo) unless you add the seed manually via conf if supported.

Download: [lrgk-full-node-android-latest.apk](https://bloodstonewallet.mytunnel.org/downloads/lrgk-full-node-android-latest.apk)

---

## Ops (this VPS)

| Item | Path / unit |
|------|-------------|
| Binary | `/root/lrgk-chain/bin/lrgkd` |
| Datadir | `/root/lrgk-chain/bootstrap-source` |
| Conf | `/root/lrgk-chain/bootstrap-source/lrgk.conf` |
| Systemd | `lrgkd.service` (`systemctl status lrgkd`) |
| P2P listen | `0.0.0.0:33685` |
| RPC | `127.0.0.1:53685` |

```bash
systemctl status lrgkd
/root/lrgk-chain/bin/lrgk-cli -datadir=/root/lrgk-chain/bootstrap-source \
  -conf=/root/lrgk-chain/bootstrap-source/lrgk.conf getnetworkinfo
```

---

## Machine-readable

[lrgk-public-peers.json](lrgk-public-peers.json)

---

*LRGK · Public peer v1.0 · 2026-07-19*

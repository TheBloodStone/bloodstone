# Bloodstone Multi-Fork Qt Wallet 0.2.11

**Released:** 2026-07-29

## Fix: AZURE / STONE wallets disconnect after startup (daemon “fails to load”)

### What was going wrong
On many Windows PCs the local node starts on a **fallback RPC port** (Hyper-V excludes e.g. AZURE `49825`). Status shows **connected**, then a later `ensure_conf` / auto-start path rewrote conf back to the **catalog default port** while the process still listened on the fallback port.

Symptoms:

- Connected at first, then wallet RPCs fail  
- Soft auto-restart tries to start a **second** `azured`/`bloodstoned` against a locked datadir → “daemon fails to load” / exit immediately  
- Settings still show the wrong `rpc :PORT`

### Fix in 0.2.11
1. **Reattach, don’t rewrite** when a daemon is already running (`reattach_running`).  
2. **Preserve** existing `rpcport` / `port` / credentials in datadir conf (never reset Hyper-V fallback ports to catalog defaults).  
3. **RPC probe** tries conf port + override + candidate ports and heals Settings when the live port is found.  
4. If a start hits **datadir lock** / port already serving our credentials → reattach instead of crash.  
5. Soft auto-restart **reattaches first** before spawning another process.

### After upgrade
1. Install **0.2.11**.  
2. If a stuck daemon remains: Task Manager → end `azured.exe` / `bloodstoned.exe` once, or use **Stop daemon**.  
3. Select STONE / AZURE → **Download & start daemon**.  
4. Confirm status stays `running` with a stable `rpc :PORT` after several minutes and after switching coins.  
5. Create / select wallet again — `loadwallet` should succeed while RPC is online.

### Downloads
- https://bloodstone.rocks/downloads/bloodstone-multi-fork-qt-0.2.11-win64-setup.exe  
- https://bloodstone.rocks/downloads/bloodstone-multi-fork-qt-0.2.11-win64-portable.zip  
- https://bloodstone.rocks/downloads/bloodstone-multi-fork-qt-0.2.11-win64.exe  
- https://bloodstone.rocks/downloads/bloodstone-multi-fork-qt-0.2.11.tar.gz  
- https://bloodstone.rocks/downloads/Bloodstone-Multi-Fork-Qt-Wallet-0.2.11-Release-Notes.md  

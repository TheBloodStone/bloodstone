Bloodstone Multi-Fork Qt Wallet — Windows
=========================================

Coins: STONE + AZURE + LRGK + any live Fork Lab child.

Local daemons (download on select)
----------------------------------
Each coin can run its own local node process:

1. Select a coin in the left list
2. With “Auto-start on select: ON” the wallet will:
   - download the active Windows daemon pack for that fork (if not bundled)
   - write a private datadir + rpc conf
   - start the daemon and wire the wallet RPC to it
3. Or click “Download & start daemon” / Node menu

Bundled packs ship under daemons\STONE, daemons\AZURE, daemons\LRGK.
Online packs: https://bloodstone.rocks/downloads/mfq-daemons/

Data / conf locations
---------------------
  %LOCALAPPDATA%\Bloodstone\MultiForkQt\daemons\   installed binaries
  %LOCALAPPDATA%\Bloodstone\MultiForkQt\datadirs\  chain data per ticker
  %LOCALAPPDATA%\Bloodstone\MultiForkQt\rpc\       wallet RPC confs

Default local RPC ports
-----------------------
  STONE  18332
  AZURE  49825
  LRGK   53685

Public seeds (P2P) — all written as addnode= (show as "manual" in getpeerinfo)
------------------
  STONE  64.188.22.190:17333
         192.119.82.145:17333
  AZURE  64.188.22.190:29825
  LRGK   64.188.22.190:33685

Support: https://bloodstone.rocks/downloads/

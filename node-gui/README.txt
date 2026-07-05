Bloodstone Wallet & Node GUI v0.7.0
=====================================

Desktop app for Windows that combines:
  - Full Bloodstone node (same GUI as Bloodstone Node)
  - Web-wallet sign-in (same username/password)
  - Send, receive, unlock, transaction history
  - JSON-RPC console

Requirements
------------
- Windows 10/11 x64
- Node.js 18+ LTS (build only)

Quick start (end users)
-----------------------
1. Install bloodstone-wallet-node-gui-0.7.0-win64.exe
2. Open Settings → click "Use VPS" (for accounts created on the web wallet)
3. Wallet tab → sign in with your web wallet username/password
4. Unlock with your wallet encryption passphrase before sending

Sign-in options
---------------
- Default: wallet web URL https://bloodstonewallet.mytunnel.org/wallet
- Optional: point Settings → users.db to a local copy of the server database

Build on Windows
----------------
  cd bloodstone-wallet-node-gui
  npm install
  npm run dist

Build on Linux (cross-compile)
------------------------------
  bash /root/build-bloodstone-wallet-node-gui-windows.sh

Outputs in dist/:
  bloodstone-wallet-node-gui-0.7.0-win64.exe
  bloodstone-wallet-node-gui-0.7.0-win64-portable.exe

Network defaults
----------------
  P2P: 17333
  RPC: 18332
  Seed: 64.188.22.190:17333
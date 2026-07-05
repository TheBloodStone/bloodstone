Bloodstone Miner — Android (Capacitor) v1.3.2
==============================================

Installable Android app with native stratum TCP, optional on-device full node,
pruned/mesh federation modes, device-pool coordination, and chain-mesh backup sync.

Requirements
------------
  - Node.js 18+
  - Android Studio (SDK 34+, JDK 17)
  - npm install

Build APK
---------
  npm install
  npx cap add android
  npx cap sync android

  Copy cleartext network config (stratum is plain TCP):
    mkdir -p android/app/src/main/res/xml
    cp android-res/network_security_config.xml android/app/src/main/res/xml/
  Edit android/app/src/main/AndroidManifest.xml — set on <application>:
    android:usesCleartextTraffic="true"

  npx cap open android
  # Build → Build APK

  Or from CLI:
    cd android && ./gradlew assembleRelease

Local node modes (Android)
--------------------------
  pruned — ~550 MiB tip node (default)
  full   — entire blockchain on device; peers on :17333 (no wallet)
  mesh   — pruned tip + up to 256 chain-mesh chunks (~64 MiB backups)

Capacitor plugins
-----------------
  plugins/bloodstone-stratum      — native stratum TCP
  plugins/bloodstone-device-pool  — decentralized VPS device pool
  plugins/bloodstone-chain-mesh   — LAN chain-mesh backup sync
  plugins/bloodstone-local-node   — bloodstoned on device (pruned/full/mesh)

The WebView loads /mining/mine?app=android from your portal.
Capacitor plugins are detected automatically by the miner UI.

Publish
-------
  Upload signed APK to /var/www/bloodstone/downloads/ or distribute via portal.
  Users enable "Install unknown apps" for sideload.

iOS
---
  Safari PWA only (no native stratum TCP in App Store policy). Use Add to Home Screen.
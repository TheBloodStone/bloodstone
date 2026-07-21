# LRGK wallet balance UI fix (1.0.29)

## Bug
Wallet showed **Current balance: —** and “enter address above” with no address field in that panel. Valid **L…** addresses were ignored (code still required Bloodstone **S…**). Balance fetched Bloodstone ElectrumX, not LRGK.

## Fix
- Accept LRGK **L…** addresses
- **Balance / mining address** field on the wallet panel
- API: `https://bloodstonewallet.mytunnel.org/mining/api/lrgk/wallet/balance`
- APK **1.0.29** (`versionCode` 10029)

## Install
- https://bloodstonewallet.mytunnel.org/downloads/lrgk-full-node-android-1.0.29.apk
- https://bloodstonewallet.mytunnel.org/downloads/lrgk-full-node-android-latest.apk

Paste your **L…** address in the new field (or create a phone wallet), then **Refresh**.

# Bloodstone

Open-source snapshot of the Bloodstone network stack: chain core, mining pool services, Android fleet miner, web mining UI, portal, and supporting tooling.

This monorepo reflects the project layout as deployed in July 2026. Component trees were upstream forks or greenfield apps; they are vendored here as a single reproducible source tree.

## Repository layout

| Path | Description |
|------|-------------|
| `core/` | Bloodstone node (`bloodstoned`, `bloodstone-cli`) — fork of SpaceXpanse ROD / Bitcoin Core lineage |
| `chain/` | Chain mesh federation, block backup, and P2P asset distribution |
| `miner-android/` | Capacitor Android app — local full/pruned node, LAN stratum, fleet mining, OTA web UI |
| `miner-web/` | Flask mining API, pool dashboards, stratum bridge, Android OTA manifest |
| `portal/` | Public Bloodstone portal (downloads, docs links, wallet entry) |
| `node-gui/` | Desktop node manager GUI (Electron) |
| `wallet-node-gui/` | Desktop wallet + node GUI (Electron) |
| `explorer/` | Block explorer web app |
| `faucet/` | Testnet/mainnet faucet service |
| `dex/` | DEX UI / integration |
| `support/` | Support site |
| `electrumx/` | Electrum protocol server for lightweight wallets |
| `docs/` | White papers, FAQ generators, network documentation sources |
| `ops/` | VPS scripts — stratum workers, watchdogs, APK/web publish, downloads metadata |
| `downloads/` | Downloads page template |

## Quick start

### Chain node (Linux)

```bash
cd core
./autogen.sh
./configure --without-gui --disable-tests
make -j"$(nproc)"
src/bloodstoned -daemon   # or spacexpansed, depending on build branding
```

See `core/doc/` and `core/INSTALL.md` for platform-specific build notes.

### Mining API (developer)

```bash
cd miner-web
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp secrets.conf.example secrets.conf   # edit locally
export BLOODSTONE_CONF=~/.bloodstone/bloodstone.conf
flask run   # or gunicorn per systemd unit in production
```

### Android miner APK

```bash
# Requires Android SDK, Java 17, signing keystore (not included)
BLOODSTONE_MINER_ANDROID_VERSION=1.3.44 ./ops/build-bloodstone-miner-android-apk.sh
```

Bundled `bloodstoned` ARM binaries live under `miner-android/plugins/bloodstone-local-node/android/src/main/assets/`.

### Web UI OTA (no APK rebuild)

```bash
BLOODSTONE_MINER_ANDROID_WEB_VERSION=1.3.65-web ./ops/publish-android-miner-web-bundle.sh
```

Phones with APK ≥ 1.3.17 download the zip from `/downloads/bloodstone-miner-android-web-latest.zip`.

## Security & secrets

**Do not commit:**

- `secrets.conf`, `service-overrides.conf`, `.env`
- Android keystores (`*.keystore`, `keystore.properties`)
- `~/.bloodstone/` RPC passwords or wallet datadirs
- SSH keys used for download worker sync

Example templates ship as `*.example` files.

## License

- `core/` — MIT (see `core/COPYING`, Bitcoin Core lineage)
- Other components — check per-directory `LICENSE` / `package.json`; default intent is MIT-compatible OSS unless noted

## Related GitHub org

Historical component repos have lived under [TheBloodStone](https://github.com/TheBloodStone) (e.g. BloodstoneChain). This monorepo supersedes scattered VPS copies for transparency and onboarding.

## Regenerating this snapshot

On the maintainer VPS:

```bash
./prepare-bloodstone-oss-repo.sh
cd bloodstone-repo && git add -A && git commit -m "Sync snapshot"
```
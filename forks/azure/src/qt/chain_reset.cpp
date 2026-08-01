// Copyright (c) 2026 The Bloodstone developers
// SPDX-License-Identifier: MIT

#include <qt/chain_reset.h>

#include <fs.h>
#include <logging.h>
#include <util/system.h>

#include <boost/system/error_code.hpp>
#include <cstring>

#include <qt/guiutil.h>

#include <QDir>
#include <QMessageBox>
#include <QSettings>
#include <QString>
#include <QWidget>

#include <algorithm>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace ChainReset {

namespace {

bool RemovePath(const fs::path& path, QString& error_out)
{
    boost::system::error_code ec;
    if (!fs::exists(path)) {
        return true;
    }
    fs::remove_all(path, ec);
    if (ec) {
        error_out = QString::fromStdString(ec.message());
        return false;
    }
    return true;
}

} // namespace

bool HasChainData(const fs::path& datadir)
{
    return fs::exists(datadir / "blocks") || fs::exists(datadir / "chainstate");
}

bool HasCorruptChainLog(const fs::path& datadir)
{
    const fs::path log = datadir / "debug.log";
    if (!fs::exists(log)) {
        return false;
    }
    try {
        std::ifstream input(log, std::ios::ate | std::ios::binary);
        if (!input) {
            return false;
        }
        input.seekg(0, std::ios::end);
        const std::streamoff size = static_cast<std::streamoff>(input.tellg());
        const std::streamoff tail_bytes = 65536;
        const std::streamoff start = size > tail_bytes ? size - tail_bytes : 0;
        input.seekg(start, std::ios::beg);
        std::string chunk((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
        return chunk.find("bad-txnmrklroot") != std::string::npos
            || chunk.find("hashMerkleRoot mismatch") != std::string::npos
            || chunk.find("A fatal internal error occurred") != std::string::npos;
    } catch (...) {
        return false;
    }
}

bool HasRelaunchMarker(const fs::path& datadir)
{
    const fs::path marker = datadir / RELAUNCH_MARKER;
    if (!fs::exists(marker)) {
        return false;
    }
    try {
        FILE* fp = fsbridge::fopen(marker, "rb");
        if (!fp) {
            return false;
        }
        char buf[128] = {0};
        const size_t n = fread(buf, 1, sizeof(buf) - 1, fp);
        fclose(fp);
        if (n == 0) {
            return false;
        }
        std::string text(buf, n);
        return text.find(EXPECTED_GENESIS_HEX) != std::string::npos;
    } catch (...) {
        return false;
    }
}

void WriteRelaunchMarker(const fs::path& datadir)
{
    const fs::path marker = datadir / RELAUNCH_MARKER;
    try {
        FILE* fp = fsbridge::fopen(marker, "wb");
        if (!fp) {
            return;
        }
        const std::string line = std::string(EXPECTED_GENESIS_HEX) + "\n";
        fwrite(line.data(), 1, line.size(), fp);
        fclose(fp);
    } catch (...) {
        LogPrintf("Could not write relaunch marker at %s\n", marker.string());
    }
}

bool WipeChainData(const fs::path& datadir, QString& error_out)
{
    static const char* const kDirs[] = {"blocks", "chainstate", "indexes"};
    static const char* const kFiles[] = {
        "mempool.dat", "fee_estimates.dat", ".lock", "bloodstoned.pid", "debug.log",
        // Also drop peer caches so a chain reset cannot re-stick on dead peers.
        "peers.dat", "peers.dat.bak", "banlist.dat", "banlist.json", "anchors.dat",
    };

    for (const char* dir : kDirs) {
        if (!RemovePath(datadir / dir, error_out)) {
            return false;
        }
    }
    for (const char* file : kFiles) {
        if (!RemovePath(datadir / file, error_out)) {
            return false;
        }
    }
    return true;
}

bool LooksLikeServerOnlyPath(const QString& path)
{
    if (path.isEmpty()) {
        return false;
    }
    const QString native = QDir::toNativeSeparators(path.trimmed());
    return native.startsWith("/root/", Qt::CaseInsensitive)
        || native.contains("/root/bloodstone", Qt::CaseInsensitive)
        || native.contains("\\root\\bloodstone", Qt::CaseInsensitive);
}

namespace {

std::string TrimAscii(const std::string& text)
{
    const auto start = text.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) {
        return {};
    }
    const auto end = text.find_last_not_of(" \t\r\n");
    return text.substr(start, end - start + 1);
}

bool ConfigLineSetsBadDataDir(const std::string& line)
{
    const std::string trimmed = TrimAscii(line);
    if (trimmed.empty() || trimmed[0] == '#') {
        return false;
    }
    const auto eq = trimmed.find('=');
    if (eq == std::string::npos) {
        return false;
    }
    const std::string key = TrimAscii(trimmed.substr(0, eq));
    if (key != "datadir") {
        return false;
    }
    const std::string value = TrimAscii(trimmed.substr(eq + 1));
    return LooksLikeServerOnlyPath(QString::fromStdString(value));
}

bool StripBadDataDirFromConfig(const fs::path& conf_path)
{
    if (!fs::exists(conf_path)) {
        return false;
    }
    std::ifstream input(conf_path);
    if (!input) {
        return false;
    }

    std::vector<std::string> kept;
    std::string line;
    bool modified = false;
    while (std::getline(input, line)) {
        if (ConfigLineSetsBadDataDir(line)) {
            modified = true;
            continue;
        }
        kept.push_back(line);
    }
    input.close();
    if (!modified) {
        return false;
    }

    std::ofstream output(conf_path, std::ios::trunc);
    if (!output) {
        return false;
    }
    for (size_t i = 0; i < kept.size(); ++i) {
        output << kept[i];
        if (i + 1 < kept.size()) {
            output << '\n';
        }
    }
    if (!kept.empty() && kept.back().empty()) {
        output << '\n';
    }
    LogPrintf("Removed unusable datadir= line from %s\n", conf_path.string());
    return true;
}

} // namespace

QString ResolveUsableDataDirectory(const QString& preferred, const QString& current_default)
{
    if (LooksLikeServerOnlyPath(preferred)) {
        return current_default;
    }
    if (!preferred.isEmpty()) {
        const fs::path path = GUIUtil::qstringToBoostPath(preferred);
        if (fs::exists(path) && fs::is_directory(path)) {
            return preferred;
        }
        try {
            if (TryCreateDirectories(path)) {
                TryCreateDirectories(path / "wallets");
                return preferred;
            }
        } catch (...) {
        }
    }
    return current_default;
}

QString MigrateLegacySettingsPath(const QString& current_default)
{
    QSettings settings;
    const QString stored = settings.value("strDataDir").toString();
    if (!stored.isEmpty()) {
        return stored;
    }

    QSettings legacy("Bloodstone", "Bloodstone-Qt");
    QString legacy_dir = legacy.value("strDataDir").toString();
    if (legacy_dir.isEmpty()) {
        QSettings spacexpanse("SpaceXpanse", "SpaceXpanse-Qt");
        legacy_dir = spacexpanse.value("strDataDir").toString();
    }
    if (legacy_dir.isEmpty()) {
        return current_default;
    }

    QString migrated = legacy_dir;
    if (legacy_dir.contains("Bloodstone", Qt::CaseInsensitive)
        || legacy_dir.contains("SpaceXpanse", Qt::CaseInsensitive)) {
        migrated = current_default;
    }
    settings.setValue("strDataDir", migrated);
    return migrated;
}

namespace {

/** Official seed endpoints — always addnode=, NEVER exclusive connect=. */
constexpr const char* kSeedEndpoints[] = {
    "64.188.22.190:17333",
    "192.119.82.145:17333",
};

bool LineKeyEquals(const std::string& line, const char* key)
{
    const std::string trimmed = TrimAscii(line);
    if (trimmed.empty() || trimmed[0] == '#') {
        return false;
    }
    const auto eq = trimmed.find('=');
    if (eq == std::string::npos) {
        return false;
    }
    return TrimAscii(trimmed.substr(0, eq)) == key;
}

bool LineIsExclusiveConnect(const std::string& line)
{
    // Exclusive -connect disables dnsseed + listen + automatic outbound peers.
    // That is the #1 reason Windows Qt wallets show 0 peers / never sync.
    return LineKeyEquals(line, "connect");
}

bool LineIsSeedAddnode(const std::string& line, const char* endpoint)
{
    const std::string trimmed = TrimAscii(line);
    if (trimmed.empty() || trimmed[0] == '#') {
        return false;
    }
    const auto eq = trimmed.find('=');
    if (eq == std::string::npos) {
        return false;
    }
    if (TrimAscii(trimmed.substr(0, eq)) != "addnode") {
        return false;
    }
    return TrimAscii(trimmed.substr(eq + 1)) == endpoint;
}

bool ConfigHasKey(const std::vector<std::string>& lines, const char* key)
{
    for (const auto& line : lines) {
        if (LineKeyEquals(line, key)) {
            return true;
        }
    }
    return false;
}

bool ConfigHasSeedAddnode(const std::vector<std::string>& lines, const char* endpoint)
{
    for (const auto& line : lines) {
        if (LineIsSeedAddnode(line, endpoint)) {
            return true;
        }
    }
    return false;
}

void ClearStalePeerCache(const fs::path& datadir)
{
    // After leaving exclusive-connect mode, peers.dat often only has the old
    // forced peers and can keep the node stuck. Drop caches; seeds repopulate.
    static const char* const kPeerFiles[] = {
        "peers.dat", "peers.dat.bak", "banlist.dat", "banlist.json", "anchors.dat",
    };
    for (const char* name : kPeerFiles) {
        QString err;
        RemovePath(datadir / name, err);
    }
    LogPrintf("Cleared stale peer/ban cache under %s after removing exclusive connect=\n",
              datadir.string());
}

std::string BuildDefaultConfBody()
{
    std::ostringstream body;
    body << "# Bloodstone Core — auto-created by bloodstone-qt\n"
            "# Do NOT use exclusive connect= (it disables peer discovery).\n"
            "server=1\n"
            "listen=1\n"
            "dnsseed=1\n"
            "discover=1\n"
            "upnp=1\n"
            "port=17333\n"
            "rpcport=18332\n"
            "rpcbind=127.0.0.1\n"
            "rpcallowip=127.0.0.1\n"
            "maxconnections=64\n"
            "txindex=1\n";
    for (const char* endpoint : kSeedEndpoints) {
        body << "addnode=" << endpoint << "\n";
    }
    return body.str();
}

} // namespace

bool EnsureDefaultNodeConfig(const fs::path& datadir)
{
    const fs::path conf_path = datadir / BITCOIN_CONF_FILENAME;
    bool stripped_connect = false;
    bool modified = false;

    try {
        if (!fs::exists(conf_path)) {
            const std::string body = BuildDefaultConfBody();
            FILE* fp = fsbridge::fopen(conf_path, "wb");
            if (fp) {
                fwrite(body.data(), 1, body.size(), fp);
                fclose(fp);
                LogPrintf("Created default %s with Bloodstone seed addnodes (no exclusive connect=)\n",
                          conf_path.string());
                return true;
            }
            return false;
        }

        std::ifstream input(conf_path);
        if (!input) {
            return false;
        }
        std::vector<std::string> lines;
        std::string line;
        while (std::getline(input, line)) {
            if (LineIsExclusiveConnect(line)) {
                stripped_connect = true;
                modified = true;
                continue;
            }
            if (ConfigLineSetsBadDataDir(line)) {
                modified = true;
                continue;
            }
            lines.push_back(line);
        }
        input.close();

        auto ensure_kv = [&](const char* key, const char* full_line) {
            if (!ConfigHasKey(lines, key)) {
                lines.emplace_back(full_line);
                modified = true;
            }
        };
        ensure_kv("server", "server=1");
        ensure_kv("listen", "listen=1");
        ensure_kv("dnsseed", "dnsseed=1");
        ensure_kv("discover", "discover=1");
        ensure_kv("port", "port=17333");
        ensure_kv("rpcport", "rpcport=18332");
        ensure_kv("maxconnections", "maxconnections=64");

        for (const char* endpoint : kSeedEndpoints) {
            if (!ConfigHasSeedAddnode(lines, endpoint)) {
                lines.emplace_back(std::string("addnode=") + endpoint);
                modified = true;
            }
        }

        if (!modified) {
            return false;
        }

        std::ofstream output(conf_path, std::ios::trunc);
        if (!output) {
            return false;
        }
        for (size_t i = 0; i < lines.size(); ++i) {
            output << lines[i];
            if (i + 1 < lines.size() || !lines[i].empty()) {
                output << '\n';
            }
        }
        if (stripped_connect) {
            LogPrintf("Rewrote %s: removed exclusive connect= and ensured seed addnodes\n",
                      conf_path.string());
            ClearStalePeerCache(datadir);
        } else {
            LogPrintf("Updated %s with Bloodstone seed addnodes / safe defaults\n",
                      conf_path.string());
        }
        return true;
    } catch (...) {
        LogPrintf("Could not ensure node config at %s\n", conf_path.string());
        return false;
    }
}

void ApplyRuntimePeerDefaults()
{
    // Drop exclusive connect= from the in-memory config (command-line -connect still wins
    // if the user intentionally set it, via command_line_options).
    gArgs.LockSettings([](util::Settings& settings) {
        for (auto& section : settings.ro_config) {
            section.second.erase("connect");
        }
    });

    // Prefer open peer discovery unless the user already chose otherwise.
    gArgs.SoftSetBoolArg("-dnsseed", true);
    gArgs.SoftSetBoolArg("-listen", true);
    gArgs.SoftSetBoolArg("-discover", true);
    gArgs.SoftSetBoolArg("-upnp", true);
    gArgs.SoftSetArg("-maxconnections", "64");

    // Inject seed addnodes into ro_config (multi-value; do not ForceSetArg single value).
    gArgs.LockSettings([](util::Settings& settings) {
        auto& main_section = settings.ro_config[""];
        auto& addnodes = main_section["addnode"];
        for (const char* endpoint : kSeedEndpoints) {
            bool found = false;
            for (const auto& v : addnodes) {
                if (v.isStr() && v.get_str() == endpoint) {
                    found = true;
                    break;
                }
            }
            if (!found) {
                addnodes.emplace_back(endpoint);
            }
        }
    });
}

void SanitizeAfterConfigRead(const fs::path& config_home, const QString& default_datadir)
{
    StripBadDataDirFromConfig(config_home / BITCOIN_CONF_FILENAME);

    const QString current = QString::fromStdString(gArgs.GetArg("-datadir", ""));
    const QString resolved = ResolveUsableDataDirectory(current, default_datadir);
    if (resolved == current) {
        return;
    }

    LogPrintf(
        "Ignoring unusable datadir \"%s\" from configuration; using \"%s\" instead.\n",
        current.toStdString(),
        resolved.toStdString());
    gArgs.ForceSetArg("-datadir", GUIUtil::qstringToBoostPath(resolved).string());
    gArgs.ClearPathCache();
}

bool EnsureRelaunchChainOrAbort(const fs::path& datadir, QWidget* parent)
{
    EnsureDefaultNodeConfig(datadir);
    ApplyRuntimePeerDefaults();

    if (!HasChainData(datadir) || HasRelaunchMarker(datadir)) {
        return true;
    }

    if (HasCorruptChainLog(datadir)) {
        LogPrintf(
            "Detected corrupt Bloodstone chain log in %s — wiping blocks/chainstate\n",
            datadir.string());
        QString error;
        if (!WipeChainData(datadir, error)) {
            if (parent) {
                QMessageBox::critical(
                    parent,
                    QObject::tr("Could not reset chain data"),
                    QObject::tr("Failed to remove corrupt chain data:\n%1").arg(error));
            }
            return false;
        }
        return true;
    }

    const QString dir = QString::fromStdString(datadir.string());
    const auto answer = QMessageBox::question(
        parent,
        QObject::tr("Reset chain data for Bloodstone relaunch?"),
        QObject::tr(
            "This data folder contains blockchain data from before the June 2026 "
            "Bloodstone relaunch (or an old Bloodstone path).\n\n"
            "Folder: %1\n\n"
            "Remove blocks and chainstate so the wallet can sync again?\n"
            "Your wallet files in this folder are kept.")
            .arg(dir),
        QMessageBox::Yes | QMessageBox::No,
        QMessageBox::Yes);

    if (answer != QMessageBox::Yes) {
        return false;
    }

    QString error;
    if (!WipeChainData(datadir, error)) {
        QMessageBox::critical(
            parent,
            QObject::tr("Could not reset chain data"),
            QObject::tr("Failed to remove old chain data:\n%1").arg(error));
        return false;
    }
    return true;
}

} // namespace ChainReset
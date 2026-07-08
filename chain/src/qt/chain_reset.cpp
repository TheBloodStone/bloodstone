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
        "mempool.dat", "fee_estimates.dat", ".lock", "bloodstoned.pid", "debug.log"};

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

void EnsureDefaultNodeConfig(const fs::path& datadir)
{
    const fs::path conf_path = datadir / BITCOIN_CONF_FILENAME;
    static const char* const kSeedLines[] = {
        "connect=64.188.22.190:17333",
        "connect=192.119.82.145:17333",
        "addnode=64.188.22.190:17333",
        "addnode=192.119.82.145:17333",
    };

    try {
        if (!fs::exists(conf_path)) {
            const std::string body =
                "# Bloodstone Core — auto-created by bloodstone-qt\n"
                "server=1\n"
                "listen=1\n"
                "port=17333\n"
                "rpcport=18332\n"
                "rpcbind=127.0.0.1\n"
                "rpcallowip=127.0.0.1\n"
                "maxconnections=32\n"
                "connect=64.188.22.190:17333\n"
                "connect=192.119.82.145:17333\n"
                "addnode=64.188.22.190:17333\n"
                "addnode=192.119.82.145:17333\n";
            FILE* fp = fsbridge::fopen(conf_path, "wb");
            if (fp) {
                fwrite(body.data(), 1, body.size(), fp);
                fclose(fp);
                LogPrintf("Created default %s with Bloodstone seed peers\n", conf_path.string());
            }
            return;
        }

        std::ifstream input(conf_path);
        if (!input) {
            return;
        }
        std::string existing;
        std::string line;
        while (std::getline(input, line)) {
            existing += line;
            existing += '\n';
        }
        input.close();

        std::string patched = existing;
        bool modified = false;
        for (const char* seed : kSeedLines) {
            if (existing.find(seed) != std::string::npos) {
                continue;
            }
            if (!patched.empty() && patched.back() != '\n') {
                patched += '\n';
            }
            patched += seed;
            patched += '\n';
            modified = true;
        }
        if (!modified) {
            return;
        }
        std::ofstream output(conf_path, std::ios::trunc);
        if (output) {
            output << patched;
            LogPrintf("Appended Bloodstone seed peers to %s\n", conf_path.string());
        }
    } catch (...) {
        LogPrintf("Could not ensure node config at %s\n", conf_path.string());
    }
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

    if (!HasChainData(datadir) || HasRelaunchMarker(datadir)) {
        return true;
    }

    const bool corrupt = HasCorruptChainLog(datadir);
    LogPrintf(
        "%s Bloodstone chain data in %s without relaunch marker — wiping blocks/chainstate (wallets kept)\n",
        corrupt ? "Corrupt" : "Stale pre-relaunch",
        datadir.string());

    QString error;
    if (!WipeChainData(datadir, error)) {
        if (parent) {
            QMessageBox::critical(
                parent,
                QObject::tr("Could not reset chain data"),
                QObject::tr("Failed to remove old chain data:\n%1").arg(error));
        }
        return false;
    }

    if (parent) {
        const QString dir = QString::fromStdString(datadir.string());
        QMessageBox::information(
            parent,
            QObject::tr("Chain data reset for Bloodstone relaunch"),
            QObject::tr(
                "Removed old blockchain data so this wallet can sync the June 2026 "
                "Bloodstone mainnet.\n\n"
                "Folder: %1\n\n"
                "Your wallet files were kept. Sync will start from the genesis block.")
                .arg(dir));
    }
    return true;
}

} // namespace ChainReset
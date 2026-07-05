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
    const QString native = QDir::toNativeSeparators(path);
    return native.startsWith("/root/", Qt::CaseInsensitive)
        || native.contains("/root/bloodstone", Qt::CaseInsensitive)
        || native.contains("\\root\\bloodstone", Qt::CaseInsensitive);
}

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
    QSettings legacy("SpaceXpanse", "SpaceXpanse-Qt");
    const QString legacy_dir = legacy.value("strDataDir").toString();
    if (legacy_dir.isEmpty()) {
        return current_default;
    }

    QSettings settings;
    const QString stored = settings.value("strDataDir").toString();
    if (!stored.isEmpty()) {
        return stored;
    }

    QString migrated = legacy_dir;
    if (legacy_dir.contains("SpaceXpanse", Qt::CaseInsensitive)) {
        migrated = current_default;
    }
    settings.setValue("strDataDir", migrated);
    return migrated;
}

bool EnsureRelaunchChainOrAbort(const fs::path& datadir, QWidget* parent)
{
    if (!HasChainData(datadir) || HasRelaunchMarker(datadir)) {
        return true;
    }

    const QString dir = QString::fromStdString(datadir.string());
    const auto answer = QMessageBox::question(
        parent,
        QObject::tr("Reset chain data for Bloodstone relaunch?"),
        QObject::tr(
            "This data folder contains blockchain data from before the June 2026 "
            "Bloodstone relaunch (or an old SpaceXpanse path).\n\n"
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
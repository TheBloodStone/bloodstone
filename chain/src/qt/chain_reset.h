// Copyright (c) 2026 The Bloodstone developers
// SPDX-License-Identifier: MIT

#ifndef BITCOIN_QT_CHAIN_RESET_H
#define BITCOIN_QT_CHAIN_RESET_H

#include <fs.h>

#include <QString>

class QWidget;

namespace ChainReset {

/** Marker written after the relaunch genesis chain loads successfully. */
constexpr const char RELAUNCH_MARKER[] = ".bloodstone_relaunch_genesis";
constexpr const char EXPECTED_GENESIS_HEX[] =
    "df04225074039e630dad825b24818a695462bd19cd585131a0568f50e9bf71d0";

bool HasChainData(const fs::path& datadir);
bool HasRelaunchMarker(const fs::path& datadir);
void WriteRelaunchMarker(const fs::path& datadir);
bool WipeChainData(const fs::path& datadir, QString& error_out);

/** Create or patch bloodstone.conf with Bloodstone seed peers. */
void EnsureDefaultNodeConfig(const fs::path& datadir);

/** Read legacy Bloodstone-Qt QSettings and migrate strDataDir when needed. */
QString MigrateLegacySettingsPath(const QString& current_default);

/** Drop missing/VPS-only paths and return a local data directory that can be used. */
QString ResolveUsableDataDirectory(const QString& preferred, const QString& current_default);

/**
 * If pre-relaunch chain folders exist without a relaunch marker, offer to wipe
 * blocks/chainstate (wallets are kept). Returns false if the user cancels.
 */
bool EnsureRelaunchChainOrAbort(const fs::path& datadir, QWidget* parent);

/**
 * After bloodstone.conf is read, undo a bad datadir= override (e.g. copied from a
 * VPS path) and strip that line from the config file under config_home.
 */
void SanitizeAfterConfigRead(const fs::path& config_home, const QString& default_datadir);

} // namespace ChainReset

#endif // BITCOIN_QT_CHAIN_RESET_H
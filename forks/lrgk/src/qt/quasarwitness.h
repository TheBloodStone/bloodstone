// Copyright (c) 2026 The Bloodstone developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_QT_QUASARWITNESS_H
#define BITCOIN_QT_QUASARWITNESS_H

#include <QObject>
#include <QElapsedTimer>
#include <QString>

#include <cstdint>
#include <string>

class ClientModel;
class QNetworkAccessManager;
class QNetworkReply;
class QTimer;

/**
 * When the pure Qt wallet is left open with a synced node, periodically submit
 * QUASAR mesh witness capsules so this machine counts as a peer witness
 * (same role as idle Android / Electron desktop peers).
 *
 * Disable with -quasarwitness=0 or Settings QSettings key bQuasarWitness=false.
 * Endpoint override: -quasarwitnessurl=https://host/api/quasar/witness/submit
 */
class QuasarWitnessService : public QObject
{
    Q_OBJECT

public:
    static constexpr int DEFAULT_INTERVAL_MS = 120000;
    static constexpr int FIRST_DELAY_MS = 25000;
    static constexpr int SAME_TIP_MIN_MS = 600000;
    static constexpr int DEFAULT_IDLE_MS = 60000;

    explicit QuasarWitnessService(ClientModel* client_model, QObject* parent = nullptr);
    ~QuasarWitnessService() override;

    void start();
    void stop();

    /** Call when the user interacts with the GUI (mouse/key/focus). */
    void noteUserActivity();

    bool isEnabled() const;
    QString lastStatus() const { return m_last_status; }

public Q_SLOTS:
    void tick();

private Q_SLOTS:
    void onReplyFinished(QNetworkReply* reply);

private:
    ClientModel* m_client_model{nullptr};
    QTimer* m_timer{nullptr};
    QNetworkAccessManager* m_nam{nullptr};
    QElapsedTimer m_idle_since;
    QString m_last_tip;
    qint64 m_last_emit_ms{0};
    QString m_last_status;
    bool m_inflight{false};

    QString deviceId() const;
    QString submitUrl() const;
    bool shouldEmit(const QString& tip_hex, bool tip_changed) const;
};

#endif // BITCOIN_QT_QUASARWITNESS_H

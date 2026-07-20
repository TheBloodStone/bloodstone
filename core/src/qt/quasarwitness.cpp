// Copyright (c) 2026 The Bloodstone developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <qt/quasarwitness.h>

#include <qt/clientmodel.h>
#include <qt/guiutil.h>

#include <hash.h>
#include <interfaces/node.h>
#include <logging.h>
#include <uint256.h>
#include <univalue.h>
#include <util/system.h>

#include <QDateTime>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QSettings>
#include <QSysInfo>
#include <QTimer>
#include <QUrl>

namespace {
constexpr const char* CAPSULE_TYPE = "bloodstone/witness-capsule/v1";
constexpr const char* DEFAULT_SUBMIT_URL =
    "https://bloodstonewallet.mytunnel.org/api/quasar/witness/submit";

QString TipHex(const uint256& hash)
{
    return QString::fromStdString(hash.ToString());
}

QString IsoUtcNow()
{
    // Capsule schema uses Zulu timestamps without milliseconds.
    return QDateTime::currentDateTimeUtc().toString(QStringLiteral("yyyy-MM-ddTHH:mm:ssZ"));
}

std::string UniToString(const UniValue& v)
{
    if (v.isStr()) return v.get_str();
    if (v.isNum()) return v.getValStr();
    if (v.isBool()) return v.get_bool() ? "1" : "0";
    return v.write();
}
} // namespace

QuasarWitnessService::QuasarWitnessService(ClientModel* client_model, QObject* parent)
    : QObject(parent), m_client_model(client_model)
{
    m_idle_since.start();
    m_nam = new QNetworkAccessManager(this);
    connect(m_nam, &QNetworkAccessManager::finished, this, &QuasarWitnessService::onReplyFinished);

    m_timer = new QTimer(this);
    m_timer->setInterval(DEFAULT_INTERVAL_MS);
    connect(m_timer, &QTimer::timeout, this, &QuasarWitnessService::tick);
}

QuasarWitnessService::~QuasarWitnessService()
{
    stop();
}

void QuasarWitnessService::start()
{
    if (!isEnabled()) {
        m_last_status = QStringLiteral("disabled");
        LogPrintf("quasar-witness: service disabled\n");
        return;
    }
    if (m_timer->isActive()) {
        return;
    }
    // First attempt shortly after the GUI finishes loading.
    QTimer::singleShot(FIRST_DELAY_MS, this, &QuasarWitnessService::tick);
    m_timer->start();
    m_last_status = QStringLiteral("started");
    LogPrintf("quasar-witness: peer witness service started (pure Qt wallet)\n");
}

void QuasarWitnessService::stop()
{
    if (m_timer) {
        m_timer->stop();
    }
}

void QuasarWitnessService::noteUserActivity()
{
    m_idle_since.restart();
}

bool QuasarWitnessService::isEnabled() const
{
    // CLI flag wins when present.
    if (gArgs.IsArgSet("-quasarwitness")) {
        return gArgs.GetBoolArg("-quasarwitness", true);
    }
    QSettings settings;
    if (!settings.contains(QStringLiteral("bQuasarWitness"))) {
        return true; // default on
    }
    return settings.value(QStringLiteral("bQuasarWitness"), true).toBool();
}

QString QuasarWitnessService::deviceId() const
{
    QString seed = QStringLiteral("bloodstone-qt|");
    if (m_client_model) {
        seed += m_client_model->dataDir();
    }
    seed += QStringLiteral("|") + QSysInfo::machineHostName();
    seed += QStringLiteral("|") + QSysInfo::productType();

    const std::string seed_std = seed.toStdString();
    const uint256 digest = Hash(seed_std);
    return QStringLiteral("qt-") + QString::fromStdString(digest.GetHex().substr(0, 24));
}

QString QuasarWitnessService::submitUrl() const
{
    if (gArgs.IsArgSet("-quasarwitnessurl")) {
        return QString::fromStdString(gArgs.GetArg("-quasarwitnessurl", DEFAULT_SUBMIT_URL));
    }
    QSettings settings;
    const QString from_settings = settings.value(QStringLiteral("strQuasarWitnessUrl")).toString().trimmed();
    if (!from_settings.isEmpty()) {
        return from_settings;
    }
    return QString::fromUtf8(DEFAULT_SUBMIT_URL);
}

bool QuasarWitnessService::shouldEmit(const QString& tip_hex, bool tip_changed) const
{
    if (m_inflight) {
        return false;
    }
    const qint64 now = QDateTime::currentMSecsSinceEpoch();
    if (!tip_changed && m_last_emit_ms > 0 && (now - m_last_emit_ms) < SAME_TIP_MIN_MS) {
        return false;
    }
    int idle_ms = DEFAULT_IDLE_MS;
    if (gArgs.IsArgSet("-quasarwitnessidlems")) {
        idle_ms = static_cast<int>(gArgs.GetArg("-quasarwitnessidlems", DEFAULT_IDLE_MS));
    }
    // New tip: emit even if the user is slightly active so peers learn chain growth.
    // Same tip: require idle window.
    if (!tip_changed && m_idle_since.isValid() && m_idle_since.elapsed() < idle_ms) {
        return false;
    }
    return true;
}

void QuasarWitnessService::tick()
{
    if (!isEnabled()) {
        m_last_status = QStringLiteral("disabled");
        return;
    }
    if (!m_client_model) {
        m_last_status = QStringLiteral("no-client-model");
        return;
    }

    interfaces::Node& node = m_client_model->node();
    if (node.isInitialBlockDownload()) {
        m_last_status = QStringLiteral("ibd");
        return;
    }
    const double progress = node.getVerificationProgress();
    if (progress > 0.0 && progress < 0.995) {
        m_last_status = QStringLiteral("syncing");
        return;
    }

    const int height = m_client_model->getNumBlocks();
    const uint256 tip = m_client_model->getBestBlockHash();
    if (height <= 0 || tip.IsNull()) {
        m_last_status = QStringLiteral("no-tip");
        return;
    }
    const QString tip_hex = TipHex(tip).toLower();
    const bool tip_changed = tip_hex != m_last_tip;
    if (!shouldEmit(tip_hex, tip_changed)) {
        m_last_status = tip_changed ? QStringLiteral("wait") : QStringLiteral("idle-throttle");
        return;
    }

    // Optional algo_work from getmininginfo; capsule still valid with empty map fallback.
    UniValue algo_work(UniValue::VOBJ);
    try {
        const UniValue mining = node.executeRpc("getmininginfo", UniValue(UniValue::VARR), "");
        if (mining.isObject() && mining.exists("difficulty")) {
            const UniValue& diff = mining["difficulty"];
            if (diff.isObject()) {
                for (const std::string& key : diff.getKeys()) {
                    algo_work.pushKV(key, UniToString(diff[key]));
                }
            } else if (!diff.isNull()) {
                algo_work.pushKV("chain", UniToString(diff));
            }
        }
    } catch (...) {
        /* optional */
    }
    if (algo_work.getKeys().empty()) {
        algo_work.pushKV("height", height);
    }

    UniValue capsule(UniValue::VOBJ);
    capsule.pushKV("type", CAPSULE_TYPE);
    capsule.pushKV("height", height);
    capsule.pushKV("tip_hash", tip_hex.toStdString());
    capsule.pushKV("algo_work", algo_work);
    capsule.pushKV("peer_count", m_client_model->getNumConnections());
    capsule.pushKV("node_mode", "qt-wallet");
    capsule.pushKV("device_id", deviceId().toStdString());
    capsule.pushKV("mesh_key", deviceId().toStdString());
    capsule.pushKV("issued_at", IsoUtcNow().toStdString());

    const QByteArray body = QByteArray::fromStdString(capsule.write() + "\n");
    QNetworkRequest req{QUrl(submitUrl())};
    req.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/json"));
    req.setRawHeader("User-Agent", "Bloodstone-Qt-Witness/1.0");
#if QT_VERSION >= QT_VERSION_CHECK(5, 9, 0)
    req.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::NoLessSafeRedirectPolicy);
#endif

    m_inflight = true;
    m_last_tip = tip_hex; // optimistic; reply may still fail
    m_last_emit_ms = QDateTime::currentMSecsSinceEpoch();
    m_last_status = QStringLiteral("submitting");
    LogPrintf("quasar-witness: submitting capsule h=%d tip=%s\n", height, tip_hex.left(16).toStdString());
    m_nam->post(req, body);
}

void QuasarWitnessService::onReplyFinished(QNetworkReply* reply)
{
    m_inflight = false;
    if (!reply) {
        return;
    }
    reply->deleteLater();

    const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    const QByteArray payload = reply->readAll();
    if (reply->error() != QNetworkReply::NoError) {
        m_last_status = QStringLiteral("error: ") + reply->errorString();
        LogPrintf("quasar-witness: submit failed: %s\n", reply->errorString().toStdString());
        // Allow retry sooner on failure
        m_last_emit_ms = 0;
        return;
    }
    if (status < 200 || status >= 300) {
        m_last_status = QStringLiteral("http-%1").arg(status);
        LogPrintf("quasar-witness: HTTP %d body=%s\n", status, payload.left(200).toStdString());
        m_last_emit_ms = 0;
        return;
    }
    m_last_status = QStringLiteral("ok");
    LogPrintf("quasar-witness: capsule accepted (%d bytes)\n", payload.size());
}

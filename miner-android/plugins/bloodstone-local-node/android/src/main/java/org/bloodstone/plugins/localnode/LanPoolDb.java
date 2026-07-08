package org.bloodstone.plugins.localnode;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import org.json.JSONArray;
import org.json.JSONObject;

import java.security.MessageDigest;
import java.util.Locale;

/** On-device pool ledger for LAN coordinators (shares, rounds, balances, payouts). */
final class LanPoolDb {
    private static final String DB_NAME = "bloodstone_lan_pool.db";
    private static final int DB_VERSION = 1;
    private static final double DEFAULT_BLOCK_REWARD = 100.0;
    private static final double DEFAULT_POOL_FEE_PCT = 1.0;
    private static final double BLOCK_FINDER_BONUS = 5.0;

    private final SQLiteOpenHelper helper;

    LanPoolDb(Context context) {
        helper = new Helper(context.getApplicationContext());
        initDb();
    }

    void initDb() {
        SQLiteDatabase db = helper.getWritableDatabase();
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS rounds ("
                + "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                + "algo TEXT NOT NULL,"
                + "job_height INTEGER NOT NULL,"
                + "status TEXT NOT NULL DEFAULT 'open',"
                + "total_weight REAL NOT NULL DEFAULT 0,"
                + "block_height INTEGER,"
                + "block_hash TEXT,"
                + "reward_stone REAL,"
                + "created_at INTEGER NOT NULL,"
                + "closed_at INTEGER"
                + ")"
        );
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS shares ("
                + "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                + "round_id INTEGER NOT NULL,"
                + "algo TEXT NOT NULL,"
                + "address TEXT NOT NULL,"
                + "worker TEXT NOT NULL,"
                + "job_height INTEGER NOT NULL,"
                + "weight REAL NOT NULL,"
                + "peer_ip TEXT,"
                + "created_at INTEGER NOT NULL,"
                + "import_id TEXT,"
                + "FOREIGN KEY(round_id) REFERENCES rounds(id)"
                + ")"
        );
        db.execSQL(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_shares_import ON shares(import_id) "
                + "WHERE import_id IS NOT NULL AND import_id != ''"
        );
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS miner_balances ("
                + "address TEXT PRIMARY KEY,"
                + "pending_stone REAL NOT NULL DEFAULT 0,"
                + "paid_stone REAL NOT NULL DEFAULT 0,"
                + "updated_at INTEGER NOT NULL"
                + ")"
        );
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS payouts ("
                + "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                + "address TEXT NOT NULL,"
                + "amount_stone REAL NOT NULL,"
                + "reason TEXT,"
                + "round_id INTEGER,"
                + "status TEXT NOT NULL DEFAULT 'credited',"
                + "created_at INTEGER NOT NULL"
                + ")"
        );
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS block_finds ("
                + "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                + "algo TEXT NOT NULL,"
                + "block_height INTEGER NOT NULL,"
                + "block_hash TEXT NOT NULL,"
                + "finder_address TEXT,"
                + "finder_worker TEXT,"
                + "reward_stone REAL,"
                + "round_id INTEGER,"
                + "created_at INTEGER NOT NULL"
                + ")"
        );
    }

    long recordShare(
        String algo,
        String address,
        String worker,
        int jobHeight,
        double weight,
        String peerIp,
        String importId
    ) {
        String normalizedAlgo = normalizeAlgo(algo);
        String payoutAddr = LanPoolShareUtil.payoutAddress(address, worker);
        if (!LanPoolShareUtil.isValidAddress(payoutAddr)) {
            return 0L;
        }
        String workerKey = LanPoolShareUtil.workerKey(worker, payoutAddr);
        double w = Math.max(0.0, weight);
        long now = System.currentTimeMillis() / 1000L;
        SQLiteDatabase db = helper.getWritableDatabase();
        db.beginTransaction();
        try {
            if (importId != null && !importId.isEmpty()) {
                Cursor dup = db.rawQuery(
                    "SELECT id FROM shares WHERE import_id = ? LIMIT 1",
                    new String[] {importId}
                );
                try {
                    if (dup.moveToFirst()) {
                        db.setTransactionSuccessful();
                        return dup.getLong(0);
                    }
                } finally {
                    dup.close();
                }
            }
            long roundId = ensureOpenRound(db, normalizedAlgo, jobHeight, now);
            db.execSQL(
                "INSERT INTO shares(algo,address,worker,job_height,weight,peer_ip,created_at,import_id,round_id) "
                    + "VALUES(?,?,?,?,?,?,?,?,?)",
                new Object[] {
                    normalizedAlgo,
                    payoutAddr,
                    workerKey,
                    jobHeight,
                    w,
                    peerIp != null ? peerIp : "",
                    now,
                    importId != null ? importId : "",
                    roundId,
                }
            );
            db.execSQL(
                "UPDATE rounds SET total_weight = total_weight + ? WHERE id = ?",
                new Object[] {w, roundId}
            );
            long shareId;
            Cursor idCur = db.rawQuery("SELECT last_insert_rowid()", null);
            try {
                shareId = idCur.moveToFirst() ? idCur.getLong(0) : 0L;
            } finally {
                idCur.close();
            }
            db.setTransactionSuccessful();
            return shareId;
        } finally {
            db.endTransaction();
        }
    }

    JSONObject distributeBlock(
        String algo,
        int blockHeight,
        String blockHash,
        String finderAddress,
        String finderWorker
    ) {
        String normalizedAlgo = normalizeAlgo(algo);
        JSONObject out = new JSONObject();
        double reward = DEFAULT_BLOCK_REWARD;
        double feePct = DEFAULT_POOL_FEE_PCT;
        long now = System.currentTimeMillis() / 1000L;
        SQLiteDatabase db = helper.getWritableDatabase();
        db.beginTransaction();
        try {
            Cursor rounds = db.rawQuery(
                "SELECT id, total_weight FROM rounds WHERE algo = ? AND status = 'open' ORDER BY id",
                new String[] {normalizedAlgo}
            );
            double totalWeight = 0.0;
            JSONArray roundIds = new JSONArray();
            try {
                while (rounds.moveToNext()) {
                    roundIds.put(rounds.getLong(0));
                    totalWeight += rounds.getDouble(1);
                }
            } finally {
                rounds.close();
            }
            if (roundIds.length() == 0) {
                out.put("ok", false);
                out.put("reason", "no_open_round");
                return out;
            }

            double feeStone = reward * (feePct / 100.0);
            double finderBonus = 0.0;
            String finder = LanPoolShareUtil.payoutAddress(finderAddress, finderWorker);
            if (LanPoolShareUtil.isValidAddress(finder) && BLOCK_FINDER_BONUS > 0) {
                finderBonus = Math.min(BLOCK_FINDER_BONUS, reward);
            }
            double distributable = Math.max(0.0, reward - feeStone - finderBonus);

            if (totalWeight > 0) {
                Cursor miners = db.rawQuery(
                    "SELECT address, SUM(weight) AS w FROM shares "
                        + "WHERE round_id IN (SELECT id FROM rounds WHERE algo = ? AND status = 'open') "
                        + "GROUP BY address",
                    new String[] {normalizedAlgo}
                );
                try {
                    while (miners.moveToNext()) {
                        String addr = miners.getString(0);
                        double minerWeight = miners.getDouble(1);
                        double credit = distributable * (minerWeight / totalWeight);
                        if (credit > 0) {
                            creditMiner(db, addr, credit, normalizedAlgo + "_block", roundIds.optLong(0), now);
                        }
                    }
                } finally {
                    miners.close();
                }
            }
            if (finderBonus > 0 && LanPoolShareUtil.isValidAddress(finder)) {
                creditMiner(db, finder, finderBonus, normalizedAlgo + "_finder_bonus", roundIds.optLong(0), now);
            }

            for (int i = 0; i < roundIds.length(); i++) {
                long rid = roundIds.optLong(i);
                db.execSQL(
                    "UPDATE rounds SET status='closed', block_height=?, block_hash=?, "
                        + "reward_stone=?, closed_at=? WHERE id=?",
                    new Object[] {blockHeight, blockHash, reward, now, rid}
                );
            }
            db.execSQL(
                "INSERT INTO block_finds(algo,block_height,block_hash,finder_address,finder_worker,reward_stone,round_id,created_at) "
                    + "VALUES(?,?,?,?,?,?,?,?)",
                new Object[] {
                    normalizedAlgo,
                    blockHeight,
                    blockHash,
                    finder != null ? finder : "",
                    finderWorker != null ? finderWorker : "",
                    reward,
                    roundIds.optLong(0),
                    now,
                }
            );
            ensureOpenRound(db, normalizedAlgo, blockHeight + 1, now);
            db.setTransactionSuccessful();
            out.put("ok", true);
            out.put("reward_stone", reward);
            out.put("distributable_stone", distributable);
            out.put("finder_bonus_stone", finderBonus);
            out.put("pool_fee_stone", feeStone);
            return out;
        } catch (Exception exc) {
            try {
                out.put("ok", false);
                out.put("error", exc.getMessage());
            } catch (Exception ignored) {
            }
            return out;
        } finally {
            db.endTransaction();
        }
    }

    JSONObject buildSnapshot(String deviceId, int blockHeight, String blockHash, boolean chainSynced) {
        JSONObject snap = new JSONObject();
        try {
            snap.put("device_id", deviceId != null ? deviceId : "");
            snap.put("block_height", blockHeight);
            snap.put("block_hash", blockHash != null ? blockHash : "");
            snap.put("chain_synced", chainSynced);
            JSONObject algos = new JSONObject();
            for (String algo : new String[] {"neoscrypt-xaya", "yespower", "sha256d"}) {
                algos.put(algo, algoRoundSummary(algo));
            }
            snap.put("algos", algos);
            snap.put("recent_block_finds", recentBlockFinds(5));
            snap.put("pool_state_hash", poolStateHash(algos));
        } catch (Exception ignored) {
        }
        return snap;
    }

    double getPendingBalance(String address) {
        if (address == null || address.isEmpty()) {
            return 0.0;
        }
        SQLiteDatabase db = helper.getReadableDatabase();
        Cursor cur = db.rawQuery(
            "SELECT pending_stone FROM miner_balances WHERE address = ? LIMIT 1",
            new String[] {address}
        );
        try {
            return cur.moveToFirst() ? cur.getDouble(0) : 0.0;
        } finally {
            cur.close();
        }
    }

    private JSONObject algoRoundSummary(String algo) {
        JSONObject row = new JSONObject();
        SQLiteDatabase db = helper.getReadableDatabase();
        Cursor cur = db.rawQuery(
            "SELECT id, job_height, total_weight, "
                + "(SELECT COUNT(*) FROM shares WHERE round_id = rounds.id) AS share_count "
                + "FROM rounds WHERE algo = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
            new String[] {algo}
        );
        try {
            if (cur.moveToFirst()) {
                try {
                    row.put("round_id", cur.getLong(0));
                    row.put("job_height", cur.getInt(1));
                    row.put("total_weight", cur.getDouble(2));
                    row.put("share_count", cur.getInt(3));
                } catch (Exception ignored) {
                }
            } else {
                try {
                    row.put("round_id", 0);
                    row.put("job_height", 0);
                    row.put("total_weight", 0.0);
                    row.put("share_count", 0);
                } catch (Exception ignored) {
                }
            }
        } finally {
            cur.close();
        }
        return row;
    }

    private JSONArray recentBlockFinds(int limit) {
        JSONArray out = new JSONArray();
        SQLiteDatabase db = helper.getReadableDatabase();
        Cursor cur = db.rawQuery(
            "SELECT algo, block_height, block_hash FROM block_finds ORDER BY id DESC LIMIT ?",
            new String[] {String.valueOf(Math.max(1, limit))}
        );
        try {
            while (cur.moveToNext()) {
                JSONObject row = new JSONObject();
                try {
                    row.put("algo", cur.getString(0));
                    row.put("height", cur.getInt(1));
                    row.put("hash", cur.getString(2));
                    out.put(row);
                } catch (Exception ignored) {
                }
            }
        } finally {
            cur.close();
        }
        return out;
    }

    private static String poolStateHash(JSONObject algos) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            md.update(algos.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
            byte[] digest = md.digest();
            StringBuilder sb = new StringBuilder(digest.length * 2);
            for (byte b : digest) {
                sb.append(String.format(Locale.US, "%02x", b));
            }
            return sb.toString();
        } catch (Exception exc) {
            return "";
        }
    }

    private long ensureOpenRound(SQLiteDatabase db, String algo, int jobHeight, long now) {
        Cursor cur = db.rawQuery(
            "SELECT id FROM rounds WHERE algo = ? AND status = 'open' AND job_height = ? LIMIT 1",
            new String[] {algo, String.valueOf(jobHeight)}
        );
        try {
            if (cur.moveToFirst()) {
                return cur.getLong(0);
            }
        } finally {
            cur.close();
        }
        db.execSQL(
            "INSERT INTO rounds(algo, job_height, status, total_weight, created_at) VALUES(?,?,'open',0,?)",
            new Object[] {algo, jobHeight, now}
        );
        Cursor idCur = db.rawQuery("SELECT last_insert_rowid()", null);
        try {
            return idCur.moveToFirst() ? idCur.getLong(0) : 0L;
        } finally {
            idCur.close();
        }
    }

    private void creditMiner(
        SQLiteDatabase db,
        String address,
        double amount,
        String reason,
        long roundId,
        long now
    ) {
        if (amount <= 0 || !LanPoolShareUtil.isValidAddress(address)) {
            return;
        }
        Cursor cur = db.rawQuery(
            "SELECT pending_stone FROM miner_balances WHERE address = ? LIMIT 1",
            new String[] {address}
        );
        boolean exists = false;
        double pending = 0.0;
        try {
            exists = cur.moveToFirst();
            if (exists) {
                pending = cur.getDouble(0);
            }
        } finally {
            cur.close();
        }
        if (exists) {
            db.execSQL(
                "UPDATE miner_balances SET pending_stone = ?, updated_at = ? WHERE address = ?",
                new Object[] {pending + amount, now, address}
            );
        } else {
            db.execSQL(
                "INSERT INTO miner_balances(address, pending_stone, paid_stone, updated_at) VALUES(?,?,0,?)",
                new Object[] {address, amount, now}
            );
        }
        db.execSQL(
            "INSERT INTO payouts(address, amount_stone, reason, round_id, status, created_at) VALUES(?,?,?,?,'credited',?)",
            new Object[] {address, amount, reason, roundId, now}
        );
    }

    private static String normalizeAlgo(String algo) {
        String a = (algo != null ? algo : "").trim().toLowerCase(Locale.US);
        if ("neoscrypt".equals(a) || "neoscrypt-xaya".equals(a)) {
            return "neoscrypt-xaya";
        }
        if ("sha256".equals(a) || "sha256d".equals(a)) {
            return "sha256d";
        }
        if ("yespower".equals(a) || "yespowerr16".equals(a)) {
            return "yespower";
        }
        return a.isEmpty() ? "neoscrypt-xaya" : a;
    }

    void syncOpenRoundJobHeights(int blockHeight) {
        if (blockHeight <= 0) {
            return;
        }
        long now = System.currentTimeMillis() / 1000L;
        SQLiteDatabase db = helper.getWritableDatabase();
        for (String algo : new String[] {"neoscrypt-xaya", "yespower", "sha256d"}) {
            ensureOpenRound(db, algo, blockHeight + 1, now);
        }
    }

    private static final class Helper extends SQLiteOpenHelper {
        Helper(Context context) {
            super(context, DB_NAME, null, DB_VERSION);
        }

        @Override
        public void onCreate(SQLiteDatabase db) {
        }

        @Override
        public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        }
    }
}
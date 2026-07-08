package org.bloodstone.plugins.devicepool;

import android.content.Context;
import android.content.SharedPreferences;

final class MinerPreferences {
    private static final String PREFS = "bloodstone_miner_prefs";
    private static final String KEY_STONE_PAYOUT = "stone_payout_address";

    private final SharedPreferences prefs;

    MinerPreferences(Context context) {
        prefs = context.getApplicationContext()
            .getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    String getStonePayoutAddress() {
        return prefs.getString(KEY_STONE_PAYOUT, "");
    }

    void setStonePayoutAddress(String address) {
        SharedPreferences.Editor editor = prefs.edit();
        if (address == null || address.trim().isEmpty()) {
            editor.remove(KEY_STONE_PAYOUT);
        } else {
            editor.putString(KEY_STONE_PAYOUT, address.trim());
        }
        editor.apply();
    }
}
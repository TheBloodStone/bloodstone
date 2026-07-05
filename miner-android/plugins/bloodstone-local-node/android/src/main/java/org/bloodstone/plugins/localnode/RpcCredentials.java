package org.bloodstone.plugins.localnode;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Base64;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;

final class RpcCredentials {
    private static final String PREFS = "bloodstone_local_node_rpc";
    private static final String KEY_USER = "rpc_user";
    private static final String KEY_PASS = "rpc_password";

    private final String user;
    private final String password;

    private RpcCredentials(String user, String password) {
        this.user = user;
        this.password = password;
    }

    static RpcCredentials loadOrCreate(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String user = prefs.getString(KEY_USER, null);
        String pass = prefs.getString(KEY_PASS, null);
        if (user == null || pass == null) {
            SecureRandom rng = new SecureRandom();
            byte[] userBytes = new byte[8];
            byte[] passBytes = new byte[24];
            rng.nextBytes(userBytes);
            rng.nextBytes(passBytes);
            user = "bs" + Base64.encodeToString(userBytes, Base64.URL_SAFE | Base64.NO_WRAP)
                .replace("=", "").substring(0, 8).toLowerCase();
            pass = Base64.encodeToString(passBytes, Base64.URL_SAFE | Base64.NO_WRAP)
                .replace("=", "");
            prefs.edit().putString(KEY_USER, user).putString(KEY_PASS, pass).apply();
        }
        return new RpcCredentials(user, pass);
    }

    String user() {
        return user;
    }

    String password() {
        return password;
    }
}
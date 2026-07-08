package org.bloodstone.plugins.localnode;

import java.util.Locale;
import java.util.regex.Pattern;

final class LanPoolShareUtil {
    private static final Pattern LEGACY_ADDR =
        Pattern.compile("^S[1-9A-HJ-NP-Za-km-z]{25,34}$");
    private static final Pattern BECH32_ADDR =
        Pattern.compile("^stone1[0-9a-z]{20,}$", Pattern.CASE_INSENSITIVE);

    private LanPoolShareUtil() {
    }

    static boolean isValidAddress(String addr) {
        if (addr == null) {
            return false;
        }
        String s = addr.trim();
        if (s.isEmpty()) {
            return false;
        }
        String upper = s.toUpperCase(Locale.US);
        if ("YOUR_STONE_ADDRESS".equals(upper) || "X".equals(upper) || "SOLO".equals(upper)) {
            return false;
        }
        return LEGACY_ADDR.matcher(s).matches() || BECH32_ADDR.matcher(s).matches();
    }

    static String payoutAddress(String address, String worker) {
        String fromWorker = worker != null ? worker.trim() : "";
        int dot = fromWorker.indexOf('.');
        if (dot > 0) {
            String base = fromWorker.substring(0, dot).trim();
            if (isValidAddress(base)) {
                return base;
            }
        }
        String fromAddr = address != null ? address.trim() : "";
        if (isValidAddress(fromAddr)) {
            return fromAddr;
        }
        if (isValidAddress(fromWorker)) {
            return fromWorker;
        }
        return fromAddr;
    }

    static String workerKey(String worker, String payoutAddress) {
        String w = worker != null ? worker.trim() : "";
        if (!w.isEmpty()) {
            return w;
        }
        return payoutAddress != null ? payoutAddress : "";
    }

    static String shareImportId(String deviceId, long shareId) {
        return (deviceId != null ? deviceId : "local") + ":" + shareId;
    }
}
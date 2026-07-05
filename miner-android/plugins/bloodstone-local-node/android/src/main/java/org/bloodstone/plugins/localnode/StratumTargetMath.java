package org.bloodstone.plugins.localnode;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.Locale;

/** Integer share-target math matching Bloodstone stratum servers. */
final class StratumTargetMath {
    private static final BigInteger DIFF1_TARGET = new BigInteger(
        "00000000FFFF0000000000000000000000000000000000000000000000000000", 16
    );
    private static final BigInteger MAX_SHARE_TARGET = BigInteger.ONE.shiftLeft(256).subtract(BigInteger.ONE);

    private StratumTargetMath() {
    }

    static BigInteger targetHexToInt(String targetHex) {
        if (targetHex == null || targetHex.isEmpty()) {
            return DIFF1_TARGET;
        }
        String clean = targetHex.trim().toLowerCase(Locale.US);
        byte[] raw = hexToBytes(clean);
        byte[] reversed = new byte[raw.length];
        for (int i = 0; i < raw.length; i++) {
            reversed[i] = raw[raw.length - 1 - i];
        }
        return new BigInteger(1, reversed);
    }

    static String intToCompareHex(BigInteger value) {
        byte[] mem = toLittleEndian32(value);
        return reverseHex(bytesToHex(mem));
    }

    static BigInteger shareTargetInt(BigInteger blockTarget, double shareDifficulty, boolean solo) {
        if (solo || shareDifficulty <= 0) {
            return blockTarget;
        }
        BigDecimal diff = BigDecimal.valueOf(Math.max(shareDifficulty, 1e-20));
        BigInteger poolTarget = new BigDecimal(DIFF1_TARGET)
            .divide(diff, 0, RoundingMode.DOWN)
            .toBigInteger();
        if (poolTarget.compareTo(MAX_SHARE_TARGET) > 0) {
            poolTarget = MAX_SHARE_TARGET;
        }
        BigInteger capped = poolTarget.max(blockTarget);
        return capped.min(MAX_SHARE_TARGET);
    }

    static double targetToDifficulty(BigInteger target) {
        if (target.signum() <= 0) {
            return 1.0;
        }
        return new BigDecimal(DIFF1_TARGET).divide(new BigDecimal(target), 12, BigDecimal.ROUND_HALF_UP).doubleValue();
    }

    private static byte[] toLittleEndian32(BigInteger value) {
        byte[] src = value.toByteArray();
        byte[] out = new byte[32];
        int copy = Math.min(src.length, 32);
        for (int i = 0; i < copy; i++) {
            out[i] = src[src.length - 1 - i];
        }
        return out;
    }

    private static byte[] hexToBytes(String hex) {
        int len = hex.length();
        byte[] out = new byte[len / 2];
        for (int i = 0; i < len; i += 2) {
            out[i / 2] = (byte) Integer.parseInt(hex.substring(i, i + 2), 16);
        }
        return out;
    }

    private static String bytesToHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(String.format(Locale.US, "%02x", b));
        }
        return sb.toString();
    }

    private static String reverseHex(String hex) {
        int len = hex.length();
        StringBuilder sb = new StringBuilder(len);
        for (int i = len - 2; i >= 0; i -= 2) {
            sb.append(hex, i, i + 2);
        }
        return sb.toString();
    }
}
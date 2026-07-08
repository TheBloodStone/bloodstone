package org.bloodstone.plugins.localnode;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

/** Minimal auxpow helpers (ported from bloodstone-core test_framework/auxpow.py). */
final class AuxpowUtil {
    static final class TxHeader {
        final String txHex;
        final String headerHex;

        TxHeader(String txHex, String headerHex) {
            this.txHex = txHex;
            this.headerHex = headerHex;
        }
    }

    static final class StratumParts {
        final String txHex;
        final String coinb1;
        final String coinb2;
        final String prevhash;

        StratumParts(String txHex, String coinb1, String coinb2, String prevhash) {
            this.txHex = txHex;
            this.coinb1 = coinb1;
            this.coinb2 = coinb2;
            this.prevhash = prevhash;
        }
    }

    private AuxpowUtil() {
    }

    static TxHeader constructAuxpow(String blockHashHex) {
        String block = blockHashHex.toLowerCase(Locale.US);
        String coinbase = "fabe6d6d" + block + "01000000" + repeatHex("00", 4);
        String vin = "01"
            + repeatHex("00", 32)
            + repeatHex("ff", 4)
            + String.format(Locale.US, "%02x", coinbase.length() / 2)
            + coinbase
            + repeatHex("ff", 4);
        String tx = "01000000" + vin + "00" + repeatHex("00", 4);
        String txHash = doubleHashHex(tx);
        String header = "01000000"
            + repeatHex("00", 32)
            + reverseHex(txHash)
            + repeatHex("00", 12);
        return new TxHeader(tx, header);
    }

    static StratumParts buildStratumParts(String blockHashHex, String extranonce1) {
        TxHeader base = constructAuxpow(blockHashHex);
        byte[] txBytes = hexToBytes(base.txHex);
        int insertAt = extranonceOffset(txBytes);
        byte[] en1 = hexToBytes(padHex(extranonce1, 8));
        if (en1.length != 4) {
            throw new IllegalArgumentException("extranonce1 must be 4 bytes");
        }
        System.arraycopy(en1, 0, txBytes, insertAt, 4);
        String txHex = bytesToHex(txBytes);
        String coinb1 = txHex.substring(0, insertAt * 2);
        String coinb2 = txHex.substring((insertAt + 8) * 2);
        String prevhash = base.headerHex.length() >= 72 ? base.headerHex.substring(8, 72) : base.headerHex;
        return new StratumParts(txHex, coinb1, coinb2, prevhash);
    }

    static String finishAuxpow(String txHex, String headerHex) {
        String blockhash = doubleHashHex(headerHex);
        StringBuilder auxpow = new StringBuilder();
        auxpow.append(txHex);
        auxpow.append(blockhash);
        auxpow.append("00");
        auxpow.append(repeatHex("00", 4));
        auxpow.append("00");
        auxpow.append(repeatHex("00", 4));
        auxpow.append(headerHex);
        return auxpow.toString();
    }

    static String doubleHashHex(String dataHex) {
        byte[] first = sha256(hexToBytes(dataHex));
        byte[] second = sha256(first);
        return reverseHex(bytesToHex(second));
    }

    static String reverseHex(String hex) {
        String clean = hex.toLowerCase(Locale.US);
        StringBuilder out = new StringBuilder(clean.length());
        for (int i = clean.length() - 2; i >= 0; i -= 2) {
            out.append(clean, i, i + 2);
        }
        return out.toString();
    }

    static int extranonceOffset(byte[] txBytes) {
        for (int i = 0; i < txBytes.length - 1; i += 1) {
            if ((txBytes[i] & 0xff) == 0xfa && (txBytes[i + 1] & 0xff) == 0xbe) {
                return i + 40;
            }
        }
        throw new IllegalStateException("coinbase marker not found");
    }

    static byte[] buildHeaderBytes(
        String txHex,
        String nbitsHex,
        String ntimeHex,
        String nonceHex,
        String versionHex
    ) {
        int versionWord = 0x01000000 | (int) Long.parseLong(versionHex, 16);
        byte[] header = new byte[80];
        writeLe32(header, 0, versionWord);
        byte[] merkle = sha256(sha256(hexToBytes(txHex)));
        System.arraycopy(merkle, 0, header, 36, 32);
        writeLe32(header, 68, (int) Long.parseLong(ntimeHex, 16));
        writeLe32(header, 72, (int) Long.parseLong(nbitsHex, 16));
        writeLe32(header, 76, (int) Long.parseLong(padHex(nonceHex, 8), 16));
        return header;
    }

    private static void writeLe32(byte[] out, int offset, int value) {
        out[offset] = (byte) (value & 0xff);
        out[offset + 1] = (byte) ((value >>> 8) & 0xff);
        out[offset + 2] = (byte) ((value >>> 16) & 0xff);
        out[offset + 3] = (byte) ((value >>> 24) & 0xff);
    }

    private static byte[] sha256(byte[] data) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(data);
        } catch (Exception exc) {
            throw new RuntimeException(exc);
        }
    }

    private static String repeatHex(String unit, int count) {
        StringBuilder sb = new StringBuilder(unit.length() * count);
        for (int i = 0; i < count; i += 1) {
            sb.append(unit);
        }
        return sb.toString();
    }

    private static String padHex(String hex, int len) {
        String clean = hex == null ? "" : hex.replaceAll("\\s+", "").toLowerCase(Locale.US);
        if (clean.length() >= len) {
            return clean.substring(clean.length() - len);
        }
        StringBuilder sb = new StringBuilder(len);
        for (int i = clean.length(); i < len; i += 1) {
            sb.append('0');
        }
        sb.append(clean);
        return sb.toString();
    }

    private static byte[] hexToBytes(String hex) {
        String clean = hex.replaceAll("\\s+", "").toLowerCase(Locale.US);
        int len = clean.length();
        byte[] out = new byte[len / 2];
        for (int i = 0; i < len; i += 2) {
            out[i / 2] = (byte) Integer.parseInt(clean.substring(i, i + 2), 16);
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
}
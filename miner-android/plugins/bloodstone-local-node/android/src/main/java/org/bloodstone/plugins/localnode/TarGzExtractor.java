package org.bloodstone.plugins.localnode;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.zip.GZIPInputStream;

final class TarGzExtractor {
    private static final int BLOCK_SIZE = 512;

    private TarGzExtractor() {
    }

    static void extract(File archive, File destDir) throws IOException {
        if (!destDir.exists() && !destDir.mkdirs()) {
            throw new IOException("cannot create " + destDir.getAbsolutePath());
        }
        try (InputStream in = new GZIPInputStream(new BufferedInputStream(new FileInputStream(archive)))) {
            byte[] header = new byte[BLOCK_SIZE];
            while (true) {
                int read = readFully(in, header);
                if (read == 0) {
                    break;
                }
                if (read < BLOCK_SIZE) {
                    throw new IOException("truncated tar header");
                }
                if (isEmptyBlock(header)) {
                    break;
                }
                String name = readAscii(header, 0, 100).replace("\u0000", "").trim();
                if (name.isEmpty()) {
                    skipEntry(in, header);
                    continue;
                }
                long size = parseOctal(header, 124, 12);
                char type = (char) header[156];
                File out = safeOutput(destDir, name);
                if (type == '5' || name.endsWith("/")) {
                    if (!out.exists() && !out.mkdirs()) {
                        throw new IOException("cannot mkdir " + out.getAbsolutePath());
                    }
                } else if (type == '0' || type == '\0') {
                    File parent = out.getParentFile();
                    if (parent != null && !parent.exists() && !parent.mkdirs()) {
                        throw new IOException("cannot mkdir " + parent.getAbsolutePath());
                    }
                    writeFile(in, out, size);
                } else {
                    skipBytes(in, size);
                }
                long padding = (BLOCK_SIZE - (size % BLOCK_SIZE)) % BLOCK_SIZE;
                skipBytes(in, padding);
            }
        }
    }

    private static void skipEntry(InputStream in, byte[] header) throws IOException {
        long size = parseOctal(header, 124, 12);
        skipBytes(in, size);
        long padding = (BLOCK_SIZE - (size % BLOCK_SIZE)) % BLOCK_SIZE;
        skipBytes(in, padding);
    }

    private static void writeFile(InputStream in, File out, long size) throws IOException {
        try (FileOutputStream fos = new FileOutputStream(out)) {
            long remaining = size;
            byte[] buf = new byte[8192];
            while (remaining > 0) {
                int chunk = (int) Math.min(buf.length, remaining);
                int read = in.read(buf, 0, chunk);
                if (read < 0) {
                    throw new IOException("unexpected EOF writing " + out.getName());
                }
                fos.write(buf, 0, read);
                remaining -= read;
            }
        }
    }

    private static File safeOutput(File destDir, String entryName) throws IOException {
        String normalized = entryName.replace('\\', '/');
        while (normalized.startsWith("./")) {
            normalized = normalized.substring(2);
        }
        if (normalized.startsWith("/") || normalized.contains("..")) {
            throw new IOException("unsafe tar path: " + entryName);
        }
        return new File(destDir, normalized);
    }

    private static int readFully(InputStream in, byte[] buf) throws IOException {
        int total = 0;
        while (total < buf.length) {
            int read = in.read(buf, total, buf.length - total);
            if (read < 0) {
                return total;
            }
            total += read;
        }
        return total;
    }

    private static void skipBytes(InputStream in, long count) throws IOException {
        long remaining = count;
        byte[] buf = new byte[8192];
        while (remaining > 0) {
            int chunk = (int) Math.min(buf.length, remaining);
            int read = in.read(buf, 0, chunk);
            if (read < 0) {
                throw new IOException("unexpected EOF in tar stream");
            }
            remaining -= read;
        }
    }

    private static boolean isEmptyBlock(byte[] block) {
        for (byte b : block) {
            if (b != 0) {
                return false;
            }
        }
        return true;
    }

    private static String readAscii(byte[] buf, int offset, int len) {
        StringBuilder sb = new StringBuilder(len);
        for (int i = offset; i < offset + len; i++) {
            char ch = (char) (buf[i] & 0xff);
            if (ch == 0) {
                break;
            }
            sb.append(ch);
        }
        return sb.toString();
    }

    private static long parseOctal(byte[] buf, int offset, int len) {
        long value = 0L;
        for (int i = offset; i < offset + len; i++) {
            char ch = (char) (buf[i] & 0xff);
            if (ch == 0 || ch == ' ') {
                continue;
            }
            if (ch < '0' || ch > '7') {
                break;
            }
            value = (value << 3) + (ch - '0');
        }
        return value;
    }
}
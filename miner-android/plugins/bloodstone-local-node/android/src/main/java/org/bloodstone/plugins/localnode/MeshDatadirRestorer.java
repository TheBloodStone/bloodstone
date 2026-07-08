package org.bloodstone.plugins.localnode;

import android.content.Context;
import android.util.Log;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Write locally cached mesh chunks into a bloodstoned datadir (overlay or replace). */
final class MeshDatadirRestorer {
    private static final String TAG = "MeshDatadirRestorer";
    private static final String MESH_META = "chain-mesh-meta.json";

    static final class Result {
        final int chunksApplied;
        final long bytesWritten;
        final int filesTouched;
        final boolean reindexRequired;

        Result(int chunksApplied, long bytesWritten, int filesTouched, boolean reindexRequired) {
            this.chunksApplied = chunksApplied;
            this.bytesWritten = bytesWritten;
            this.filesTouched = filesTouched;
            this.reindexRequired = reindexRequired;
        }
    }

    private MeshDatadirRestorer() {
    }

    static Result apply(Context context, File dataDir, boolean replaceExisting) throws Exception {
        if (dataDir == null) {
            throw new IllegalArgumentException("datadir required");
        }
        if (!dataDir.exists() && !dataDir.mkdirs()) {
            throw new IllegalStateException("cannot create datadir");
        }

        File meshRoot = new File(context.getFilesDir(), "bloodstone-chain-mesh");
        JSONObject allMeta = readMeshMeta(meshRoot);
        List<ChunkEntry> entries = listChunkEntries(meshRoot, allMeta);
        if (entries.isEmpty()) {
            throw new IllegalStateException("no mesh chunks on device — sync Time Capsule or import a mesh backup first");
        }

        Map<String, List<ChunkEntry>> byFile = new HashMap<>();
        for (ChunkEntry entry : entries) {
            if (!isSafeRelativePath(entry.sourceFile)) {
                Log.w(TAG, "skip unsafe source path: " + entry.sourceFile);
                continue;
            }
            byFile.computeIfAbsent(entry.sourceFile, k -> new ArrayList<>()).add(entry);
        }
        if (byFile.isEmpty()) {
            throw new IllegalStateException("mesh chunks have no restorable block/chainstate paths");
        }

        if (replaceExisting) {
            deleteTree(new File(dataDir, "blocks"));
            ChainBootstrapInstaller.prepareForReindex(dataDir);
        }

        int chunksApplied = 0;
        long bytesWritten = 0L;
        int filesTouched = 0;
        boolean touchedBlocks = false;

        for (Map.Entry<String, List<ChunkEntry>> row : byFile.entrySet()) {
            String rel = row.getKey();
            File target = new File(dataDir, rel.replace("/", File.separator));
            File parent = target.getParentFile();
            if (parent != null && !parent.exists() && !parent.mkdirs()) {
                throw new IllegalStateException("cannot create " + parent.getAbsolutePath());
            }
            for (ChunkEntry chunk : row.getValue()) {
                byte[] data = readChunkBytes(meshRoot, chunk.hash);
                if (data == null || data.length == 0) {
                    Log.w(TAG, "missing chunk data " + chunk.hash);
                    continue;
                }
                int expected = chunk.size > 0 ? chunk.size : data.length;
                if (data.length != expected) {
                    Log.w(TAG, "chunk size mismatch " + chunk.hash);
                    continue;
                }
                writeAtOffset(target, chunk.fileOffset, data);
                chunksApplied += 1;
                bytesWritten += data.length;
            }
            filesTouched += 1;
            if (rel.startsWith("blocks/")) {
                touchedBlocks = true;
            }
        }

        if (chunksApplied <= 0) {
            throw new IllegalStateException("no mesh chunks could be written — re-sync mesh data");
        }

        boolean reindexRequired = touchedBlocks;
        if (reindexRequired) {
            ChainBootstrapInstaller.prepareForReindex(dataDir);
            try (FileOutputStream marker = new FileOutputStream(
                new File(dataDir, ".bootstrap-reindex"))) {
                marker.write("mesh-overlay\n".getBytes(StandardCharsets.UTF_8));
            }
        }

        Log.i(
            TAG,
            "applied mesh overlay: chunks="
                + chunksApplied
                + " bytes="
                + bytesWritten
                + " files="
                + filesTouched
                + " reindex="
                + reindexRequired
        );
        return new Result(chunksApplied, bytesWritten, filesTouched, reindexRequired);
    }

    private static boolean isSafeRelativePath(String rel) {
        if (rel == null || rel.isEmpty()) {
            return false;
        }
        String norm = rel.replace("\\", "/").trim();
        if (norm.startsWith("/") || norm.contains("..")) {
            return false;
        }
        if (!(norm.startsWith("blocks/") || norm.startsWith("chainstate/"))) {
            return false;
        }
        return norm.matches("^(blocks|chainstate)/[A-Za-z0-9._-]+$");
    }

    private static void writeAtOffset(File target, long offset, byte[] data) throws Exception {
        try (RandomAccessFile raf = new RandomAccessFile(target, "rw")) {
            raf.seek(offset);
            raf.write(data);
        }
    }

    private static byte[] readChunkBytes(File meshRoot, String hash) throws Exception {
        String h = hash.trim().toLowerCase(Locale.US);
        File file = new File(new File(meshRoot, h.substring(0, 2)), h + ".bin");
        if (!file.isFile()) {
            return null;
        }
        try (FileInputStream in = new FileInputStream(file)) {
            byte[] buf = new byte[(int) file.length()];
            int read = in.read(buf);
            if (read <= 0) {
                return null;
            }
            if (read < buf.length) {
                byte[] trimmed = new byte[read];
                System.arraycopy(buf, 0, trimmed, 0, read);
                return trimmed;
            }
            return buf;
        }
    }

    private static JSONObject readMeshMeta(File meshRoot) throws Exception {
        File meta = new File(meshRoot, MESH_META);
        if (!meta.isFile()) {
            return new JSONObject();
        }
        try (FileInputStream in = new FileInputStream(meta)) {
            byte[] buf = new byte[(int) meta.length()];
            int read = in.read(buf);
            if (read <= 0) {
                return new JSONObject();
            }
            return new JSONObject(new String(buf, 0, read, StandardCharsets.UTF_8));
        }
    }

    private static List<ChunkEntry> listChunkEntries(File meshRoot, JSONObject allMeta) {
        List<ChunkEntry> out = new ArrayList<>();
        if (!meshRoot.isDirectory()) {
            return out;
        }
        File[] subs = meshRoot.listFiles();
        if (subs == null) {
            return out;
        }
        for (File sub : subs) {
            if (!sub.isDirectory()) {
                continue;
            }
            File[] files = sub.listFiles();
            if (files == null) {
                continue;
            }
            for (File file : files) {
                if (!file.isFile() || !file.getName().endsWith(".bin")) {
                    continue;
                }
                String hash = file.getName().replace(".bin", "");
                JSONObject meta = allMeta.optJSONObject(hash);
                String sourceFile = meta != null ? meta.optString("sourceFile", "") : "";
                long offset = meta != null ? meta.optLong("fileOffset", 0L) : 0L;
                int size = meta != null ? meta.optInt("size", (int) file.length()) : (int) file.length();
                if (sourceFile.isEmpty()) {
                    continue;
                }
                out.add(new ChunkEntry(hash, sourceFile, offset, size));
            }
        }
        return out;
    }

    private static void deleteTree(File dir) {
        if (dir == null || !dir.exists()) {
            return;
        }
        if (dir.isDirectory()) {
            File[] children = dir.listFiles();
            if (children != null) {
                for (File child : children) {
                    deleteTree(child);
                }
            }
        }
        if (!dir.delete()) {
            Log.w(TAG, "could not delete " + dir.getAbsolutePath());
        }
    }

    private static final class ChunkEntry {
        final String hash;
        final String sourceFile;
        final long fileOffset;
        final int size;

        ChunkEntry(String hash, String sourceFile, long fileOffset, int size) {
            this.hash = hash;
            this.sourceFile = sourceFile;
            this.fileOffset = fileOffset;
            this.size = size;
        }
    }
}
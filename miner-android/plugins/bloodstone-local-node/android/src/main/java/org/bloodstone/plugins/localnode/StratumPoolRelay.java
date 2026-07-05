package org.bloodstone.plugins.localnode;

import android.util.Log;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

/**
 * Transparent stratum line relay — forwards pool-mode miners on LAN to upstream VPS pool.
 */
final class StratumPoolRelay {
    private static final String TAG = "BloodstonePoolRelay";

    private StratumPoolRelay() {
    }

    static void relayWithHandshake(
        Socket client,
        String upstreamHost,
        int upstreamPort,
        String firstLine,
        String secondLine
    ) {
        Socket upstream = null;
        try (
            Socket clientSock = client;
            BufferedReader clientReader = new BufferedReader(
                new InputStreamReader(clientSock.getInputStream(), StandardCharsets.UTF_8)
            );
            BufferedWriter clientWriter = new BufferedWriter(
                new OutputStreamWriter(clientSock.getOutputStream(), StandardCharsets.UTF_8)
            )
        ) {
            upstream = new Socket();
            upstream.connect(new InetSocketAddress(upstreamHost, upstreamPort), 15000);
            upstream.setTcpNoDelay(true);
            upstream.setKeepAlive(true);

            try (
                BufferedReader upstreamReader = new BufferedReader(
                    new InputStreamReader(upstream.getInputStream(), StandardCharsets.UTF_8)
                );
                BufferedWriter upstreamWriter = new BufferedWriter(
                    new OutputStreamWriter(upstream.getOutputStream(), StandardCharsets.UTF_8)
                )
            ) {
                writeLine(upstreamWriter, firstLine);
                writeLine(upstreamWriter, secondLine);
                forwardInitialResponses(upstreamReader, clientWriter, 2);

                Thread clientToUpstream = new Thread(
                    () -> pipeLines(clientReader, upstreamWriter, "client→pool"),
                    "bloodstone-pool-relay-up"
                );
                Thread upstreamToClient = new Thread(
                    () -> pipeLines(upstreamReader, clientWriter, "pool→client"),
                    "bloodstone-pool-relay-down"
                );
                clientToUpstream.setDaemon(true);
                upstreamToClient.setDaemon(true);
                clientToUpstream.start();
                upstreamToClient.start();
                clientToUpstream.join();
                upstreamToClient.join();
            }
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
        } catch (Exception exc) {
            Log.w(TAG, "handshake relay ended: " + exc.getMessage());
        } finally {
            closeQuietly(upstream);
        }
    }

    static void relay(Socket client, String upstreamHost, int upstreamPort) {
        Socket upstream = null;
        try (
            Socket clientSock = client;
            BufferedReader clientReader = new BufferedReader(
                new InputStreamReader(clientSock.getInputStream(), StandardCharsets.UTF_8)
            );
            BufferedWriter clientWriter = new BufferedWriter(
                new OutputStreamWriter(clientSock.getOutputStream(), StandardCharsets.UTF_8)
            )
        ) {
            upstream = new Socket();
            upstream.connect(new InetSocketAddress(upstreamHost, upstreamPort), 15000);
            upstream.setTcpNoDelay(true);
            upstream.setKeepAlive(true);
            Log.i(TAG, "pool relay open " + upstreamHost + ":" + upstreamPort);

            try (
                BufferedReader upstreamReader = new BufferedReader(
                    new InputStreamReader(upstream.getInputStream(), StandardCharsets.UTF_8)
                );
                BufferedWriter upstreamWriter = new BufferedWriter(
                    new OutputStreamWriter(upstream.getOutputStream(), StandardCharsets.UTF_8)
                )
            ) {
                Thread clientToUpstream = new Thread(
                    () -> pipeLines(clientReader, upstreamWriter, "client→pool"),
                    "bloodstone-pool-relay-up"
                );
                Thread upstreamToClient = new Thread(
                    () -> pipeLines(upstreamReader, clientWriter, "pool→client"),
                    "bloodstone-pool-relay-down"
                );
                clientToUpstream.setDaemon(true);
                upstreamToClient.setDaemon(true);
                clientToUpstream.start();
                upstreamToClient.start();
                clientToUpstream.join();
                upstreamToClient.join();
            }
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
        } catch (Exception exc) {
            Log.w(TAG, "relay ended: " + exc.getMessage());
        } finally {
            if (upstream != null) {
                try {
                    upstream.close();
                } catch (IOException ignored) {
                }
            }
        }
    }

    private static void writeLine(BufferedWriter writer, String line) throws IOException {
        writer.write(line);
        writer.write('\n');
        writer.flush();
    }

    private static void forwardInitialResponses(
        BufferedReader upstreamReader,
        BufferedWriter clientWriter,
        int count
    ) throws IOException {
        for (int i = 0; i < count; i++) {
            String line = upstreamReader.readLine();
            if (line == null || line.isEmpty()) {
                break;
            }
            writeLine(clientWriter, line);
        }
    }

    private static void closeQuietly(Socket socket) {
        if (socket == null) {
            return;
        }
        try {
            socket.close();
        } catch (IOException ignored) {
        }
    }

    private static void pipeLines(BufferedReader reader, BufferedWriter writer, String label) {
        try {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isEmpty()) {
                    continue;
                }
                writer.write(line);
                writer.write('\n');
                writer.flush();
            }
        } catch (IOException exc) {
            Log.d(TAG, label + " pipe closed: " + exc.getMessage());
        }
    }
}
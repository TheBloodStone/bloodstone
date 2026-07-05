package org.bloodstone.plugins.stratum;

import android.util.Log;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

@CapacitorPlugin(name = "BloodstoneStratum")
public class StratumPlugin extends Plugin {
    private static final String TAG = "BloodstoneStratum";

    private final ExecutorService ioExecutor = Executors.newSingleThreadExecutor();
    private final AtomicBoolean connected = new AtomicBoolean(false);

    private Socket socket;
    private BufferedWriter writer;
    private Thread readerThread;

    @PluginMethod
    public void connect(PluginCall call) {
        String host = call.getString("host");
        Integer port = call.getInt("port");
        if (host == null || host.isEmpty() || port == null || port <= 0) {
            call.reject("host and port are required");
            return;
        }

        ioExecutor.execute(() -> {
            try {
                disconnectInternal("reconnect");
                Socket next = new Socket();
                next.connect(new InetSocketAddress(host, port), 15000);
                next.setTcpNoDelay(true);
                next.setKeepAlive(true);
                socket = next;
                writer = new BufferedWriter(
                    new OutputStreamWriter(next.getOutputStream(), StandardCharsets.UTF_8)
                );
                connected.set(true);
                startReader();
                JSObject ret = new JSObject();
                ret.put("connected", true);
                call.resolve(ret);
            } catch (IOException exc) {
                Log.w(TAG, "connect failed: " + exc.getMessage());
                disconnectInternal("connect failed");
                call.reject("connect failed: " + exc.getMessage());
            }
        });
    }

    @PluginMethod
    public void send(PluginCall call) {
        String line = call.getString("line");
        if (line == null || line.isEmpty()) {
            call.reject("line is required");
            return;
        }
        ioExecutor.execute(() -> {
            try {
                if (!connected.get() || writer == null) {
                    call.reject("not connected");
                    return;
                }
                writer.write(line.trim());
                writer.write('\n');
                writer.flush();
                call.resolve();
            } catch (IOException exc) {
                Log.w(TAG, "send failed: " + exc.getMessage());
                notifyClose("send failed");
                call.reject("send failed: " + exc.getMessage());
            }
        });
    }

    @PluginMethod
    public void disconnect(PluginCall call) {
        ioExecutor.execute(() -> {
            disconnectInternal("client disconnect");
            call.resolve();
        });
    }

    private void startReader() {
        readerThread = new Thread(() -> {
            try {
                BufferedReader reader = new BufferedReader(
                    new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8)
                );
                String line;
                while (connected.get() && (line = reader.readLine()) != null) {
                    if (line.isEmpty()) {
                        continue;
                    }
                    JSObject payload = new JSObject();
                    payload.put("line", line);
                    notifyListeners("stratumMessage", payload);
                }
                notifyClose("stratum closed");
            } catch (IOException exc) {
                if (connected.get()) {
                    notifyClose("read error");
                }
            }
        }, "bloodstone-stratum-reader");
        readerThread.setDaemon(true);
        readerThread.start();
    }

    private void notifyClose(String reason) {
        disconnectInternal(reason);
        JSObject payload = new JSObject();
        payload.put("reason", reason);
        notifyListeners("stratumClose", payload);
    }

    private void disconnectInternal(String reason) {
        connected.set(false);
        if (readerThread != null) {
            readerThread.interrupt();
            readerThread = null;
        }
        if (writer != null) {
            try {
                writer.close();
            } catch (IOException ignored) {
            }
            writer = null;
        }
        if (socket != null) {
            try {
                socket.close();
            } catch (IOException ignored) {
            }
            socket = null;
        }
        Log.i(TAG, "disconnected: " + reason);
    }

    @Override
    protected void handleOnDestroy() {
        disconnectInternal("app destroyed");
        ioExecutor.shutdownNow();
        super.handleOnDestroy();
    }
}
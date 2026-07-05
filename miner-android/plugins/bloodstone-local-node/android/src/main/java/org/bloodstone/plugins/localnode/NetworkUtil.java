package org.bloodstone.plugins.localnode;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.os.Build;

import java.net.Inet4Address;
import java.net.InetAddress;
import java.util.Locale;

final class NetworkUtil {
    private NetworkUtil() {
    }

    static String lanIpv4(Context context) {
        ConnectivityManager cm = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm == null) {
            return "";
        }
        Network network = null;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Network[] networks = cm.getAllNetworks();
            for (Network candidate : networks) {
                NetworkCapabilities caps = cm.getNetworkCapabilities(candidate);
                if (caps == null) {
                    continue;
                }
                if (caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
                    || caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)) {
                    network = candidate;
                    break;
                }
            }
            if (network == null && networks.length > 0) {
                network = networks[0];
            }
        }
        if (network == null) {
            return "";
        }
        LinkProperties props = cm.getLinkProperties(network);
        if (props == null) {
            return "";
        }
        for (LinkAddress link : props.getLinkAddresses()) {
            InetAddress addr = link.getAddress();
            if (addr instanceof Inet4Address && !addr.isLoopbackAddress()) {
                String host = addr.getHostAddress();
                if (host != null && isPrivateLan(host)) {
                    return host;
                }
            }
        }
        return "";
    }

    static boolean isPrivateLan(String ip) {
        if (ip == null) {
            return false;
        }
        String value = ip.trim();
        if (value.startsWith("10.")) {
            return true;
        }
        if (value.startsWith("192.168.")) {
            return true;
        }
        if (value.startsWith("172.")) {
            String[] parts = value.split("\\.");
            if (parts.length >= 2) {
                try {
                    int second = Integer.parseInt(parts[1]);
                    return second >= 16 && second <= 31;
                } catch (NumberFormatException ignored) {
                    return false;
                }
            }
        }
        return false;
    }

    static boolean isLanClient(String remoteIp) {
        if (remoteIp == null || remoteIp.isEmpty()) {
            return false;
        }
        String ip = remoteIp.trim();
        if ("127.0.0.1".equals(ip) || "::1".equals(ip)) {
            return true;
        }
        return isPrivateLan(ip);
    }
}
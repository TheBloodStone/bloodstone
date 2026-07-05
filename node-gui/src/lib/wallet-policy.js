function walletsForUser(user) {
  const names = new Set();
  if (user?.wallet_name) {
    names.add(user.wallet_name);
  }
  if (user?.primary_receive_wallet) {
    names.add(user.primary_receive_wallet);
  }
  for (const name of user?.linked_wallets || []) {
    if (name) {
      names.add(name);
    }
  }
  return [...names].sort((a, b) => a.localeCompare(b));
}

/** Wallet list for UI dropdowns — prefers cached available_wallets from login. */
function walletNamesForUser(user) {
  if (user?.available_wallets?.length) {
    return user.available_wallets;
  }
  return walletsForUser(user);
}

/** Web wallet accounts store funds on the VPS — use VPS RPC after sign-in. */
function useVpsWalletRpc(user) {
  return !!user?.wallet_name;
}

/** Accounts whose funds live on a VPS-only wallet (e.g. linked `mine`). */
function requiresVpsRpc(user) {
  if (!user?.wallet_name) {
    return false;
  }
  const primary = user.primary_receive_wallet || user.wallet_name;
  if (primary !== user.wallet_name) {
    return true;
  }
  const linked = user.linked_wallets || [];
  return linked.some((name) => name && name !== user.wallet_name);
}

function activeWalletForUser(user) {
  return (
    user?.active_wallet ||
    user?.primary_receive_wallet ||
    user?.wallet_name ||
    null
  );
}

function vpsRpcActive(settings) {
  return settings?.rpcProfile === "vps" && settings?.rpcHost && settings.rpcHost !== "127.0.0.1";
}

function prefersLocalNodeRpc(settings) {
  return settings?.walletRpcPreference === "local" || settings?.rpcProfile === "local";
}

function shouldAutoApplyVps(settings) {
  return !prefersLocalNodeRpc(settings);
}

module.exports = {
  walletsForUser,
  walletNamesForUser,
  useVpsWalletRpc,
  requiresVpsRpc,
  activeWalletForUser,
  vpsRpcActive,
  prefersLocalNodeRpc,
  shouldAutoApplyVps,
};
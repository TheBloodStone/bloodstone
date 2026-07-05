const $w = (sel) => document.querySelector(sel);

const walletEls = {
  loginPanel: $w("#wallet-login-panel"),
  walletPanel: $w("#wallet-main-panel"),
  loginForm: $w("#wallet-login-form"),
  loginError: $w("#wallet-login-error"),
  loginStatus: $w("#wallet-login-status"),
  loginSubmit: $w("#wallet-login-submit"),
  loginUsername: $w("#wallet-login-username"),
  loginPassword: $w("#wallet-login-password"),
  signedInAs: $w("#wallet-signed-in-as"),
  walletSelect: $w("#wallet-active-select"),
  btnLogout: $w("#wallet-btn-logout"),
  balance: $w("#wallet-balance"),
  unconfirmed: $w("#wallet-unconfirmed"),
  walletName: $w("#wallet-name"),
  primaryAddress: $w("#wallet-primary-address"),
  addressList: $w("#wallet-address-list"),
  txList: $w("#wallet-tx-list"),
  unlockForm: $w("#wallet-unlock-form"),
  unlockError: $w("#wallet-unlock-error"),
  sendForm: $w("#wallet-send-form"),
  sendError: $w("#wallet-send-error"),
  sendResult: $w("#wallet-send-result"),
  btnRefresh: $w("#wallet-btn-refresh"),
  btnNewAddress: $w("#wallet-btn-new-address"),
  vpsAlert: $w("#wallet-vps-alert"),
  vpsAlertText: $w("#wallet-vps-alert-text"),
};

let currentUser = null;
let walletSwitchBusy = false;

function activeWalletName(user) {
  return (
    user?.active_wallet ||
    user?.primary_receive_wallet ||
    user?.wallet_name ||
    null
  );
}

function walletNamesForUser(user) {
  if (user?.available_wallets?.length) {
    return user.available_wallets;
  }
  return [
    ...new Set(
      [
        user?.wallet_name,
        user?.primary_receive_wallet,
        ...(user?.linked_wallets || []),
      ].filter(Boolean)
    ),
  ].sort((a, b) => a.localeCompare(b));
}

function formatAmount(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return "—";
  }
  return n.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

function formatTxCategory(category) {
  switch (category) {
    case "generate":
      return "mined";
    case "immature":
      return "mining (immature)";
    case "orphan":
      return "stale block";
    default:
      return category || "—";
  }
}

function setLoginBusy(busy, message = "") {
  if (walletEls.loginSubmit) {
    walletEls.loginSubmit.disabled = busy;
    walletEls.loginSubmit.textContent = busy ? "Signing in…" : "Sign in";
  }
  if (walletEls.loginStatus) {
    walletEls.loginStatus.textContent = message;
  }
}

function showLoginError(message) {
  if (!walletEls.loginError) {
    return;
  }
  walletEls.loginError.textContent = message || "";
  walletEls.loginError.classList.remove("form-success");
}

function showLogin() {
  walletEls.loginPanel?.classList.remove("hidden");
  walletEls.walletPanel?.classList.add("hidden");
}

function fillWalletSelect(user, selectedOverride = null) {
  if (!walletEls.walletSelect) {
    return;
  }
  const names = walletNamesForUser(user);
  const active = selectedOverride || activeWalletName(user) || names[0] || "";
  walletEls.walletSelect.innerHTML = "";
  if (!names.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No wallets";
    walletEls.walletSelect.appendChild(opt);
    walletEls.walletSelect.disabled = true;
    walletEls.walletSelect.title = "No wallets linked to this account";
    return;
  }
  for (const name of names) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    walletEls.walletSelect.appendChild(opt);
  }
  if (active && names.includes(active)) {
    walletEls.walletSelect.value = active;
  }
  walletEls.walletSelect.disabled = names.length <= 1 || walletSwitchBusy;
  walletEls.walletSelect.title =
    names.length <= 1
      ? "Only one wallet on this account"
      : "Switch which wallet to view and use";
}

function showWallet(user) {
  currentUser = user;
  walletEls.loginPanel?.classList.add("hidden");
  walletEls.walletPanel?.classList.remove("hidden");
  if (walletEls.signedInAs) {
    walletEls.signedInAs.textContent = user.username;
  }
  fillWalletSelect(user);
}

function showVpsAlert(message, visible = true) {
  if (!walletEls.vpsAlert) {
    return;
  }
  walletEls.vpsAlert.classList.toggle("hidden", !visible);
  if (visible && walletEls.vpsAlertText && message) {
    walletEls.vpsAlertText.textContent = message;
  }
}

async function refreshWallet() {
  if (!currentUser) {
    return;
  }
  if (walletEls.btnRefresh) {
    walletEls.btnRefresh.disabled = true;
  }
  const summaryResult = await window.bloodstone.walletSummary();
  if (walletEls.btnRefresh) {
    walletEls.btnRefresh.disabled = false;
  }
  if (!summaryResult.ok) {
    if (summaryResult.needsVps) {
      showVpsAlert(summaryResult.message, true);
    }
    if (walletEls.sendError) {
      walletEls.sendError.textContent = summaryResult.message;
    }
    return;
  }
  showVpsAlert("", false);
  const { summary } = summaryResult;
  if (walletEls.balance) {
    walletEls.balance.textContent = `${formatAmount(summary.balance)} STONE`;
  }
  if (walletEls.unconfirmed) {
    walletEls.unconfirmed.textContent = formatAmount(summary.unconfirmed);
  }
  if (walletEls.walletName) {
    walletEls.walletName.textContent = summary.wallet;
  }

  const addrResult = await window.bloodstone.walletAddresses();
  if (addrResult.ok) {
    if (walletEls.primaryAddress) {
      walletEls.primaryAddress.textContent =
        addrResult.primary || addrResult.addresses[0]?.address || "—";
    }
    if (walletEls.addressList) {
      walletEls.addressList.innerHTML = addrResult.addresses
        .slice(0, 12)
        .map(
          (row) =>
            `<tr><td class="mono">${row.address}</td><td>${formatAmount(row.amount)}</td></tr>`
        )
        .join("");
    }
  }

  const txResult = await window.bloodstone.walletTransactions({ count: 1000 });
  if (txResult.ok && walletEls.txList) {
    const orphanCount = txResult.transactions.filter((tx) => tx.category === "orphan").length;
    const visible = txResult.transactions.slice(0, 15);
    walletEls.txList.innerHTML = visible
      .map((tx) => {
        const amount = Number(tx.amount);
        const cls = amount >= 0 ? "tx-in" : "tx-out";
        return `<tr class="${cls}"><td>${formatTxCategory(tx.category || tx.type)}</td><td class="mono">${formatAmount(amount)}</td><td>${tx.confirmations ?? 0}</td><td class="mono truncate">${tx.txid || "—"}</td></tr>`;
      })
      .join("");
    const txPanel = walletEls.txList.closest(".info-card");
    let orphanNote = txPanel?.querySelector("#wallet-orphan-note");
    if (orphanCount > 0) {
      if (!orphanNote && txPanel) {
        orphanNote = document.createElement("p");
        orphanNote.id = "wallet-orphan-note";
        orphanNote.className = "muted small";
        txPanel.appendChild(orphanNote);
      }
      if (orphanNote) {
        orphanNote.textContent =
          `${orphanCount} stale solo-mined block${orphanCount === 1 ? "" : "s"} listed last in full history — ` +
          "they never made the main chain and do not affect your balance.";
      }
    } else if (orphanNote) {
      orphanNote.remove();
    }
  }
}

walletEls.loginForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  showLoginError("");
  setLoginBusy(true, "Contacting Bloodstone web wallet…");
  const username = walletEls.loginUsername?.value?.trim();
  const password = walletEls.loginPassword?.value || "";
  try {
    if (!window.bloodstone?.walletLogin) {
      throw new Error("Wallet UI failed to initialize. Restart the app.");
    }
    const result = await window.bloodstone.walletLogin(username, password);
    if (!result.ok) {
      showLoginError(result.message || "Login failed");
      return;
    }
    showWallet(result.user);
    if (result.message) {
      if (result.vpsAutoApplied && walletEls.loginError) {
        walletEls.loginError.textContent = result.message;
        walletEls.loginError.classList.add("form-success");
      } else if (result.message && walletEls.sendError) {
        walletEls.sendError.textContent = result.message;
      }
    }
    setLoginBusy(true, "Loading wallet balances…");
    await refreshWallet();
  } catch (err) {
    showLoginError(err?.message || String(err));
  } finally {
    setLoginBusy(false);
  }
});

walletEls.walletSelect?.addEventListener("change", async () => {
  const walletName = walletEls.walletSelect?.value;
  const previousWallet = activeWalletName(currentUser);
  if (!walletName || !currentUser || walletName === previousWallet || walletSwitchBusy) {
    if (previousWallet) {
      fillWalletSelect(currentUser);
    }
    return;
  }
  walletSwitchBusy = true;
  fillWalletSelect(currentUser, walletName);
  if (walletEls.walletName) {
    walletEls.walletName.textContent = walletName;
  }
  if (walletEls.sendError) {
    walletEls.sendError.textContent = `Switching to ${walletName}…`;
  }
  try {
    const result = await window.bloodstone.walletSwitch(walletName);
    if (!result.ok) {
      alert(result.message || "Could not switch wallet.");
      if (result.needsVps) {
        showVpsAlert(result.message, true);
      }
      fillWalletSelect(currentUser);
      return;
    }
    currentUser = result.user;
    fillWalletSelect(currentUser);
    showVpsAlert("", false);
    await refreshWallet();
  } catch (err) {
    alert(err?.message || String(err));
    fillWalletSelect(currentUser);
  } finally {
    walletSwitchBusy = false;
    if (walletEls.sendError?.textContent?.startsWith("Switching to ")) {
      walletEls.sendError.textContent = "";
    }
    fillWalletSelect(currentUser);
  }
});

walletEls.btnLogout?.addEventListener("click", async () => {
  await window.bloodstone.walletLogout();
  currentUser = null;
  showLogin();
});

walletEls.btnRefresh?.addEventListener("click", async () => {
  await refreshWallet();
  if (typeof window.refreshGift === "function") {
    await window.refreshGift();
  }
});

walletEls.btnNewAddress?.addEventListener("click", async () => {
  const result = await window.bloodstone.walletNewAddress();
  if (!result.ok) {
    alert(result.message);
    return;
  }
  await refreshWallet();
});

walletEls.unlockForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (walletEls.unlockError) {
    walletEls.unlockError.textContent = "";
  }
  const passphrase = new FormData(walletEls.unlockForm).get("passphrase");
  const result = await window.bloodstone.walletUnlock(passphrase, 1800);
  if (!result.ok) {
    if (walletEls.unlockError) {
      walletEls.unlockError.textContent = result.message;
    }
    return;
  }
  walletEls.unlockForm.reset();
  await refreshWallet();
});

walletEls.sendForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (walletEls.sendError) {
    walletEls.sendError.textContent = "";
  }
  if (walletEls.sendResult) {
    walletEls.sendResult.textContent = "";
  }
  const data = new FormData(walletEls.sendForm);
  const result = await window.bloodstone.walletSend({
    address: data.get("address"),
    amount: data.get("amount"),
    comment: data.get("comment") || "",
    passphrase: data.get("passphrase") || "",
  });
  if (!result.ok) {
    if (walletEls.sendError) {
      walletEls.sendError.textContent = result.message;
    }
    return;
  }
  if (walletEls.sendResult) {
    walletEls.sendResult.textContent = `Sent — txid: ${result.txid}`;
  }
  walletEls.sendForm.reset();
  await refreshWallet();
});

window.refreshWallet = refreshWallet;

(async function initWallet() {
  try {
    const session = await window.bloodstone.walletSession();
    if (session) {
      showWallet(session);
      await refreshWallet();
    } else {
      showLogin();
    }
  } catch (err) {
    showLogin();
    showLoginError(err?.message || String(err));
  }
})();
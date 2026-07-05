const $i = (sel) => document.querySelector(sel);

const importEls = {
  form: $i("#wallet-import-form"),
  wallet: $i("#import-wallet-name"),
  username: $i("#import-web-username"),
  password: $i("#import-web-password"),
  passphrase: $i("#import-wallet-passphrase"),
  status: $i("#import-status"),
  error: $i("#import-error"),
  btnListVps: $i("#btn-import-list-vps"),
  btnListUser: $i("#btn-import-list-user"),
  localNodeHint: $i("#import-local-node-hint"),
};

function setImportStatus(text, isError = false) {
  if (importEls.status) {
    importEls.status.textContent = text;
    importEls.status.classList.toggle("form-error", isError);
    importEls.status.classList.toggle("form-success", !isError && !!text);
  }
}

function fillWalletSelect(names) {
  if (!importEls.wallet) {
    return;
  }
  const current = importEls.wallet.value;
  importEls.wallet.innerHTML = "";
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = "— select —";
  importEls.wallet.appendChild(blank);
  for (const name of names) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    importEls.wallet.appendChild(opt);
  }
  if (current && names.includes(current)) {
    importEls.wallet.value = current;
  }
}

async function updateListVpsButtonState() {
  if (!importEls.btnListVps) {
    return;
  }
  const ready = await window.bloodstone.importLocalNodeReady();
  const enabled = !!ready.reachable;
  importEls.btnListVps.disabled = !enabled;
  importEls.btnListVps.title = enabled
    ? "List wallets on the VPS (local node must be running)"
    : ready.message || "Start local node first";
  if (importEls.localNodeHint) {
    importEls.localNodeHint.textContent = enabled
      ? "Local node is running — you can list VPS wallets to import."
      : ready.message || "Start your local node before listing VPS wallets.";
    importEls.localNodeHint.classList.toggle("form-error", !enabled);
  }
}

importEls.btnListVps?.addEventListener("click", async () => {
  const ready = await window.bloodstone.importLocalNodeReady();
  if (!ready.reachable) {
    setImportStatus(ready.message, true);
    return;
  }
  setImportStatus("Loading VPS wallet list…");
  const result = await window.bloodstone.importListVpsWallets();
  if (!result.ok) {
    setImportStatus(result.message, true);
    return;
  }
  fillWalletSelect(result.wallets || []);
  setImportStatus(`Found ${result.wallets.length} wallet(s) on VPS.`);
});

importEls.btnListUser?.addEventListener("click", async () => {
  const username = importEls.username?.value?.trim();
  const password = importEls.password?.value || "";
  if (!username || !password) {
    setImportStatus("Enter web wallet username and password first.", true);
    return;
  }
  setImportStatus("Loading your wallets…");
  const result = await window.bloodstone.importListUserWallets(username, password);
  if (!result.ok) {
    setImportStatus(result.message, true);
    return;
  }
  fillWalletSelect(result.wallets || []);
  setImportStatus(`You can import: ${result.wallets.join(", ")}`);
});

importEls.form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (importEls.error) {
    importEls.error.textContent = "";
  }
  const ready = await window.bloodstone.importLocalNodeReady();
  if (!ready.reachable) {
    setImportStatus(ready.message, true);
    return;
  }
  const walletName = importEls.wallet?.value?.trim();
  const passphrase = importEls.passphrase?.value || "";
  const username = importEls.username?.value?.trim();
  const password = importEls.password?.value || "";
  if (!walletName) {
    setImportStatus("Select or enter a wallet name.", true);
    return;
  }
  if (!passphrase) {
    setImportStatus("Wallet encryption passphrase is required.", true);
    return;
  }
  setImportStatus("Exporting from VPS and importing locally… this may take a minute.");
  const result = await window.bloodstone.importWalletFromVps({
    walletName,
    passphrase,
    username,
    password,
  });
  if (!result.ok) {
    setImportStatus(result.message, true);
    return;
  }
  setImportStatus(result.message || "Import complete.");
  importEls.passphrase.value = "";
});

if (window.bloodstone.onStatus) {
  window.bloodstone.onStatus(() => {
    void updateListVpsButtonState();
  });
}

void updateListVpsButtonState();
setInterval(() => {
  void updateListVpsButtonState();
}, 5000);

(async function prefillImportForm() {
  if (typeof window.bloodstone.walletSession !== "function") {
    return;
  }
  const session = await window.bloodstone.walletSession();
  if (session && importEls.username && !importEls.username.value) {
    importEls.username.value = session.username || "";
  }
  if (session) {
    const names = session.available_wallets?.length
      ? session.available_wallets
      : [
          ...new Set(
            [
              session.wallet_name,
              session.primary_receive_wallet,
              ...(session.linked_wallets || []),
            ].filter(Boolean)
          ),
        ].sort();
    if (names.length) {
      fillWalletSelect(names);
    }
  }
})();
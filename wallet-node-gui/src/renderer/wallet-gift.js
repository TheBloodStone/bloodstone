const $g = (sel) => document.querySelector(sel);

const giftEls = {
  overviewView: $g("#wallet-overview-view"),
  giftView: $g("#wallet-gift-view"),
  innerTabs: document.querySelectorAll(".wallet-inner-tab"),
  activeCount: $g("#gift-active-count"),
  activeEscrow: $g("#gift-active-escrow"),
  primaryAddress: $g("#gift-primary-address"),
  activeWallet: $g("#gift-active-wallet"),
  createForm: $g("#gift-create-form"),
  createPassHint: $g("#gift-create-pass-hint"),
  createPassphrase: $g("#gift-create-passphrase"),
  createMin: $g("#gift-create-min"),
  createError: $g("#gift-create-error"),
  createResult: $g("#gift-create-result"),
  createSubmit: $g("#gift-create-submit"),
  createdBox: $g("#gift-created-box"),
  createdCode: $g("#gift-created-code"),
  btnCopyCode: $g("#gift-btn-copy-code"),
  redeemForm: $g("#gift-redeem-form"),
  redeemError: $g("#gift-redeem-error"),
  redeemResult: $g("#gift-redeem-result"),
  createdPanel: $g("#gift-created-panel"),
  createdList: $g("#gift-created-list"),
  redeemedPanel: $g("#gift-redeemed-panel"),
  redeemedList: $g("#gift-redeemed-list"),
};

let giftViewActive = false;
let referralsViewActive = false;

function formatGiftAmount(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return "—";
  }
  return n.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

function showWalletView(view) {
  giftViewActive = view === "gift";
  referralsViewActive = view === "referrals";
  const subViewActive = giftViewActive || referralsViewActive;
  giftEls.overviewView?.classList.toggle("hidden", subViewActive);
  giftEls.giftView?.classList.toggle("hidden", !giftViewActive);
  document.getElementById("wallet-referrals-view")?.classList.toggle(
    "hidden",
    !referralsViewActive
  );
  for (const tab of giftEls.innerTabs) {
    tab.classList.toggle("active", tab.dataset.walletView === view);
  }
  if (giftViewActive) {
    refreshGift();
  }
  if (referralsViewActive && typeof window.refreshReferrals === "function") {
    window.refreshReferrals();
  }
}

function setGiftPassphraseVisible(visible) {
  giftEls.createPassHint?.classList.toggle("hidden", !visible);
  giftEls.createPassphrase?.classList.toggle("hidden", !visible);
  if (giftEls.createPassphrase) {
    giftEls.createPassphrase.required = visible;
  }
}

function hideCreatedCodeBox() {
  giftEls.createdBox?.classList.add("hidden");
  if (giftEls.createdCode) {
    giftEls.createdCode.textContent = "";
  }
}

async function revealGiftCode(btn) {
  const createdAt = btn.getAttribute("data-created-at");
  const row = btn.closest("tr");
  const maskEl = row?.querySelector(".gift-code-mask");
  if (!createdAt || !maskEl || !window.bloodstone?.walletGiftReveal) {
    return;
  }
  btn.disabled = true;
  btn.textContent = "…";
  try {
    const result = await window.bloodstone.walletGiftReveal({ created_at: Number(createdAt) });
    if (!result.ok) {
      maskEl.title = result.message || "Could not reveal code.";
      btn.disabled = false;
      btn.textContent = "Reveal";
      return;
    }
    maskEl.textContent = result.code;
    maskEl.classList.add("gift-code-revealed");
    btn.textContent = "Copy";
    btn.disabled = false;
    btn.onclick = async () => {
      try {
        await navigator.clipboard.writeText(result.code);
        btn.textContent = "Copied!";
      } catch (_) {
        alert(result.code);
      }
    };
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Reveal";
    maskEl.title = err?.message || String(err);
  }
}

async function refreshGift() {
  if (!window.bloodstone?.walletGiftStatus) {
    return;
  }
  const statusResult = await window.bloodstone.walletGiftStatus();
  if (!statusResult.ok) {
    if (giftEls.createError) {
      giftEls.createError.textContent = statusResult.message || "Could not load gift codes.";
    }
    return;
  }
  if (giftEls.createError) {
    giftEls.createError.textContent = "";
  }
  if (giftEls.activeCount) {
    const count = Number(statusResult.your_active_count || 0);
    giftEls.activeCount.textContent = String(count);
  }
  if (giftEls.activeEscrow) {
    giftEls.activeEscrow.textContent = `${formatGiftAmount(statusResult.your_active_escrow)} STONE`;
  }
  if (giftEls.primaryAddress) {
    giftEls.primaryAddress.textContent = statusResult.primary_address || "—";
  }
  if (giftEls.activeWallet) {
    giftEls.activeWallet.textContent = statusResult.active_wallet || "—";
  }
  if (giftEls.createMin) {
    giftEls.createMin.textContent = `Minimum ${formatGiftAmount(statusResult.min_amount)} STONE.`;
  }
  setGiftPassphraseVisible(!!statusResult.needs_passphrase);

  const listResult = await window.bloodstone.walletGiftList();
  if (!listResult.ok) {
    return;
  }
  const created = listResult.created || [];
  const redeemed = listResult.redeemed || [];

  if (giftEls.createdPanel) {
    giftEls.createdPanel.classList.toggle("hidden", created.length === 0);
  }
  if (giftEls.createdList) {
    giftEls.createdList.innerHTML = created
      .map(
        (row) => {
          const revealBtn = row.can_reveal
            ? `<button type="button" class="btn btn-ghost btn-sm gift-reveal-btn" data-created-at="${row.created_at}">Reveal</button>`
            : "";
          return (
            `<tr><td class="mono"><span class="gift-code-mask">${row.code}</span>${revealBtn}</td>` +
            `<td>${formatGiftAmount(row.amount)}</td>` +
            `<td><span class="gift-badge gift-badge-${row.status}">${row.status}</span></td>` +
            `<td>${row.created_at_fmt || "—"}</td>` +
            `<td>${row.redeemed_by_username || "—"}</td></tr>`
          );
        }
      )
      .join("");
    giftEls.createdList.querySelectorAll(".gift-reveal-btn").forEach((btn) => {
      btn.addEventListener("click", () => revealGiftCode(btn));
    });
  }

  if (giftEls.redeemedPanel) {
    giftEls.redeemedPanel.classList.toggle("hidden", redeemed.length === 0);
  }
  if (giftEls.redeemedList) {
    giftEls.redeemedList.innerHTML = redeemed
      .map(
        (row) =>
          `<tr><td class="mono">${row.code}</td><td>${formatGiftAmount(row.amount)}</td>` +
          `<td>${row.creator_username || "—"}</td>` +
          `<td>${row.redeemed_at_fmt || "—"}</td>` +
          `<td class="mono truncate">${row.redeem_txid_short || row.redeem_txid || "—"}</td></tr>`
      )
      .join("");
  }
}

for (const tab of giftEls.innerTabs) {
  tab.addEventListener("click", () => {
    showWalletView(tab.dataset.walletView || "overview");
  });
}

giftEls.createForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideCreatedCodeBox();
  if (giftEls.createError) {
    giftEls.createError.textContent = "";
  }
  if (giftEls.createResult) {
    giftEls.createResult.textContent = "";
  }
  const data = new FormData(giftEls.createForm);
  if (giftEls.createSubmit) {
    giftEls.createSubmit.disabled = true;
    giftEls.createSubmit.textContent = "Creating…";
  }
  try {
    const result = await window.bloodstone.walletGiftCreate({
      amount: data.get("amount"),
      passphrase: data.get("passphrase") || "",
    });
    if (!result.ok) {
      if (giftEls.createError) {
        giftEls.createError.textContent = result.message || "Could not create gift code.";
      }
      if (result.needsPassphrase) {
        setGiftPassphraseVisible(true);
      }
      return;
    }
    if (giftEls.createResult) {
      giftEls.createResult.textContent =
        `Created ${formatGiftAmount(result.amount)} STONE gift code. Fund tx: ${result.fund_txid_short || result.fund_txid}`;
    }
    if (giftEls.createdCode && giftEls.createdBox) {
      giftEls.createdCode.textContent = result.code;
      giftEls.createdBox.classList.remove("hidden");
    }
    giftEls.createForm.reset();
    await refreshGift();
  } catch (err) {
    if (giftEls.createError) {
      giftEls.createError.textContent = err?.message || String(err);
    }
  } finally {
    if (giftEls.createSubmit) {
      giftEls.createSubmit.disabled = false;
      giftEls.createSubmit.textContent = "Create gift code";
    }
  }
});

giftEls.redeemForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (giftEls.redeemError) {
    giftEls.redeemError.textContent = "";
  }
  if (giftEls.redeemResult) {
    giftEls.redeemResult.textContent = "";
  }
  const data = new FormData(giftEls.redeemForm);
  try {
    const result = await window.bloodstone.walletGiftRedeem({
      code: data.get("code"),
    });
    if (!result.ok) {
      if (giftEls.redeemError) {
        giftEls.redeemError.textContent = result.message || "Could not redeem gift code.";
      }
      return;
    }
    if (giftEls.redeemResult) {
      giftEls.redeemResult.textContent =
        `Redeemed ${formatGiftAmount(result.amount)} STONE — txid: ${result.txid_short || result.txid}`;
    }
    giftEls.redeemForm.reset();
    await refreshGift();
    if (typeof window.refreshWallet === "function") {
      await window.refreshWallet();
    }
  } catch (err) {
    if (giftEls.redeemError) {
      giftEls.redeemError.textContent = err?.message || String(err);
    }
  }
});

giftEls.btnCopyCode?.addEventListener("click", async () => {
  const code = giftEls.createdCode?.textContent?.trim();
  if (!code) {
    return;
  }
  try {
    await navigator.clipboard.writeText(code);
    giftEls.btnCopyCode.textContent = "Copied!";
    setTimeout(() => {
      if (giftEls.btnCopyCode) {
        giftEls.btnCopyCode.textContent = "Copy code";
      }
    }, 2000);
  } catch (_) {
    alert(code);
  }
});

window.refreshGift = refreshGift;
window.showWalletView = showWalletView;
const $r = (sel) => document.querySelector(sel);

const referralEls = {
  statJoined: $r("#referral-stat-joined"),
  statSignups: $r("#referral-stat-signups"),
  statLinked: $r("#referral-stat-linked"),
  statClicks: $r("#referral-stat-clicks"),
  link: $r("#referral-link"),
  code: $r("#referral-code"),
  btnCopy: $r("#referral-btn-copy"),
  btnDiscord: $r("#referral-btn-discord"),
  btnServer: $r("#referral-btn-server"),
  discordStatus: $r("#referral-discord-status"),
  error: $r("#referral-error"),
  listPanel: $r("#referral-list-panel"),
  rows: $r("#referral-rows"),
  liveFeed: $r("#referral-live-feed"),
};

let referralPollTimer = null;
let inviteUrl = "";

function statusBadgeClass(status) {
  return `referral-badge referral-badge-${String(status || "").replace(/_/g, "-")}`;
}

function renderStats(stats) {
  if (!stats) {
    return;
  }
  if (referralEls.statJoined) {
    referralEls.statJoined.textContent = stats.discord_joined ?? 0;
  }
  if (referralEls.statSignups) {
    referralEls.statSignups.textContent = stats.signups ?? 0;
  }
  if (referralEls.statLinked) {
    referralEls.statLinked.textContent = stats.discord_linked ?? 0;
  }
  if (referralEls.statClicks) {
    referralEls.statClicks.textContent = stats.clicks ?? 0;
  }
}

function renderReferrals(rows) {
  const list = rows || [];
  referralEls.listPanel?.classList.toggle("hidden", list.length === 0);
  if (!referralEls.rows) {
    return;
  }
  referralEls.rows.innerHTML = list
    .map(
      (row) =>
        `<tr><td class="mono">${row.referred_username || "—"}</td>` +
        `<td><span class="${statusBadgeClass(row.status)}">${String(row.status || "").replace(/_/g, " ")}</span></td>` +
        `<td>${row.created_at_fmt || "—"}</td>` +
        `<td>${row.discord_joined_at_fmt || "—"}</td></tr>`
    )
    .join("");
}

function renderEvents(events) {
  if (!referralEls.liveFeed) {
    return;
  }
  const list = events || [];
  referralEls.liveFeed.innerHTML = list.length
    ? list
        .map((event) => {
          const who =
            event.referred_username && event.referred_username !== "—"
              ? event.referred_username
              : event.referrer_username || "Someone";
          const when = event.created_at_fmt || "";
          return `<li><span class="mono">${event.event_type}</span> — ${who}` +
            (when ? ` <span class="muted small">${when}</span>` : "") +
            `</li>`;
        })
        .join("")
    : '<li class="muted">No activity yet.</li>';
}

function renderDashboard(data) {
  if (referralEls.link) {
    referralEls.link.textContent = data.referral_link || "—";
  }
  if (referralEls.code) {
    referralEls.code.textContent = data.code || "—";
  }
  inviteUrl = data.invite_url || "";
  renderStats(data.stats);
  renderReferrals(data.referrals);

  const oauthReady = !!data.oauth_ready;
  referralEls.btnDiscord?.classList.toggle("hidden", !oauthReady);
  referralEls.btnServer?.classList.toggle("hidden", !inviteUrl);

  const discord = data.discord;
  if (referralEls.discordStatus) {
    if (discord) {
      referralEls.discordStatus.textContent =
        `Linked as ${discord.discord_global_name || discord.discord_username || "Discord user"}`;
    } else if (oauthReady) {
      referralEls.discordStatus.textContent =
        "Connect Discord so we can verify when invited users join the server.";
    } else {
      referralEls.discordStatus.textContent =
        "Discord OAuth is not configured yet — ask an admin to finish setup.";
    }
  }
}

async function refreshReferralsLive() {
  if (!window.bloodstone?.walletReferralsLive) {
    return;
  }
  const result = await window.bloodstone.walletReferralsLive();
  if (!result.ok) {
    return;
  }
  renderStats(result.stats);
  renderEvents(result.events);
}

async function refreshReferrals() {
  if (!window.bloodstone?.walletReferralsDashboard) {
    return;
  }
  if (referralEls.error) {
    referralEls.error.textContent = "";
  }
  const result = await window.bloodstone.walletReferralsDashboard();
  if (!result.ok) {
    if (referralEls.error) {
      referralEls.error.textContent = result.message || "Could not load referrals.";
    }
    return;
  }
  renderDashboard(result);
  await refreshReferralsLive();
}

function startReferralPolling() {
  stopReferralPolling();
  referralPollTimer = setInterval(() => {
    if (typeof window.showWalletView === "function") {
      refreshReferralsLive();
    }
  }, 5000);
}

function stopReferralPolling() {
  if (referralPollTimer) {
    clearInterval(referralPollTimer);
    referralPollTimer = null;
  }
}

referralEls.btnCopy?.addEventListener("click", async () => {
  const link = referralEls.link?.textContent?.trim();
  if (!link || link === "—") {
    return;
  }
  try {
    await navigator.clipboard.writeText(link);
    referralEls.btnCopy.textContent = "Copied!";
    setTimeout(() => {
      if (referralEls.btnCopy) {
        referralEls.btnCopy.textContent = "Copy link";
      }
    }, 2000);
  } catch (_) {
    alert(link);
  }
});

referralEls.btnDiscord?.addEventListener("click", async () => {
  if (!window.bloodstone?.walletReferralsDiscordConnect) {
    return;
  }
  if (referralEls.error) {
    referralEls.error.textContent = "";
  }
  const result = await window.bloodstone.walletReferralsDiscordConnect();
  if (!result.ok) {
    if (referralEls.error) {
      referralEls.error.textContent = result.message || "Could not start Discord sign-in.";
    }
    return;
  }
  if (result.url && window.bloodstone.openUrl) {
    await window.bloodstone.openUrl(result.url);
  }
});

referralEls.btnServer?.addEventListener("click", async () => {
  if (!inviteUrl || !window.bloodstone?.openUrl) {
    return;
  }
  await window.bloodstone.openUrl(inviteUrl);
});

window.refreshReferrals = refreshReferrals;
startReferralPolling();
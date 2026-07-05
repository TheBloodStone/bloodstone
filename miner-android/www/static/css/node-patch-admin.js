/** Master Creator: upload / publish / apply live node patch bundles. */

function apiUrl(path) {
  const prefix = document.body?.dataset?.urlPrefix || "";
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${prefix}${normalized}`;
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

async function refreshNodePatchStatus() {
  const statusEl = document.getElementById("node-patch-status");
  if (!statusEl) return;
  try {
    const res = await fetch(apiUrl("/admin/api/node-patch/status"), { cache: "no-store" });
    const data = await res.json();
    if (!res.ok || !data?.ok) throw new Error(data?.error || "status unavailable");
    const active = data.active || {};
    const published = data.published || {};
    const lines = [
      `Applied: ${active.patch_version || "none"}`,
      published.patch_version ? `Published: ${published.patch_version}` : "Published: none",
      active.applied_at
        ? `Last apply: ${new Date(active.applied_at * 1000).toLocaleString()}`
        : "",
    ].filter(Boolean);
    statusEl.textContent = lines.join(" · ");
  } catch (err) {
    statusEl.textContent = `Patch status unavailable (${err.message || err})`;
  }
}

async function postPatchForm(formId, resultId) {
  const form = document.getElementById(formId);
  const resultEl = document.getElementById(resultId);
  if (!form) return;
  const fd = new FormData(form);
  if (resultEl) resultEl.textContent = "Working…";
  try {
    const res = await fetch(form.action, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok || !data?.ok) throw new Error(data?.error || `HTTP ${res.status}`);
    if (resultEl) {
      resultEl.textContent = data.message || data.note || "Done.";
    }
    await refreshNodePatchStatus();
  } catch (err) {
    if (resultEl) resultEl.textContent = err.message || String(err);
  }
}

export function initNodePatchAdmin() {
  const panel = document.getElementById("node-patch-panel");
  if (!panel) return;

  void refreshNodePatchStatus();
  setInterval(refreshNodePatchStatus, 60000);

  panel.querySelector("#node-patch-apply-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    void postPatchForm("node-patch-apply-form", "node-patch-apply-result");
  });

  panel.querySelector("#node-patch-publish-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    void postPatchForm("node-patch-publish-form", "node-patch-publish-result");
  });

  document.getElementById("node-patch-check-updates")?.addEventListener("click", async () => {
    setText("node-patch-auto-result", "Checking…");
    try {
      const res = await fetch(apiUrl("/admin/api/node-patch/auto-apply"), {
        method: "POST",
        cache: "no-store",
      });
      const data = await res.json();
      if (!res.ok || !data?.ok) throw new Error(data?.error || "auto-apply failed");
      setText(
        "node-patch-auto-result",
        data.action === "applied"
          ? `Applied patch ${data.patch_version}`
          : `No update (${data.action || "noop"})`,
      );
      await refreshNodePatchStatus();
    } catch (err) {
      setText("node-patch-auto-result", err.message || String(err));
    }
  });
}
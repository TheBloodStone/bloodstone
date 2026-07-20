/** Master Creator: generate beta tester invite codes (single-use or lifetime). */

function apiUrl(path) {
  const prefix = document.body?.dataset?.urlPrefix || "";
  return `${prefix}${path}`;
}

function setStatus(message, kind = "muted") {
  const el = document.getElementById("beta-codes-admin-status");
  if (!el) return;
  el.textContent = message || "";
  el.className = `muted small ${kind}`.trim();
}

function renderCodes(codes) {
  const list = document.getElementById("beta-codes-admin-list");
  if (!list) return;
  list.innerHTML = "";
  codes.forEach((code) => {
    const li = document.createElement("li");
    li.className = "mono";
    li.textContent = code;
    list.appendChild(li);
  });
}

async function refreshCodeInventory() {
  const tbody = document.getElementById("beta-codes-admin-table");
  if (!tbody) return;
  const res = await fetch(apiUrl("/admin/api/beta-codes?include_redeemed=1"), {
    cache: "no-store",
  });
  const data = await res.json();
  if (!data?.ok) return;
  tbody.innerHTML = "";
  for (const row of data.codes || []) {
    const tr = document.createElement("tr");
    const codeType = row.code_type === "lifetime" ? "lifetime" : "single";
    const redeemed = row.redeemed_at
      ? new Date(row.redeemed_at * 1000).toISOString().slice(0, 16).replace("T", " ")
      : codeType === "lifetime"
        ? "active"
        : "pending";
    tr.innerHTML = `
      <td>${row.id}</td>
      <td>${codeType}</td>
      <td>${row.label || "—"}</td>
      <td>${redeemed}</td>
      <td class="mono small">${row.redeemed_device_id || "—"}</td>
    `;
    tbody.appendChild(tr);
  }
}

export function initBetaCodesAdmin() {
  const btn = document.getElementById("beta-codes-generate-btn");
  if (!btn || btn.dataset.hooked === "1") return;
  btn.dataset.hooked = "1";

  void refreshCodeInventory();

  btn.addEventListener("click", async () => {
    const label = document.getElementById("beta-codes-label")?.value?.trim() || "";
    const codeType = document.getElementById("beta-codes-type")?.value || "single";
    const count = Number(document.getElementById("beta-codes-count")?.value || 1) || 1;
    btn.disabled = true;
    setStatus("Generating…");
    try {
      const res = await fetch(apiUrl("/admin/api/beta-codes/generate"), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ label, count, code_type: codeType }),
      });
      const data = await res.json();
      if (!data?.ok) {
        setStatus("Could not generate beta codes.", "warn");
        return;
      }
      renderCodes(data.codes || []);
      const kindLabel =
        data.code_type === "lifetime" ? "lifetime beta unlock" : "single-use";
      setStatus(
        `Generated ${data.count} ${kindLabel} code(s) — copy now; they are not shown again.`,
        "success",
      );
      await refreshCodeInventory();
    } catch (err) {
      setStatus(err?.message || "Generate failed.", "warn");
    } finally {
      btn.disabled = false;
    }
  });
}
(function () {
  const prefix = document.body.dataset.urlPrefix || "";
  const apiBase = prefix + "/api/pool/rentals";

  function fmtHashrate(hps) {
    if (!hps || hps <= 0) return "0 H/s";
    if (hps >= 1e12) return (hps / 1e12).toFixed(2) + " TH/s";
    if (hps >= 1e9) return (hps / 1e9).toFixed(2) + " GH/s";
    if (hps >= 1e6) return (hps / 1e6).toFixed(2) + " MH/s";
    if (hps >= 1e3) return (hps / 1e3).toFixed(2) + " kH/s";
    return Math.round(hps) + " H/s";
  }

  function fmtBytes(n) {
    const b = Number(n) || 0;
    if (b >= 1073741824) return (b / 1073741824).toFixed(2) + " GiB";
    if (b >= 1048576) return (b / 1048576).toFixed(2) + " MiB";
    if (b >= 1024) return (b / 1024).toFixed(1) + " KiB";
    return b + " B";
  }

  function renderOrders(orders) {
    const el = document.getElementById("rental-orders-list");
    if (!el) return;
    if (!orders || !orders.length) {
      el.innerHTML = '<p class="muted">No rental orders yet.</p>';
      return;
    }
    el.innerHTML = orders
      .map(function (o) {
        const meter = o._meter || {};
        const stratum = o.stratum || {};
        const progress =
          meter.progress_fraction != null
            ? Math.round(meter.progress_fraction * 100) + "%"
            : "—";
        return (
          '<article class="rental-card" data-order-id="' +
          o.id +
          '">' +
          "<h3>" +
          o.id +
          ' <span class="badge">' +
          o.status +
          "</span></h3>" +
          "<dl class='detail-dl compact'>" +
          "<dt>Algo</dt><dd>" +
          o.algo +
          "</dd>" +
          "<dt>Target</dt><dd>" +
          fmtHashrate(o.target_hashrate) +
          "</dd>" +
          "<dt>Delivered</dt><dd>" +
          fmtHashrate(meter.estimated_hashrate) +
          " (" +
          progress +
          ")</dd>" +
          "<dt>Credits</dt><dd>" +
          fmtBytes(o.credit_bytes_available || meter.credit_bytes_available || 0) +
          " available</dd>" +
          "<dt>Renter</dt><dd class='mono'>" +
          (o.renter_wallet || "") +
          "</dd>" +
          (o.worker_prefix
            ? "<dt>Worker</dt><dd class='mono'>" + o.worker_prefix + "</dd>"
            : "") +
          (stratum.url
            ? "<dt>Stratum</dt><dd class='mono'>" +
              stratum.url +
              "</dd>"
            : "") +
          "</dl>" +
          "</article>"
        );
      })
      .join("");
  }

  async function loadOrders() {
    try {
      const resp = await fetch(apiBase + "?limit=30");
      const data = await resp.json();
      const orders = data.orders || [];
      await Promise.all(
        orders.map(async function (o) {
          if (o.status !== "active" && o.status !== "open") return;
          try {
            const m = await fetch(apiBase + "/" + encodeURIComponent(o.id));
            const md = await m.json();
            o._meter = md.meter || {};
          } catch (e) {
            o._meter = {};
          }
        })
      );
      renderOrders(orders);
    } catch (e) {
      const el = document.getElementById("rental-orders-list");
      if (el) el.innerHTML = '<p class="flash flash-error">Failed to load orders.</p>';
    }
  }

  const createForm = document.getElementById("rental-create-form");
  if (createForm) {
    createForm.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      const fd = new FormData(createForm);
      const payload = Object.fromEntries(fd.entries());
      payload.target_hashrate = Number(payload.target_hashrate);
      payload.duration_hours = Number(payload.duration_hours);
      payload.max_price_eth = Number(payload.max_price_eth || 0);
      const out = document.getElementById("rental-create-result");
      try {
        const resp = await fetch(apiBase, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "create failed");
        const order = data.order || {};
        if (out) {
          out.hidden = false;
          out.innerHTML =
            "<strong>Order " +
            order.id +
            " created.</strong> Save your renter token — shown once:<br><code>" +
            (order.renter_token || "") +
            "</code><br>Mesh prefix: <code>" +
            (order.mesh_key_prefix || "") +
            "</code>";
        }
        createForm.reset();
        loadOrders();
      } catch (e) {
        if (out) {
          out.hidden = false;
          out.textContent = e.message || String(e);
        }
      }
    });
  }

  const acceptForm = document.getElementById("rental-accept-form");
  if (acceptForm) {
    acceptForm.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      const fd = new FormData(acceptForm);
      const orderId = fd.get("order_id");
      const seller = fd.get("seller_wallet");
      const out = document.getElementById("rental-accept-result");
      try {
        const resp = await fetch(
          apiBase + "/" + encodeURIComponent(orderId) + "/accept",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ seller_wallet: seller }),
          }
        );
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "accept failed");
        const order = data.order || {};
        const st = order.stratum || {};
        if (out) {
          out.hidden = false;
          out.innerHTML =
            "<strong>Active.</strong> Point your miner at:<br>" +
            "<code>" +
            (st.example_cmd || st.url || "") +
            "</code><br>Worker: <code>" +
            (order.worker_prefix || "") +
            "</code>";
        }
        loadOrders();
      } catch (e) {
        if (out) {
          out.hidden = false;
          out.textContent = e.message || String(e);
        }
      }
    });
  }

  const refreshBtn = document.getElementById("rental-refresh");
  if (refreshBtn) refreshBtn.addEventListener("click", loadOrders);

  loadOrders();
})();
const $r = (sel) => document.querySelector(sel);

const rpcEls = {
  form: $r("#rpc-console-form"),
  method: $r("#rpc-method"),
  params: $r("#rpc-params"),
  wallet: $r("#rpc-wallet"),
  output: $r("#rpc-output"),
  error: $r("#rpc-error"),
  history: $r("#rpc-history"),
  btnClear: $r("#rpc-btn-clear"),
};

const history = [];

function appendHistory(entry) {
  history.unshift(entry);
  if (history.length > 30) {
    history.pop();
  }
  if (rpcEls.history) {
    rpcEls.history.innerHTML = history
      .map(
        (item) =>
          `<button type="button" class="rpc-history-item" data-method="${item.method}" data-params="${encodeURIComponent(item.paramsText)}" data-wallet="${item.wallet || ""}">${item.method}</button>`
      )
      .join("");
    rpcEls.history.querySelectorAll(".rpc-history-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (rpcEls.method) {
          rpcEls.method.value = btn.dataset.method || "";
        }
        if (rpcEls.params) {
          rpcEls.params.value = decodeURIComponent(btn.dataset.params || "[]");
        }
        if (rpcEls.wallet) {
          rpcEls.wallet.value = btn.dataset.wallet || "";
        }
      });
    });
  }
}

function appendOutput(line) {
  if (!rpcEls.output) {
    return;
  }
  rpcEls.output.textContent += `${line}\n`;
  rpcEls.output.scrollTop = rpcEls.output.scrollHeight;
}

rpcEls.form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (rpcEls.error) {
    rpcEls.error.textContent = "";
  }
  const method = rpcEls.method?.value?.trim();
  const paramsText = rpcEls.params?.value?.trim() || "[]";
  const wallet = rpcEls.wallet?.value?.trim() || null;
  if (!method) {
    if (rpcEls.error) {
      rpcEls.error.textContent = "Method is required";
    }
    return;
  }
  let params = [];
  try {
    params = JSON.parse(paramsText);
    if (!Array.isArray(params)) {
      throw new Error("Params must be a JSON array");
    }
  } catch (err) {
    if (rpcEls.error) {
      rpcEls.error.textContent = `Invalid params JSON: ${err.message}`;
    }
    return;
  }

  appendOutput(`> ${method}(${paramsText})${wallet ? ` [wallet=${wallet}]` : ""}`);
  const started = Date.now();
  const result = await window.bloodstone.rpcCall(method, params, wallet);
  const ms = Date.now() - started;
  if (!result.ok) {
    appendOutput(`ERROR (${ms}ms): ${result.message}`);
    if (rpcEls.error) {
      rpcEls.error.textContent = result.message;
    }
    return;
  }
  appendOutput(JSON.stringify(result.result, null, 2));
  appendOutput(`OK (${ms}ms)\n`);
  appendHistory({ method, paramsText, wallet });
});

rpcEls.btnClear?.addEventListener("click", () => {
  if (rpcEls.output) {
    rpcEls.output.textContent = "";
  }
  if (rpcEls.error) {
    rpcEls.error.textContent = "";
  }
});
"""Wave S — unified multi-tenant dashboard (compute + bandwidth + storage)."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

DASHBOARD_FORMAT = "bloodstone_tenant_dashboard/v1"


def _default_tenant() -> str:
    return (os.environ.get("DTN_DEFAULT_TENANT") or "bloodstone").strip()[:64] or "bloodstone"


def _normalize_author(value: str = "") -> str:
    return (value or "").lstrip("@").lower().strip()[:64]


def dashboard_payload(
    *,
    tenant_id: str = "",
    blurt_author: str = "",
    stone_address: str = "",
) -> Dict[str, Any]:
    from chain_mesh import bandwidth_tenant_quota as bw
    from chain_mesh import compute_tenant_quota as compute
    from chain_mesh import storage_tenant_quota as storage

    tid = (tenant_id or _default_tenant()).strip()[:64] or _default_tenant()
    author = _normalize_author(blurt_author)
    addr = (stone_address or "").strip()
    compute_q = compute.tenant_quota(
        tenant_id=tid, blurt_author=author, stone_address=addr
    )
    bandwidth_q = bw.tenant_quota(
        tenant_id=tid, blurt_author=author, stone_address=addr
    )
    storage_q = storage.tenant_quota(
        tenant_id=tid, blurt_author=author, stone_address=addr
    )
    from chain_mesh import tenant_ai_route as troute
    from chain_mesh import tenant_npu_models as tnpu
    from chain_mesh import tenant_route_ledger as tledger
    from chain_mesh import tenant_submit_gate as tgate

    quorum = tgate.quorum_for_author(tenant_id=tid, blurt_author=author) if author else {}
    npu_models = tnpu.list_npu_models(tenant_id=tid, blurt_author=author) if author else []
    submit_gate = (
        tgate.check_submit_allowed(
            tenant_id=tid,
            blurt_author=author,
            stone_address=addr,
        )
        if author
        else {}
    )
    ai_route = (
        troute.resolve_job_inference_spec(
            {"blurt_author": author, "tenant_id": tid, "ai_spec": {}}
        )
        if author
        else {}
    )
    route_history = (
        tledger.list_assignments(tenant_id=tid, blurt_author=author, limit=3)
        if author
        else {}
    )
    return {
        "ok": True,
        "format": DASHBOARD_FORMAT,
        "tenant_id": tid,
        "blurt_author": author,
        "stone_address": addr,
        "rails": {
            "compute": compute_q,
            "bandwidth": bandwidth_q,
            "storage": storage_q,
        },
        "enforce": {
            "compute": bool(compute_q.get("enforce")),
            "bandwidth": bool(bandwidth_q.get("enforce")),
            "storage": bool(storage_q.get("enforce")),
        },
        "quorum": quorum,
        "npu_models": npu_models,
        "submit_gate": submit_gate,
        "ai_route": ai_route,
        "route_history": route_history,
    }


def bind_all_rails(
    *,
    tenant_id: str = "",
    blurt_author: str = "",
    stone_address: str = "",
    flops_cap: int = 0,
    bandwidth_bytes_cap: int = 0,
    storage_bytes_cap: int = 0,
) -> Dict[str, Any]:
    from chain_mesh import bandwidth_tenant_quota as bw
    from chain_mesh import compute_tenant_quota as compute
    from chain_mesh import storage_tenant_quota as storage

    tid = (tenant_id or _default_tenant()).strip()[:64] or _default_tenant()
    author = _normalize_author(blurt_author)
    if not author:
        raise ValueError("blurt_author required")
    addr = (stone_address or "").strip()
    return {
        "ok": True,
        "tenant_id": tid,
        "blurt_author": author,
        "stone_address": addr,
        "compute": compute.bind_tenant_author(
            tenant_id=tid,
            blurt_author=author,
            stone_address=addr,
            flops_cap=int(flops_cap or 0),
        ),
        "bandwidth": bw.bind_tenant_author(
            tenant_id=tid,
            blurt_author=author,
            stone_address=addr,
            bytes_cap=int(bandwidth_bytes_cap or 0),
        ),
        "storage": storage.bind_tenant_author(
            tenant_id=tid,
            blurt_author=author,
            stone_address=addr,
            bytes_cap=int(storage_bytes_cap or 0),
        ),
    }


def resolve_tenant_context(
    *,
    blurt_author: str = "",
    tenant_id: str = "",
    stone_address: str = "",
) -> Dict[str, str]:
    from chain_mesh import tenant_fleet_sync as fleet

    return fleet.resolve_tenant_context(
        blurt_author=blurt_author,
        tenant_id=tenant_id,
        stone_address=stone_address,
    )


def dashboard_page_html() -> str:
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bloodstone Tenant Dashboard</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{ margin: 0; font-family: system-ui, sans-serif; background: #0d1117; color: #e6edf3; }}
    main {{ max-width: 820px; margin: 0 auto; padding: 1.25rem; }}
    h1 {{ font-size: 1.4rem; }}
    .badge {{ display: inline-block; background: #8957e5; color: #fff; font-size: 0.75rem;
      padding: 0.15rem 0.5rem; border-radius: 4px; margin-left: 0.5rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem; }}
    .card {{ border: 1px solid #30363d; border-radius: 8px; padding: 0.85rem; }}
    .card h2 {{ margin: 0 0 0.5rem; font-size: 1rem; color: #58a6ff; }}
    .meta {{ color: #8b949e; font-size: 0.85rem; }}
    input {{ background: #161b22; border: 1px solid #30363d; color: #e6edf3; padding: 0.4rem 0.6rem;
      border-radius: 6px; margin-right: 0.5rem; }}
    button {{ background: #238636; color: #fff; border: none; padding: 0.45rem 0.8rem; border-radius: 6px;
      cursor: pointer; }}
    #status {{ margin: 1rem 0; color: #8b949e; }}
  </style>
</head>
<body>
  <main>
    <h1>Tenant Dashboard <span class="badge">Wave Y</span></h1>
    <p class="meta">Per-author caps, quorum, NPU models, route ledger, and upkeep.</p>
    <div>
      <input id="author" placeholder="blurt author" />
      <input id="stone" placeholder="STONE address (optional)" />
      <button id="load">Load quota</button>
    </div>
    <p id="status">Enter an author and click Load quota.</p>
    <div class="grid" id="rails"></div>
    <div class="card" id="quorum" style="margin-top:0.75rem;display:none"></div>
    <div class="card" id="npu" style="margin-top:0.75rem;display:none"></div>
    <div class="card" id="submit" style="margin-top:0.75rem;display:none"></div>
    <div class="card" id="route" style="margin-top:0.75rem;display:none"></div>
    <div class="card" id="history" style="margin-top:0.75rem;display:none"></div>
    <p class="meta"><a href="{public}/api/convergence/tenant/status">API status</a> ·
      <a href="{public}/api/convergence/status">Convergence</a></p>
  </main>
  <script>
    document.getElementById('load').onclick = () => {{
      const author = document.getElementById('author').value.trim();
      const stone = document.getElementById('stone').value.trim();
      if (!author) {{ document.getElementById('status').textContent = 'Author required'; return; }}
      let url = '/api/convergence/tenant/dashboard?blurt_author=' + encodeURIComponent(author);
      if (stone) url += '&stone_address=' + encodeURIComponent(stone);
      document.getElementById('status').textContent = 'Loading…';
      fetch(url).then(r => r.json()).then(data => {{
        if (!data.ok) {{ document.getElementById('status').textContent = data.error || 'Error'; return; }}
        document.getElementById('status').textContent = '@' + data.blurt_author + ' · tenant ' + data.tenant_id;
        const rails = data.rails || {{}};
        const grid = document.getElementById('rails');
        grid.innerHTML = '';
        for (const [name, q] of Object.entries(rails)) {{
          const card = document.createElement('div');
          card.className = 'card';
          const cap = q.flops_cap || q.bytes_cap || 0;
          const used = q.flops_used || q.bytes_used || 0;
          const rem = q.flops_remaining || q.bytes_remaining || 0;
          const unit = q.flops_cap !== undefined ? 'FLOPS' : 'bytes';
          card.innerHTML = '<h2>' + name + '</h2><div>cap: ' + cap + ' ' + unit +
            '</div><div>used: ' + used + '</div><div>remaining: ' + rem + '</div>';
          grid.appendChild(card);
        }}
        const q = data.quorum || {{}};
        const qEl = document.getElementById('quorum');
        if (q.blurt_author) {{
          qEl.style.display = 'block';
          qEl.innerHTML = '<h2>fleet quorum</h2><div>' + (q.quorum || '?') +
            ' · votes ' + (q.votes_found || 0) + ' · ' +
            (q.satisfied ? 'satisfied ✓' : 'pending') + '</div>';
        }} else {{ qEl.style.display = 'none'; }}
        const npu = data.npu_models || [];
        const nEl = document.getElementById('npu');
        if (npu.length) {{
          nEl.style.display = 'block';
          nEl.innerHTML = '<h2>NPU models</h2>' + npu.map(m =>
            '<div>' + m.runtime + ': ' + (m.model_path || '(auto)') + ' [' + (m.hardware_kind || 'cpu') + ']</div>'
          ).join('');
        }} else {{ nEl.style.display = 'none'; }}
        const sg = data.submit_gate || {{}};
        const sEl = document.getElementById('submit');
        if (sg.blurt_author) {{
          sEl.style.display = 'block';
          sEl.innerHTML = '<h2>submit gate</h2><div>' +
            (sg.allowed ? 'allowed ✓' : 'blocked') + ' · ' + (sg.reason || '') + '</div>';
        }} else {{ sEl.style.display = 'none'; }}
        const ar = data.ai_route || {{}};
        const rEl = document.getElementById('route');
        if (ar.runtime) {{
          rEl.style.display = 'block';
          rEl.innerHTML = '<h2>AI route</h2><div>' + ar.runtime +
            (ar.model_path ? ' · ' + ar.model_path : '') + ' [' + (ar.hardware_kind || 'cpu') + ']</div>';
        }} else {{ rEl.style.display = 'none'; }}
        const hist = (data.route_history || {{}}).assignments || [];
        const hEl = document.getElementById('history');
        if (hist.length) {{
          hEl.style.display = 'block';
          hEl.innerHTML = '<h2>route ledger</h2>' + hist.map(h =>
            '<div>' + (h.provider_id || '?') + ' · ' + (h.runtime || '') +
            ' · ' + (h.route_status || '') + '</div>'
          ).join('');
        }} else {{ hEl.style.display = 'none'; }}
      }}).catch(e => document.getElementById('status').textContent = String(e));
    }};
  </script>
</body>
</html>"""


def status_payload() -> Dict[str, Any]:
    from chain_mesh import bandwidth_tenant_quota as bw
    from chain_mesh import compute_tenant_quota as compute
    from chain_mesh import storage_tenant_quota as storage

    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    compute_s = compute.status_payload()
    bandwidth_s = bw.status_payload()
    storage_s = storage.status_payload()
    return {
        "ok": True,
        "format": DASHBOARD_FORMAT,
        "default_tenant": _default_tenant(),
        "rails": {
            "compute": compute_s,
            "bandwidth": bandwidth_s,
            "storage": storage_s,
        },
        "bindings_total": (
            int(compute_s.get("bindings_count") or 0)
            + int(bandwidth_s.get("bindings_count") or 0)
            + int(storage_s.get("bindings_count") or 0)
        ),
        "apis": {
            "dashboard": f"{public}/api/convergence/tenant/dashboard",
            "dashboard_page": f"{public}/convergence/tenant",
            "bind": f"{public}/api/convergence/tenant/bind",
            "status": f"{public}/api/convergence/tenant/status",
        },
    }
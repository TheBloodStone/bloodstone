"""SpaceXAI (xAI) review for QUASAR witness tip-height disagreements.

Uses XAI_API_KEY + https://api.x.ai/v1 (OpenAI-compatible). Default model: grok-4.5.
When the API is unavailable, falls back to a deterministic heuristic review so
ops still get a structured recommendation without blocking the status path.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import requests

def _xai_api_key() -> str:
    return (os.environ.get("XAI_API_KEY") or "").strip()


def _xai_base_url() -> str:
    return (os.environ.get("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/")


def _xai_model() -> str:
    return (os.environ.get("XAI_MODEL") or "grok-4.5").strip()


def _xai_timeout_sec() -> int:
    return max(5, int(os.environ.get("XAI_TIMEOUT_SEC", "45")))


def _xai_enable() -> bool:
    """Full SpaceXAI review gate — admin panel toggle wins over bare env when set."""
    try:
        import quasar_ai_settings as qas

        return bool(qas.full_ai_review_enabled())
    except Exception:
        return os.environ.get("QUASAR_WITNESS_AI_ENABLE", "1").strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )

_SYSTEM = (
    "You are QUASAR mesh witness arbitrator for the Bloodstone chain. "
    "Witnesses report tip_hash + height. When they disagree on tip height, "
    "assess likely causes (lag, private fork, stale capsule, partition) and "
    "recommend an operator action. Reply with ONLY a single JSON object, no markdown."
)


def _heuristic_review(disagreement: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic review when SpaceXAI is offline or disabled."""
    local_h = int(disagreement.get("local_tip_height") or 0)
    local_hash = str(disagreement.get("local_tip_hash") or "")
    heights = disagreement.get("heights") or []
    # heights: [{height, tip_hash, signers, mesh_keys}, ...] sorted by signers desc
    if not heights:
        return {
            "ok": True,
            "reviewer": "heuristic",
            "recommended_height": local_h,
            "recommended_tip_hash": local_hash,
            "confidence": 0.4,
            "severity": "medium",
            "action": "keep_halt",
            "rationale": "No height clusters available; keep spend halt and re-sample capsules.",
            "factors": ["no_clusters"],
            "prefer": "local",
        }

    top = heights[0]
    top_h = int(top.get("height") or 0)
    top_hash = str(top.get("tip_hash") or "")
    top_signers = int(top.get("signers") or 0)
    second_signers = int(heights[1].get("signers") or 0) if len(heights) > 1 else 0
    max_h = max(int(h.get("height") or 0) for h in heights)
    min_h = min(int(h.get("height") or 0) for h in heights)
    spread = max_h - min_h

    factors: List[str] = [f"height_spread={spread}", f"clusters={len(heights)}"]
    if local_h == top_h and local_hash and local_hash == top_hash:
        factors.append("local_matches_mesh_majority")
        prefer = "local"
        conf = 0.72 if top_signers >= second_signers + 2 else 0.55
        action = "monitor" if top_signers >= 3 and second_signers <= 1 else "keep_halt"
        severity = "medium" if action == "monitor" else "high"
        rationale = (
            f"Local tip height {local_h} matches majority mesh cluster "
            f"({top_signers} signers). Secondary cluster has {second_signers} signers; "
            f"spread {spread} blocks."
        )
    elif local_h == max_h:
        factors.append("local_is_highest")
        prefer = "local"
        conf = 0.6
        action = "keep_halt"
        severity = "high" if second_signers >= 2 else "medium"
        rationale = (
            f"Local tip {local_h} is the highest observed height but mesh clusters disagree "
            f"(majority cluster height={top_h}, signers={top_signers}). Treat as possible lag "
            f"or fork; keep halt until more capsules align."
        )
    elif top_h > local_h and top_signers >= 2:
        factors.append("mesh_ahead_of_local")
        prefer = "mesh_majority"
        conf = 0.58
        action = "escalate"
        severity = "critical"
        rationale = (
            f"Mesh majority reports height {top_h} while local tip is {local_h}. "
            "Possible local lag or isolation — escalate sync check before relaxing policy."
        )
    else:
        prefer = "none"
        conf = 0.45
        action = "keep_halt"
        severity = "high"
        rationale = (
            f"Conflicting tip heights (local={local_h}, majority={top_h}, spread={spread}). "
            "Keep halt and request fresh capsules from lagging mesh keys."
        )

    return {
        "ok": True,
        "reviewer": "heuristic",
        "recommended_height": top_h if prefer == "mesh_majority" else local_h,
        "recommended_tip_hash": top_hash if prefer == "mesh_majority" else local_hash,
        "confidence": round(conf, 3),
        "severity": severity,
        "action": action,
        "rationale": rationale,
        "factors": factors,
        "prefer": prefer,
    }


def _extract_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty model response")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # fenced or trailing prose
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("no JSON object in model response")
    return json.loads(m.group(0))


def _normalize_ai_review(raw: Dict[str, Any], disagreement: Dict[str, Any]) -> Dict[str, Any]:
    local_h = int(disagreement.get("local_tip_height") or 0)
    local_hash = str(disagreement.get("local_tip_hash") or "")
    action = str(raw.get("action") or "keep_halt").strip().lower()
    allowed_actions = {
        "keep_halt",
        "monitor",
        "escalate",
        "prefer_local",
        "prefer_mesh_majority",
    }
    if action not in allowed_actions:
        action = "keep_halt"
    severity = str(raw.get("severity") or "high").strip().lower()
    if severity not in ("low", "medium", "high", "critical"):
        severity = "high"
    try:
        conf = float(raw.get("confidence") if raw.get("confidence") is not None else 0.5)
    except (TypeError, ValueError):
        conf = 0.5
    conf = max(0.0, min(1.0, conf))
    rec_h = raw.get("recommended_height")
    try:
        rec_h = int(rec_h) if rec_h is not None else local_h
    except (TypeError, ValueError):
        rec_h = local_h
    rec_hash = str(raw.get("recommended_tip_hash") or local_hash).strip().lower()
    if len(rec_hash) != 64:
        rec_hash = local_hash
    prefer = str(raw.get("prefer") or "").strip().lower()
    if prefer not in ("local", "mesh_majority", "none"):
        if action in ("prefer_local",):
            prefer = "local"
        elif action in ("prefer_mesh_majority",):
            prefer = "mesh_majority"
        else:
            prefer = "none"
    factors = raw.get("factors")
    if not isinstance(factors, list):
        factors = []
    factors = [str(f)[:120] for f in factors[:12]]
    rationale = str(raw.get("rationale") or raw.get("reason") or "").strip()[:2000]
    if not rationale:
        rationale = "AI review completed without detailed rationale."
    return {
        "ok": True,
        "reviewer": "spacexai",
        "model": _xai_model(),
        "recommended_height": rec_h,
        "recommended_tip_hash": rec_hash,
        "confidence": round(conf, 3),
        "severity": severity,
        "action": action,
        "rationale": rationale,
        "factors": factors,
        "prefer": prefer,
    }


def _call_spacexai(disagreement: Dict[str, Any]) -> Dict[str, Any]:
    api_key = _xai_api_key()
    if not api_key:
        raise RuntimeError("XAI_API_KEY not set")
    model = _xai_model()
    user_payload = {
        "task": "review_witness_tip_height_disagreement",
        "local_tip_height": disagreement.get("local_tip_height"),
        "local_tip_hash": disagreement.get("local_tip_hash"),
        "window_sec": disagreement.get("window_sec"),
        "height_spread": disagreement.get("height_spread"),
        "distinct_heights": disagreement.get("distinct_heights"),
        "distinct_tip_hashes": disagreement.get("distinct_tip_hashes"),
        "total_signers": disagreement.get("total_signers"),
        "heights": disagreement.get("heights"),
        "stale_vs_local": disagreement.get("stale_vs_local"),
        "ahead_of_local": disagreement.get("ahead_of_local"),
        "instructions": {
            "action_enum": [
                "keep_halt",
                "monitor",
                "escalate",
                "prefer_local",
                "prefer_mesh_majority",
            ],
            "severity_enum": ["low", "medium", "high", "critical"],
            "prefer_enum": ["local", "mesh_majority", "none"],
            "response_schema": {
                "recommended_height": "int",
                "recommended_tip_hash": "64-hex or empty",
                "confidence": "0..1",
                "severity": "enum",
                "action": "enum",
                "prefer": "enum",
                "rationale": "string",
                "factors": ["string"],
            },
            "policy": (
                "Never auto-clear a spend halt for multi-signer splits. "
                "Prefer escalate when mesh is ahead of local by 2+ blocks with 2+ signers. "
                "Prefer keep_halt when two height clusters each have >=2 signers."
            ),
        },
    }
    body = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    "Review this witness tip-height disagreement and return JSON only:\n"
                    + json.dumps(user_payload, sort_keys=True)
                ),
            },
        ],
    }
    url = f"{_xai_base_url()}/chat/completions"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=_xai_timeout_sec(),
    )
    resp.raise_for_status()
    data = resp.json()
    content = ""
    choices = data.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        content = str(msg.get("content") or "")
    if not content and data.get("output_text"):
        content = str(data.get("output_text"))
    parsed = _extract_json(content)
    return _normalize_ai_review(parsed, disagreement)


def review_tip_disagreement(disagreement: Dict[str, Any]) -> Dict[str, Any]:
    """Return structured AI (or heuristic) review for a tip-height disagreement."""
    if not disagreement or not disagreement.get("disagreement"):
        return {
            "ok": True,
            "reviewer": "none",
            "recommended_height": int(disagreement.get("local_tip_height") or 0),
            "recommended_tip_hash": str(disagreement.get("local_tip_hash") or ""),
            "confidence": 1.0,
            "severity": "low",
            "action": "monitor",
            "rationale": "No tip-height disagreement detected.",
            "factors": [],
            "prefer": "local",
            "skipped": True,
        }

    if _xai_enable() and _xai_api_key():
        try:
            out = _call_spacexai(disagreement)
            out["fallback"] = False
            return out
        except Exception as exc:
            heuristic = _heuristic_review(disagreement)
            heuristic["fallback"] = True
            heuristic["ai_error"] = str(exc)[:400]
            return heuristic

    heuristic = _heuristic_review(disagreement)
    heuristic["fallback"] = True
    if not _xai_enable():
        heuristic["ai_error"] = "Full QUASAR AI review disabled (admin toggle)"
        heuristic["full_ai_review_enabled"] = False
    else:
        heuristic["ai_error"] = "XAI_API_KEY not set"
        heuristic["full_ai_review_enabled"] = True
    return heuristic

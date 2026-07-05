"""Admin document generators — white papers, release notes, mesh publish helpers."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

DOCS_ROOT = "/root/bloodstone-docs"
DOWNLOADS_DIR = os.environ.get("BLOODSTONE_DOWNLOADS_DIR", "/var/www/bloodstone/downloads")
PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
).rstrip("/")
STATE_PATH = os.environ.get(
    "BLOODSTONE_DOC_GENERATOR_STATE",
    "/var/lib/bloodstone/doc-generator-runs.json",
)
LOG_DIR = "/var/log/bloodstone-doc-generators"
RUN_TIMEOUT_SEC = int(os.environ.get("BLOODSTONE_DOC_GENERATOR_TIMEOUT", "180"))

MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

GENERATORS: List[Dict[str, Any]] = [
    {
        "id": "blurt-s3-livestream-mesh",
        "title": "Blurt S3 Livestream & Chain Mesh Technical Note",
        "category": "white-paper",
        "description": "How Blurt S3/VOD and live ingest differ from Chain Mesh file storage; migration phases.",
        "runtime": "node",
        "script": f"{DOCS_ROOT}/generate-blurt-s3-livestream-mesh-storage-doc.js",
        "cwd": DOCS_ROOT,
        "output_path": f"{DOCS_ROOT}/Bloodstone-Blurt-S3-Livestream-And-Mesh-Storage.docx",
        "downloads_name": "Bloodstone-Blurt-S3-Livestream-And-Mesh-Storage.docx",
        "mesh_key": "downloads/Bloodstone-Blurt-S3-Livestream-And-Mesh-Storage.docx",
        "mesh_display_name": "Blurt S3 Livestream & Chain Mesh Technical Note",
        "version": "1.0",
    },
    {
        "id": "blurt-mesh-storage-partnership",
        "title": "Blurt Mesh Storage Partnership White Paper",
        "category": "white-paper",
        "description": "Blurt.blog integration proposal — limits, tenancy, streaming, STONE economics.",
        "runtime": "node",
        "script": f"{DOCS_ROOT}/generate-blurt-mesh-storage-partnership-whitepaper.js",
        "cwd": DOCS_ROOT,
        "output_path": f"{DOCS_ROOT}/Bloodstone-Blurt-Mesh-Storage-Partnership-White-Paper.docx",
        "downloads_name": "Bloodstone-Blurt-Mesh-Storage-Partnership-White-Paper.docx",
        "mesh_key": "downloads/Bloodstone-Blurt-Mesh-Storage-Partnership-White-Paper.docx",
        "mesh_display_name": "Bloodstone Blurt Mesh Storage Partnership White Paper",
        "version": "1.0",
    },
    {
        "id": "infrastructure-audit-rebuttal",
        "title": "Infrastructure Audit Point-by-Point Rebuttal",
        "category": "white-paper",
        "description": "Technical response to external infrastructure review (Blurt follow-up).",
        "runtime": "node",
        "script": f"{DOCS_ROOT}/generate-infrastructure-audit-rebuttal.js",
        "cwd": DOCS_ROOT,
        "output_path": f"{DOCS_ROOT}/Bloodstone-Infrastructure-Audit-Point-by-Point-Rebuttal.docx",
        "downloads_name": "Bloodstone-Infrastructure-Audit-Point-by-Point-Rebuttal.docx",
        "mesh_key": "downloads/Bloodstone-Infrastructure-Audit-Point-by-Point-Rebuttal.docx",
        "mesh_display_name": "Bloodstone Infrastructure Audit Point-by-Point Rebuttal",
        "version": "1.0",
    },
    {
        "id": "infrastructure-independence",
        "title": "Infrastructure Independence White Paper",
        "category": "white-paper",
        "description": "Audit response: VPS control plane vs node-independent consensus and LAN paths.",
        "runtime": "node",
        "script": f"{DOCS_ROOT}/generate-infrastructure-independence-whitepaper.js",
        "cwd": DOCS_ROOT,
        "output_path": f"{DOCS_ROOT}/Bloodstone-Infrastructure-Independence-White-Paper.docx",
        "downloads_name": "Bloodstone-Infrastructure-Independence-White-Paper.docx",
        "mesh_key": "downloads/Bloodstone-Infrastructure-Independence-White-Paper.docx",
        "mesh_display_name": "Bloodstone Infrastructure Independence White Paper",
        "version": "1.0",
    },
    {
        "id": "decentralized-network",
        "title": "Decentralized Network White Paper",
        "category": "white-paper",
        "description": "Node types, Android evolution, decentralization architecture.",
        "runtime": "node",
        "script": f"{DOCS_ROOT}/generate-whitepaper.js",
        "cwd": DOCS_ROOT,
        "output_path": f"{DOCS_ROOT}/Bloodstone-Decentralized-Network-White-Paper.docx",
        "downloads_name": "Bloodstone-Decentralized-Network-White-Paper.docx",
        "mesh_key": "downloads/Bloodstone-Decentralized-Network-White-Paper.docx",
        "mesh_display_name": "Bloodstone Decentralized Network White Paper",
        "version": "1.0",
    },
    {
        "id": "chain-mesh-storage",
        "title": "Chain Mesh Storage White Paper",
        "category": "white-paper",
        "description": "Chunking, asset library, BSM1 anchors, mesh APK fallback.",
        "runtime": "node",
        "script": f"{DOCS_ROOT}/generate-chain-mesh-storage-whitepaper.js",
        "cwd": DOCS_ROOT,
        "output_path": f"{DOCS_ROOT}/Bloodstone-Chain-Mesh-Storage-White-Paper.docx",
        "downloads_name": "Bloodstone-Chain-Mesh-Storage-White-Paper.docx",
        "mesh_key": "downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx",
        "mesh_display_name": "Bloodstone Chain Mesh Storage White Paper",
        "version": "1.1",
    },
    {
        "id": "economic-model",
        "title": "Economic Model White Paper",
        "category": "white-paper",
        "description": "Halving schedule, subsidies, staking, pool reward waterfall.",
        "runtime": "node",
        "script": f"{DOCS_ROOT}/generate-economic-whitepaper.js",
        "cwd": DOCS_ROOT,
        "output_path": f"{DOCS_ROOT}/Bloodstone-Economic-Model-White-Paper.docx",
        "downloads_name": "Bloodstone-Economic-Model-White-Paper.docx",
        "mesh_key": "downloads/Bloodstone-Economic-Model-White-Paper.docx",
        "mesh_display_name": "Bloodstone Economic Model White Paper",
        "version": "1.1",
    },
    {
        "id": "mesh-virtual-lan",
        "title": "Mesh Virtual LAN & Internet Tunnel White Paper",
        "category": "white-paper",
        "description": "BSM3 virtual LAN packets, BSM4 IPv4 tunnel, mesh-gateway egress.",
        "runtime": "node",
        "script": f"{DOCS_ROOT}/generate-mesh-virtual-lan-whitepaper.js",
        "cwd": DOCS_ROOT,
        "output_path": f"{DOCS_ROOT}/Bloodstone-Mesh-Virtual-LAN-White-Paper.docx",
        "downloads_name": "Bloodstone-Mesh-Virtual-LAN-White-Paper.docx",
        "mesh_key": "downloads/Bloodstone-Mesh-Virtual-LAN-White-Paper.docx",
        "mesh_display_name": "Bloodstone Mesh Virtual LAN White Paper",
        "version": "1.2",
    },
    {
        "id": "mesh-file-upload",
        "title": "Mesh File Upload White Paper",
        "category": "white-paper",
        "description": "Posting files, writable keys, overwrite-by-key, HTTP API guide.",
        "runtime": "node",
        "script": f"{DOCS_ROOT}/generate-mesh-file-upload-whitepaper.js",
        "cwd": DOCS_ROOT,
        "output_path": f"{DOCS_ROOT}/Bloodstone-Mesh-File-Upload-White-Paper.docx",
        "downloads_name": "Bloodstone-Mesh-File-Upload-White-Paper.docx",
        "mesh_key": "downloads/Bloodstone-Mesh-File-Upload-White-Paper.docx",
        "mesh_display_name": "Bloodstone Mesh File Upload White Paper",
        "version": "1.0",
    },
    {
        "id": "development-journey",
        "title": "Development Journey White Paper",
        "category": "white-paper",
        "description": "ROD fork through genesis relaunch and Core 0.7.x releases.",
        "runtime": "python",
        "script": f"{DOCS_ROOT}/build-development-journey-whitepaper.py",
        "cwd": DOCS_ROOT,
        "output_path": f"{DOCS_ROOT}/Bloodstone-Development-Journey-White-Paper.docx",
        "downloads_name": "Bloodstone-Development-Journey-White-Paper.docx",
        "mesh_key": "downloads/Bloodstone-Development-Journey-White-Paper.docx",
        "mesh_display_name": "Bloodstone Development Journey White Paper",
        "version": "1.0",
    },
    {
        "id": "time-capsule",
        "title": "Time Capsule White Paper",
        "category": "white-paper",
        "description": "Archive chain history to mesh; pruned tip sync workflow.",
        "runtime": "python",
        "script": "/root/build-time-capsule-white-paper.py",
        "cwd": "/root",
        "output_path": "/root/Bloodstone-Time-Capsule-White-Paper.docx",
        "downloads_name": "Bloodstone-Time-Capsule-White-Paper.docx",
        "mesh_key": "downloads/Bloodstone-Time-Capsule-White-Paper.docx",
        "mesh_display_name": "Bloodstone Time Capsule White Paper",
        "version": "1.0",
    },
    {
        "id": "subsidy-fork-release",
        "title": "Subsidy Fork Release Notes",
        "category": "release-notes",
        "description": "Bloodstone Core 0.7.0 halving and subsidy fork draft notes.",
        "runtime": "node",
        "script": f"{DOCS_ROOT}/generate-subsidy-fork-release-notes.js",
        "cwd": DOCS_ROOT,
        "output_path": f"{DOCS_ROOT}/Bloodstone-Subsidy-Fork-Release-Notes.docx",
        "downloads_name": "Bloodstone-Subsidy-Fork-Release-Notes.docx",
        "mesh_key": "downloads/Bloodstone-Subsidy-Fork-Release-Notes.docx",
        "mesh_display_name": "Bloodstone Subsidy Fork Release Notes",
        "version": "draft",
    },
    {
        "id": "subsidy-fork-1000",
        "title": "Subsidy Fork 1000 White Paper",
        "category": "white-paper",
        "description": "1000 STONE initial subsidy era technical white paper.",
        "runtime": "python",
        "script": f"{DOCS_ROOT}/build-subsidy-fork-whitepaper.py",
        "cwd": DOCS_ROOT,
        "output_path": f"{DOCS_ROOT}/Bloodstone-Subsidy-Fork-1000-White-Paper.docx",
        "downloads_name": "Bloodstone-Subsidy-Fork-1000-White-Paper.docx",
        "mesh_key": "downloads/Bloodstone-Subsidy-Fork-1000-White-Paper.docx",
        "mesh_display_name": "Bloodstone Subsidy Fork 1000 White Paper",
        "version": "1.0",
    },
]

UTILITIES: List[Dict[str, Any]] = [
    {
        "id": "mesh-always-publish",
        "title": "Republish canonical mesh docs",
        "category": "utility",
        "description": "Hash-gated republish of Live-Patchable Node and Time Capsule white papers to chain mesh.",
        "runtime": "python",
        "script": "/root/publish-bloodstone-mesh-always.py",
        "cwd": "/root",
        "output_path": "",
        "no_output": True,
    },
]


def _by_id(gen_id: str) -> Optional[Dict[str, Any]]:
    for row in GENERATORS + UTILITIES:
        if row["id"] == gen_id:
            return row
    return None


def _load_state() -> Dict[str, Any]:
    if not os.path.isfile(STATE_PATH):
        return {"runs": {}}
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            data.setdefault("runs", {})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"runs": {}}


def _save_state(state: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, STATE_PATH)


def _file_info(path: str) -> Dict[str, Any]:
    if not path or not os.path.isfile(path):
        return {"exists": False, "path": path}
    st = os.stat(path)
    return {
        "exists": True,
        "path": path,
        "size": st.st_size,
        "mtime": int(st.st_mtime),
        "sha256": _sha256_file(path),
    }


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tail_log(path: str, *, max_lines: int = 40) -> str:
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        return "".join(lines[-max_lines:]).strip()
    except OSError:
        return ""


def catalog_payload() -> Dict[str, Any]:
    state = _load_state()
    items = []
    for row in GENERATORS:
        out = row.get("output_path") or ""
        dl_name = row.get("downloads_name") or ""
        dl_path = os.path.join(DOWNLOADS_DIR, dl_name) if dl_name else ""
        last = state.get("runs", {}).get(row["id"], {})
        items.append(
            {
                "id": row["id"],
                "title": row["title"],
                "category": row["category"],
                "description": row["description"],
                "runtime": row["runtime"],
                "script": row["script"],
                "script_exists": os.path.isfile(row["script"]),
                "output": _file_info(out),
                "downloads": _file_info(dl_path),
                "downloads_url": f"{PUBLIC_ROOT}/downloads/{dl_name}" if dl_name else "",
                "mesh_key": row.get("mesh_key", ""),
                "version": row.get("version", ""),
                "last_run": last,
            }
        )
    utils = []
    for row in UTILITIES:
        last = state.get("runs", {}).get(row["id"], {})
        utils.append(
            {
                "id": row["id"],
                "title": row["title"],
                "category": row["category"],
                "description": row["description"],
                "runtime": row["runtime"],
                "script": row["script"],
                "script_exists": os.path.isfile(row["script"]),
                "last_run": last,
            }
        )
    return {"ok": True, "generators": items, "utilities": utils}


def _run_command(row: Dict[str, Any], log_path: str) -> Dict[str, Any]:
    runtime = row["runtime"]
    script = row["script"]
    cwd = row.get("cwd") or os.path.dirname(script)
    if not os.path.isfile(script):
        raise FileNotFoundError(f"generator script not found: {script}")

    if runtime == "node":
        cmd = ["/usr/bin/node", script]
    elif runtime == "python":
        cmd = ["/usr/bin/python3", script]
    else:
        raise ValueError(f"unsupported runtime: {runtime}")

    os.makedirs(LOG_DIR, exist_ok=True)
    started = int(time.time())
    with open(log_path, "a", encoding="utf-8") as logfh:
        logfh.write(f"\n--- run {row['id']} started {started} ---\n")
        logfh.flush()
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=logfh,
            stderr=subprocess.STDOUT,
            timeout=RUN_TIMEOUT_SEC,
            check=False,
        )
    finished = int(time.time())
    return {
        "exit_code": proc.returncode,
        "duration_sec": finished - started,
        "log_path": log_path,
        "log_tail": _tail_log(log_path),
    }


def _copy_to_downloads(src: str, downloads_name: str) -> Dict[str, Any]:
    if not downloads_name:
        return {"ok": False, "error": "no downloads_name"}
    if not os.path.isfile(src):
        return {"ok": False, "error": "output file missing"}
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    dest = os.path.join(DOWNLOADS_DIR, downloads_name)
    shutil.copy2(src, dest)
    return {"ok": True, "path": dest, "size": os.path.getsize(dest)}


def _sync_downloads_worker(paths: List[str]) -> Dict[str, Any]:
    script = "/root/sync-bloodstone-downloads-to-worker.sh"
    if not os.path.isfile(script) or not os.access(script, os.X_OK):
        return {"ok": False, "skipped": True, "reason": "sync script unavailable"}
    existing = [p for p in paths if p and os.path.isfile(p)]
    if not existing:
        return {"ok": False, "skipped": True, "reason": "no files to sync"}
    proc = subprocess.run(
        ["/bin/bash", script, *existing],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-1000:],
    }


def _publish_mesh(row: Dict[str, Any], src: str) -> Dict[str, Any]:
    mesh_key = row.get("mesh_key") or ""
    if not mesh_key:
        return {"ok": False, "skipped": True, "reason": "no mesh_key"}
    if not os.path.isfile(src):
        return {"ok": False, "error": "output file missing"}

    import sys

    sys.path.insert(0, "/root")
    from chain_mesh.assets import publish_asset  # noqa: E402

    result = publish_asset(
        src,
        asset_key=mesh_key,
        display_name=row.get("mesh_display_name") or row.get("title") or mesh_key,
        version=str(row.get("version") or ""),
        mime_type=MIME_DOCX,
        anchor=True,
    )
    return {
        "ok": True,
        "asset_key": result.get("asset_key"),
        "chunk_count": result.get("chunk_count"),
        "anchor_txid": (result.get("anchor") or {}).get("txid"),
    }


def run_generator(
    gen_id: str,
    *,
    copy_downloads: bool = True,
    publish_mesh: bool = False,
    sync_worker: bool = False,
    triggered_by: str = "admin",
) -> Dict[str, Any]:
    row = _by_id(gen_id)
    if not row:
        return {"ok": False, "error": "unknown generator"}

    log_path = os.path.join(LOG_DIR, f"{gen_id}.log")
    run_meta: Dict[str, Any] = {
        "id": gen_id,
        "started_at": int(time.time()),
        "triggered_by": triggered_by,
        "options": {
            "copy_downloads": copy_downloads,
            "publish_mesh": publish_mesh,
            "sync_worker": sync_worker,
        },
    }

    try:
        cmd_result = _run_command(row, log_path)
        run_meta.update(cmd_result)
        if cmd_result["exit_code"] != 0:
            run_meta["ok"] = False
            run_meta["error"] = f"generator exited {cmd_result['exit_code']}"
            _record_run(gen_id, run_meta)
            return run_meta

        output_path = row.get("output_path") or ""
        if not row.get("no_output"):
            info = _file_info(output_path)
            run_meta["output"] = info
            if not info.get("exists"):
                run_meta["ok"] = False
                run_meta["error"] = "generator finished but output file missing"
                _record_run(gen_id, run_meta)
                return run_meta

        post: Dict[str, Any] = {}
        sync_paths: List[str] = []

        if copy_downloads and output_path and row.get("downloads_name"):
            post["downloads"] = _copy_to_downloads(output_path, row["downloads_name"])
            if post["downloads"].get("ok"):
                sync_paths.append(post["downloads"]["path"])

        if publish_mesh and output_path:
            try:
                post["mesh"] = _publish_mesh(row, output_path)
            except Exception as exc:
                post["mesh"] = {"ok": False, "error": str(exc)}

        if sync_worker and sync_paths:
            post["sync"] = _sync_downloads_worker(sync_paths)

        run_meta["post"] = post
        run_meta["ok"] = True
        run_meta["finished_at"] = int(time.time())
        _record_run(gen_id, run_meta)
        return run_meta
    except subprocess.TimeoutExpired:
        run_meta["ok"] = False
        run_meta["error"] = f"timed out after {RUN_TIMEOUT_SEC}s"
        run_meta["log_tail"] = _tail_log(log_path)
        _record_run(gen_id, run_meta)
        return run_meta
    except Exception as exc:
        run_meta["ok"] = False
        run_meta["error"] = str(exc)
        run_meta["log_tail"] = _tail_log(log_path)
        _record_run(gen_id, run_meta)
        return run_meta


def _record_run(gen_id: str, meta: Dict[str, Any]) -> None:
    state = _load_state()
    state.setdefault("runs", {})[gen_id] = {
        "ok": meta.get("ok"),
        "error": meta.get("error", ""),
        "started_at": meta.get("started_at"),
        "finished_at": meta.get("finished_at"),
        "duration_sec": meta.get("duration_sec"),
        "exit_code": meta.get("exit_code"),
        "triggered_by": meta.get("triggered_by"),
        "options": meta.get("options"),
        "output_size": (meta.get("output") or {}).get("size"),
        "post": meta.get("post"),
        "log_tail": meta.get("log_tail", "")[-4000:],
    }
    _save_state(state)
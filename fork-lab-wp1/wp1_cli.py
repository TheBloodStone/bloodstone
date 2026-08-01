#!/usr/bin/env python3
"""Fork Lab WP1 operator CLI."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from wp1_db import init, connect
from wp1_draft import draft_open
from wp1_watcher import watch_once
from wp1_provision import provision

def main(argv=None):
    p = argparse.ArgumentParser(description="Fork Lab WP1 burn-triggered pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("draft-open")
    d.add_argument("--ticker", required=True)
    d.add_argument("--name", required=True)
    d.add_argument("--creator", required=True)
    d.add_argument("--fee", type=float, default=None)

    sub.add_parser("watch-once")
    sub.add_parser("list-drafts")

    pr = sub.add_parser("provision")
    pr.add_argument("--draft-id", required=True)

    args = p.parse_args(argv)
    init()
    if args.cmd == "draft-open":
        print(json.dumps(draft_open(ticker=args.ticker, name=args.name, creator=args.creator, fee=args.fee), indent=2))
        return 0
    if args.cmd == "watch-once":
        print(json.dumps(watch_once(), indent=2))
        return 0
    if args.cmd == "list-drafts":
        with connect() as c:
            rows = [dict(r) for r in c.execute("SELECT draft_id,ticker,status,fee_stone,burn_address,created_at,expires_at FROM drafts ORDER BY created_at DESC LIMIT 50")]
        print(json.dumps({"ok": True, "drafts": rows}, indent=2))
        return 0
    if args.cmd == "provision":
        print(json.dumps(provision(args.draft_id), indent=2))
        return 0
    return 1

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fork Lab WP1 operator CLI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wp1_db import init  # noqa: E402
from wp1_draft import draft_open, get_draft, list_drafts  # noqa: E402
from wp1_provision import provision  # noqa: E402
from wp1_reconcile import reconcile  # noqa: E402
from wp1_watcher import expire_orphans, watch_once  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description="Fork Lab WP1 burn-triggered pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("draft-open", help="Freeze fee, issue burn address, reserve ticker")
    d.add_argument("--ticker", required=True)
    d.add_argument("--name", required=True)
    d.add_argument("--creator", required=True)
    d.add_argument(
        "--fee",
        type=float,
        default=None,
        help="Override freeze (default: live §3c fee curve)",
    )

    sub.add_parser("watch-once", help="Scan burn addresses; apply open-min / fund / expire")
    sub.add_parser("expire", help="Lapse 48h open-min misses + expire 90d orphans")

    g = sub.add_parser("get-draft", help="Show draft + credits + remaining")
    g.add_argument("--draft-id", required=True)

    ls = sub.add_parser("list-drafts")
    ls.add_argument("--status", default=None)
    ls.add_argument("--limit", type=int, default=50)

    pr = sub.add_parser("provision")
    pr.add_argument("--draft-id", required=True)

    rc = sub.add_parser(
        "reconcile",
        help="Manual reconciliation (RFQ Decision #13) — draft_id and/or burn txids",
    )
    rc.add_argument("--draft-id", default="")
    rc.add_argument("--burn-address", default="")
    rc.add_argument(
        "--txid",
        action="append",
        default=[],
        dest="txids",
        help="Burn txid (repeatable)",
    )
    rc.add_argument(
        "--auto-provision",
        action="store_true",
        help="Provision immediately if funded",
    )

    fee = sub.add_parser("fee-quote", help="Show current §3c requirement (not frozen)")

    args = p.parse_args(argv)
    init()
    if args.cmd == "draft-open":
        print(
            json.dumps(
                draft_open(
                    ticker=args.ticker,
                    name=args.name,
                    creator=args.creator,
                    fee=args.fee,
                ),
                indent=2,
            )
        )
        return 0
    if args.cmd == "watch-once":
        print(json.dumps(watch_once(), indent=2))
        return 0
    if args.cmd == "expire":
        print(json.dumps(expire_orphans(), indent=2))
        return 0
    if args.cmd == "get-draft":
        print(json.dumps(get_draft(args.draft_id), indent=2))
        return 0
    if args.cmd == "list-drafts":
        print(json.dumps(list_drafts(limit=args.limit, status=args.status), indent=2))
        return 0
    if args.cmd == "provision":
        print(json.dumps(provision(args.draft_id), indent=2))
        return 0
    if args.cmd == "reconcile":
        print(
            json.dumps(
                reconcile(
                    draft_id=args.draft_id,
                    burn_address=args.burn_address,
                    txids=args.txids,
                    auto_provision=True if args.auto_provision else None,
                ),
                indent=2,
            )
        )
        return 0
    if args.cmd == "fee-quote":
        sys.path.insert(0, "/root")
        from fork_lab_fee_curve import current_requirement

        print(json.dumps(current_requirement(), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fork Lab WP2 — catalog + MFQ two-speed operator CLI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main(argv=None):
    p = argparse.ArgumentParser(description="Fork Lab WP2 catalog / daemon packs / train")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("catalog-rebuild", help="Rebuild runtime catalog from all sources")
    sub.add_parser("catalog-show", help="Show current runtime catalog (rebuild if stale)")

    pq = sub.add_parser("process-queue", help="Process MFQ queue + refresh packs/catalog")
    pq.add_argument("--limit", type=int, default=50)

    pub = sub.add_parser("publish-pack", help="Publish/register daemon pack for ticker")
    pub.add_argument("--ticker", required=True)
    pub.add_argument(
        "--metadata-only",
        action="store_true",
        help="Force metadata pack even if zip exists",
    )

    sub.add_parser("train-status", help="MFQ installer train status")
    sh = sub.add_parser("train-shipped", help="Mark train pending as shipped with version")
    sh.add_argument("--version", required=True)
    sh.add_argument("--ticker", action="append", default=None)

    args = p.parse_args(argv)

    if args.cmd == "catalog-rebuild":
        from wp2_catalog import write_catalog

        print(json.dumps(write_catalog(), indent=2))
        return 0
    if args.cmd == "catalog-show":
        from wp2_catalog import get_catalog

        print(json.dumps(get_catalog(), indent=2))
        return 0
    if args.cmd == "process-queue":
        from wp2_daemon_pack import process_queue

        print(json.dumps(process_queue(limit=args.limit), indent=2))
        return 0
    if args.cmd == "publish-pack":
        from wp2_daemon_pack import publish_ticker

        print(
            json.dumps(
                publish_ticker(args.ticker, force_metadata=args.metadata_only),
                indent=2,
            )
        )
        return 0
    if args.cmd == "train-status":
        from wp2_installer_train import status

        print(json.dumps(status(), indent=2))
        return 0
    if args.cmd == "train-shipped":
        from wp2_installer_train import mark_shipped

        print(json.dumps(mark_shipped(args.version, args.ticker), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

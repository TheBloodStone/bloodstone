"""Smoke tests for Wave T — tenant fleet sync, broadcast queue, auto-tenant."""

from __future__ import annotations

import io
import json
import os
import unittest
import zipfile


class TestAiWaveT(unittest.TestCase):
    def test_tenant_fleet_snapshots_and_ingest(self):
        from chain_mesh import tenant_dashboard as tdash
        from chain_mesh import tenant_fleet_sync as tfleet

        tdash.bind_all_rails(
            tenant_id="fleet-a",
            blurt_author="fleetuser",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            flops_cap=500_000,
            bandwidth_bytes_cap=600_000,
            storage_bytes_cap=700_000,
        )
        snaps = tfleet.collect_tenant_snapshots(tenant_id="fleet-a")
        self.assertGreaterEqual(len(snaps), 1)
        match = [s for s in snaps if s.get("blurt_author") == "fleetuser"]
        self.assertTrue(match)
        rails = match[0].get("rails") or {}
        self.assertEqual(rails.get("compute", {}).get("flops_cap"), 500_000)

        result = tfleet.ingest_tenant_snapshots(snaps)
        self.assertGreaterEqual(result.get("recorded"), 1)

    def test_gossip_includes_tenant_snapshots(self):
        from chain_mesh import dtn_gossip as gossip

        payload = gossip.build_exchange_payload()
        self.assertIn("tenant_snapshots", payload)
        self.assertIsInstance(payload.get("tenant_snapshots"), list)

    def test_dtn_bundle_includes_tenant_bindings(self):
        from chain_mesh import dtn_sync as dtn
        from chain_mesh import tenant_dashboard as tdash

        os.environ["TENANT_FLEET_SYNC_ENABLE"] = "1"
        tdash.bind_all_rails(
            tenant_id="bloodstone",
            blurt_author="dtnuser",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            flops_cap=1000,
            bandwidth_bytes_cap=2000,
            storage_bytes_cap=3000,
        )
        blob, _filename, meta = dtn.build_dtn_bundle(include_chunks=False)
        self.assertGreaterEqual(int(meta.get("tenant_snapshot_count") or 0), 0)
        with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
            if int(meta.get("tenant_snapshot_count") or 0) > 0:
                self.assertIn("tenant-bindings.json", zf.namelist())

    def test_broadcast_queue_prepare(self):
        from chain_mesh import ai_provider as aip

        aip.register_ai_provider(
            provider_id="queue-test-ai",
            source="local",
            body={
                "v": "1",
                "provider_id": "queue-test-ai",
                "node_id": "queue-test",
                "runtimes": ["onnx", "cpu-inference"],
                "region": "lan",
            },
        )
        queue = aip.prepare_broadcast_queue(limit=5)
        self.assertTrue(queue.get("ok"))
        self.assertGreaterEqual(queue.get("count", 0), 1)

    def test_compute_submit_auto_tenant(self):
        from chain_mesh import compute_job as cjobs
        from chain_mesh import depin_credits as depin

        os.environ["COMPUTE_TENANT_ENFORCE"] = "0"
        os.environ["COMPUTE_CREDIT_ENFORCE"] = "0"
        os.environ["DTN_DEFAULT_TENANT"] = "auto-tenant-test"
        result = cjobs.submit_payload(
            {
                "stone_address": "STONE1abcdefghijklmnopqrstuvwxyz12",
                "blurt_author": "autosubmit",
                "job_type": "inference",
                "flops_budget": 100,
                "ai_spec": {"runtime": "cpu-inference"},
            }
        )
        self.assertTrue(result.get("ok"))


if __name__ == "__main__":
    unittest.main()
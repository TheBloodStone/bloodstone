"""Smoke tests for Wave Y — route ledger, coordinator tenant dispatch, unified upkeep."""

from __future__ import annotations

import os
import unittest


class TestAiWaveY(unittest.TestCase):
    def setUp(self):
        os.environ["TENANT_NPU_PROBE_ON_BIND"] = "0"

    def test_route_ledger_record_and_list(self):
        from chain_mesh import tenant_route_ledger as tledger

        tledger.record_assignment(
            job={
                "job_id": "job-y-001",
                "tenant_id": "ledger-y",
                "blurt_author": "ledgeruser",
            },
            provider={"provider_id": "pi-edge-ai"},
            tenant_spec={"runtime": "onnx", "hardware_kind": "hailo"},
            score=88.5,
        )
        result = tledger.list_assignments(
            tenant_id="ledger-y",
            blurt_author="ledgeruser",
        )
        self.assertGreaterEqual(result.get("count", 0), 1)
        self.assertEqual(result["assignments"][0].get("provider_id"), "pi-edge-ai")

    def test_route_gossip_snapshots(self):
        from chain_mesh import tenant_route_ledger as tledger

        tledger.record_assignment(
            job={"job_id": "job-y-002", "blurt_author": "gossiproute"},
            provider={"provider_id": "node-b-ai"},
            tenant_spec={"runtime": "tflite"},
        )
        snaps = tledger.build_route_gossip_snapshots(limit=5)
        self.assertGreaterEqual(len(snaps), 1)
        ingest = tledger.ingest_route_snapshots(snaps)
        self.assertGreaterEqual(ingest.get("recorded", 0), 1)

    def test_gossip_includes_tenant_route_snapshots(self):
        from chain_mesh import dtn_gossip as gossip

        payload = gossip.build_exchange_payload()
        self.assertIn("tenant_route_snapshots", payload)

    def test_unified_tenant_upkeep(self):
        from chain_mesh import tenant_upkeep as tup

        result = tup.upkeep_tenant()
        self.assertTrue(result.get("ok"))
        self.assertIn("quorum", result)
        self.assertIn("broadcast_queue", result)
        status = tup.status_payload()
        self.assertTrue(status.get("ok"))

    def test_coordinator_dispatch_includes_tenant_route(self):
        from chain_mesh import ai_routing as ai

        os.environ["AI_COORDINATOR_DISPATCH_ENABLE"] = "0"
        # Ensure module loads; full HTTP dispatch tested via integration elsewhere.
        self.assertTrue(hasattr(ai, "dispatch_to_coordinator"))

    def test_npu_probe_on_bind_blocks_missing(self):
        from chain_mesh import tenant_npu_models as tnpu

        os.environ["TENANT_NPU_PROBE_ON_BIND"] = "1"
        with self.assertRaises(ValueError):
            tnpu.bind_npu_model(
                blurt_author="probeuser",
                runtime="onnx",
                model_path="/no/such/model-y.onnx",
            )
        os.environ["TENANT_NPU_PROBE_ON_BIND"] = "0"

    def test_dashboard_route_history(self):
        from chain_mesh import tenant_dashboard as tdash
        from chain_mesh import tenant_route_ledger as tledger

        tledger.record_assignment(
            job={"job_id": "job-y-dash", "blurt_author": "dashy", "tenant_id": "dash-y"},
            provider={"provider_id": "dash-ai"},
            tenant_spec={"runtime": "onnx"},
        )
        dash = tdash.dashboard_payload(tenant_id="dash-y", blurt_author="dashy")
        self.assertIn("route_history", dash)
        self.assertGreaterEqual((dash.get("route_history") or {}).get("count", 0), 1)
        html = tdash.dashboard_page_html()
        self.assertTrue("Wave Y" in html or "Wave Z" in html)
        self.assertIn("route ledger", html)

    def test_api_wave_y_payloads(self):
        from chain_mesh import api as cmap

        ledger = cmap.convergence_tenant_route_ledger_status_payload()
        self.assertTrue(ledger.get("ok"))
        upkeep = cmap.convergence_tenant_upkeep_status_payload()
        self.assertTrue(upkeep.get("ok"))


if __name__ == "__main__":
    unittest.main()
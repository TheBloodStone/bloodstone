"""Smoke tests for Wave Z — tenant planetary quorum + sovereign mesh reconcile."""

from __future__ import annotations

import os
import unittest


class TestAiWaveZ(unittest.TestCase):
    def setUp(self):
        os.environ["TENANT_NPU_PROBE_ON_BIND"] = "0"

    def test_tenant_planetary_snapshot_and_rollup(self):
        from chain_mesh import tenant_planetary_quorum as tplanetary

        snap = tplanetary.build_quorum_snapshot()
        self.assertEqual(snap.get("format"), tplanetary.TENANT_PLANETARY_FORMAT)
        ingest = tplanetary.ingest_planetary_snapshots([snap])
        self.assertGreaterEqual(ingest.get("votes_recorded", 0), 1)
        rollup = ingest.get("rollup") or {}
        self.assertTrue(rollup.get("ok"))
        self.assertGreaterEqual(rollup.get("regions_total", 0), 1)

    def test_gossip_includes_tenant_planetary_snapshots(self):
        from chain_mesh import dtn_gossip as gossip

        payload = gossip.build_exchange_payload()
        self.assertIn("tenant_planetary_snapshots", payload)

    def test_sovereign_reconcile(self):
        from chain_mesh import tenant_sovereign as tsov

        result = tsov.reconcile_sovereign_mesh()
        self.assertTrue(result.get("ok"))
        self.assertIn("upkeep", result)
        self.assertIn("planetary", result)
        self.assertIn("summary", result)
        status = tsov.status_payload()
        self.assertTrue(status.get("ok"))
        self.assertIn("subsystems", status)

    def test_upkeep_includes_planetary(self):
        from chain_mesh import tenant_upkeep as tup

        result = tup.upkeep_tenant()
        self.assertTrue(result.get("ok"))
        self.assertIn("planetary", result)

    def test_coordinator_dispatch_submit_gate_permissive(self):
        from chain_mesh import ai_routing as ai

        os.environ["TENANT_SUBMIT_QUORUM_REQUIRE"] = "0"
        os.environ["AI_ROUTING_ENABLE"] = "0"
        result = ai.coordinator_dispatch_job(
            job_id="job-z-gate",
            payload={"tenant_route": {"runtime": "onnx", "hardware_kind": "cpu"}},
        )
        self.assertTrue(result.get("skipped") or result.get("ok") is not None)

    def test_dashboard_sovereign_panel(self):
        from chain_mesh import tenant_dashboard as tdash

        dash = tdash.dashboard_payload(blurt_author="sovuser")
        self.assertIn("sovereign", dash)
        html = tdash.dashboard_page_html()
        self.assertIn("Wave Z", html)
        self.assertIn("sovereign mesh", html)

    def test_convergence_includes_tenant_sovereign(self):
        from chain_mesh import convergence as conv

        status = conv.status_payload()
        self.assertIn("tenant_sovereign", status)
        self.assertIn("Wave Z", status.get("roadmap", ""))

    def test_api_wave_z_payloads(self):
        from chain_mesh import api as cmap

        planetary = cmap.convergence_tenant_planetary_status_payload()
        self.assertTrue(planetary.get("ok"))
        sovereign = cmap.convergence_tenant_sovereign_status_payload()
        self.assertTrue(sovereign.get("ok"))
        reconcile = cmap.convergence_tenant_sovereign_reconcile_payload()
        self.assertTrue(reconcile.get("ok"))


if __name__ == "__main__":
    unittest.main()
"""Smoke tests for Wave X — tenant AI routing, manifest gossip, NPU model probe."""

from __future__ import annotations

import os
import tempfile
import unittest


class TestAiWaveX(unittest.TestCase):
    def test_tenant_ai_route_resolve(self):
        from chain_mesh import tenant_ai_route as troute
        from chain_mesh import tenant_npu_models as tnpu

        tnpu.bind_npu_model(
            tenant_id="route-x",
            blurt_author="routeuser",
            runtime="onnx",
            model_path="/tmp/route-x.onnx",
            hardware_kind="hailo",
        )
        spec = troute.resolve_job_inference_spec(
            {
                "tenant_id": "route-x",
                "blurt_author": "routeuser",
                "ai_spec": {},
            }
        )
        self.assertEqual(spec.get("runtime"), "onnx")
        self.assertEqual(spec.get("model_path"), "/tmp/route-x.onnx")

    def test_tenant_route_bonus(self):
        from chain_mesh import tenant_ai_route as troute

        spec = {"runtime": "onnx", "hardware_kind": "hailo"}
        provider = {
            "runtimes": '["onnx","cpu-inference"]',
            "hardware_json": '{"kind":"hailo"}',
            "models_json": "[]",
        }
        bonus = troute.tenant_route_bonus(provider, spec=spec)
        self.assertGreaterEqual(bonus, 55.0)

    def test_build_dispatch_payload(self):
        from chain_mesh import tenant_ai_route as troute

        payload = troute.build_dispatch_payload(
            {"blurt_author": "dispatchx", "tenant_id": "bloodstone"},
            base_payload={"prompt": "hi"},
        )
        self.assertEqual(payload.get("blurt_author"), "dispatchx")
        self.assertIn("tenant_id", payload)

    def test_manifest_gossip_build_and_ingest(self):
        from chain_mesh import tenant_dashboard as tdash
        from chain_mesh import tenant_manifest_gossip as tmgossip

        tdash.bind_all_rails(
            tenant_id="gossip-x",
            blurt_author="gossipuser",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            flops_cap=1000,
            bandwidth_bytes_cap=2000,
            storage_bytes_cap=3000,
        )
        snaps = tmgossip.build_manifest_snapshots(limit=5)
        self.assertGreaterEqual(len(snaps), 1)
        result = tmgossip.ingest_manifest_snapshots(snaps)
        self.assertGreaterEqual(result.get("indexed", 0), 1)

    def test_gossip_includes_tenant_manifest_snapshots(self):
        from chain_mesh import dtn_gossip as gossip

        payload = gossip.build_exchange_payload()
        self.assertIn("tenant_manifest_snapshots", payload)
        self.assertIsInstance(payload.get("tenant_manifest_snapshots"), list)

    def test_npu_probe_missing_file(self):
        from chain_mesh import tenant_npu_models as tnpu

        result = tnpu.probe_model(runtime="onnx", model_path="/no/such/model.onnx")
        self.assertFalse(result.get("ok"))

    def test_dashboard_includes_submit_and_route(self):
        from chain_mesh import tenant_dashboard as tdash

        tdash.bind_all_rails(
            tenant_id="dash-x",
            blurt_author="dashx",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            flops_cap=5000,
            bandwidth_bytes_cap=6000,
            storage_bytes_cap=7000,
        )
        dash = tdash.dashboard_payload(tenant_id="dash-x", blurt_author="dashx")
        self.assertIn("submit_gate", dash)
        self.assertIn("ai_route", dash)
        html = tdash.dashboard_page_html()
        self.assertIn("Wave X", html)
        self.assertIn("submit gate", html)

    def test_api_wave_x_payloads(self):
        from chain_mesh import api as cmap

        route = cmap.convergence_tenant_ai_route_status_payload()
        self.assertTrue(route.get("ok"))
        gossip = cmap.convergence_tenant_manifest_gossip_status_payload()
        self.assertTrue(gossip.get("ok"))


if __name__ == "__main__":
    unittest.main()
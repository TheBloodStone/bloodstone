"""Smoke tests for Wave W — submit quorum gate, tenant NPU models, dashboard quorum panel."""

from __future__ import annotations

import importlib.util
import os
import unittest


class TestAiWaveW(unittest.TestCase):
    def test_submit_gate_permissive_by_default(self):
        from chain_mesh import tenant_submit_gate as tgate

        os.environ.pop("TENANT_SUBMIT_QUORUM_REQUIRE", None)
        gate = tgate.check_submit_allowed(
            tenant_id="bloodstone",
            blurt_author="gateuser",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
        )
        self.assertTrue(gate.get("allowed"))
        self.assertFalse(gate.get("require_quorum"))

    def test_submit_gate_strict_when_required(self):
        from chain_mesh import tenant_submit_gate as tgate

        os.environ["TENANT_SUBMIT_QUORUM_REQUIRE"] = "1"
        gate = tgate.check_submit_allowed(
            tenant_id="strict-test",
            blurt_author="unquorumuser",
        )
        self.assertFalse(gate.get("allowed"))
        os.environ.pop("TENANT_SUBMIT_QUORUM_REQUIRE", None)

    def test_quorum_for_author(self):
        from chain_mesh import tenant_dashboard as tdash
        from chain_mesh import tenant_fleet_quorum as tquorum
        from chain_mesh import tenant_fleet_sync as tfleet
        from chain_mesh import tenant_submit_gate as tgate

        tdash.bind_all_rails(
            tenant_id="author-q",
            blurt_author="authorq",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            flops_cap=1000,
            bandwidth_bytes_cap=2000,
            storage_bytes_cap=3000,
        )
        snaps = tfleet.collect_tenant_snapshots(tenant_id="author-q")
        tquorum.record_snapshot_votes(snaps, reporter_node_id="node-a")
        tquorum.record_snapshot_votes(snaps, reporter_node_id="node-b")
        tquorum.update_quorum_state()
        q = tgate.quorum_for_author(tenant_id="author-q", blurt_author="authorq")
        self.assertTrue(q.get("satisfied"))

    def test_tenant_npu_bind_and_resolve(self):
        from chain_mesh import tenant_npu_models as tnpu

        tnpu.bind_npu_model(
            tenant_id="npu-w",
            blurt_author="npuuser",
            runtime="onnx",
            model_path="/tmp/wave-w-model.onnx",
            hardware_kind="hailo",
        )
        spec = tnpu.resolve_inference_spec(
            tenant_id="npu-w",
            blurt_author="npuuser",
        )
        self.assertEqual(spec.get("runtime"), "onnx")
        self.assertEqual(spec.get("model_path"), "/tmp/wave-w-model.onnx")
        self.assertEqual(spec.get("source"), "tenant_binding")

    def test_dashboard_includes_quorum_and_npu(self):
        from chain_mesh import tenant_dashboard as tdash
        from chain_mesh import tenant_npu_models as tnpu

        tdash.bind_all_rails(
            tenant_id="dash-w",
            blurt_author="dashw",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            flops_cap=5000,
            bandwidth_bytes_cap=6000,
            storage_bytes_cap=7000,
        )
        tnpu.bind_npu_model(
            tenant_id="dash-w",
            blurt_author="dashw",
            runtime="tflite",
            model_path="/tmp/edge.tflite",
            hardware_kind="coral",
        )
        dash = tdash.dashboard_payload(tenant_id="dash-w", blurt_author="dashw")
        self.assertIn("quorum", dash)
        self.assertGreaterEqual(len(dash.get("npu_models") or []), 1)
        html = tdash.dashboard_page_html()
        self.assertIn("Wave W", html)
        self.assertIn("fleet quorum", html)

    def test_tenant_manifest_includes_npu_models(self):
        from chain_mesh import tenant_broadcast as tb
        from chain_mesh import tenant_npu_models as tnpu

        tnpu.bind_npu_model(
            tenant_id="manifest-w",
            blurt_author="manifestw",
            runtime="onnx",
            model_path="/tmp/manifest.onnx",
            hardware_kind="hailo",
        )
        manifest = tb.build_tenant_broadcast_manifest(
            tenant_id="manifest-w",
            blurt_author="manifestw",
        )
        body = manifest.get("body") or {}
        self.assertGreaterEqual(len(body.get("npu_models") or []), 1)

    def test_compute_submit_includes_gate(self):
        from chain_mesh import compute_job as cjobs

        os.environ["COMPUTE_TENANT_ENFORCE"] = "0"
        os.environ["COMPUTE_CREDIT_ENFORCE"] = "0"
        result = cjobs.submit_payload(
            {
                "stone_address": "STONE1abcdefghijklmnopqrstuvwxyz12",
                "blurt_author": "submitw",
                "job_type": "inference",
                "flops_budget": 100,
                "ai_spec": {"runtime": "cpu-inference"},
            }
        )
        self.assertTrue(result.get("ok"))
        self.assertIn("submit_gate", result)

    def test_inference_shim_tenant_resolve(self):
        from chain_mesh import tenant_npu_models as tnpu

        shim_path = "/root/ops/bloodstone-pi-fleet/scripts/ai-inference-shim.py"
        spec = importlib.util.spec_from_file_location("ai_inference_shim_w", shim_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        tnpu.bind_npu_model(
            tenant_id="shim-w",
            blurt_author="shimuser",
            runtime="onnx",
            model_path="/tmp/shim.onnx",
            hardware_kind="hailo",
        )
        hint = mod._tenant_inference_hint({"blurt_author": "shimuser", "tenant_id": "shim-w"})
        self.assertEqual(hint.get("runtime"), "onnx")

    def test_api_submit_and_npu_payloads(self):
        from chain_mesh import api as cmap

        status = cmap.convergence_tenant_submit_status_payload()
        self.assertTrue(status.get("ok"))
        npu = cmap.convergence_tenant_npu_status_payload()
        self.assertTrue(npu.get("ok"))


if __name__ == "__main__":
    unittest.main()
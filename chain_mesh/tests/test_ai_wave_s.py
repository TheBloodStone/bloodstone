"""Smoke tests for Wave S — tenant dashboard, Blurt broadcast, runtime delegates."""

from __future__ import annotations

import importlib.util
import os
import unittest


class TestAiWaveS(unittest.TestCase):
    def test_unified_tenant_dashboard(self):
        from chain_mesh import tenant_dashboard as tdash

        tdash.bind_all_rails(
            tenant_id="dash-test",
            blurt_author="creatorx",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            flops_cap=1_000_000,
            bandwidth_bytes_cap=2_000_000,
            storage_bytes_cap=3_000_000,
        )
        dash = tdash.dashboard_payload(
            tenant_id="dash-test",
            blurt_author="creatorx",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
        )
        self.assertEqual(dash.get("format"), "bloodstone_tenant_dashboard/v1")
        rails = dash.get("rails") or {}
        self.assertEqual(rails.get("compute", {}).get("flops_cap"), 1_000_000)
        self.assertEqual(rails.get("bandwidth", {}).get("bytes_cap"), 2_000_000)
        self.assertEqual(rails.get("storage", {}).get("bytes_cap"), 3_000_000)

    def test_tenant_status_payload(self):
        from chain_mesh import tenant_dashboard as tdash

        status = tdash.status_payload()
        self.assertTrue(status.get("ok"))
        self.assertIn("compute", status.get("rails", {}))
        self.assertIn("dashboard", status.get("apis", {}).get("dashboard", ""))

    def test_ai_provider_broadcast_manifest(self):
        from chain_mesh import ai_provider as aip

        result = aip.broadcast_provider_payload(
            {
                "provider_id": "wave-s-pi-ai",
                "node_id": "wave-s-pi",
                "blurt_author": "meshops",
                "runtimes": ["onnx", "tflite", "llama.cpp"],
                "region": "lan",
            }
        )
        self.assertTrue(result.get("ok"))
        bcj = result.get("blurt_custom_json") or {}
        self.assertEqual(bcj.get("id"), aip.AI_PROVIDER_ID)
        self.assertIn("json", bcj)
        self.assertIn("Broadcast", " ".join(result.get("next_steps") or []))

    def test_inference_shim_runtime_dispatch(self):
        shim_path = "/root/ops/bloodstone-pi-fleet/scripts/ai-inference-shim.py"
        spec = importlib.util.spec_from_file_location("ai_inference_shim_s", shim_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        onnx_out = mod.dispatch_completion(
            {"runtime": "onnx", "model": "onnx:test", "prompt": "wave s", "max_tokens": 8}
        )
        self.assertEqual(onnx_out.get("runtime"), "onnx")
        self.assertTrue(onnx_out.get("choices"))
        tflite_out = mod.dispatch_completion(
            {"runtime": "tflite", "model": "tflite:edge", "prompt": "coral", "max_tokens": 8}
        )
        self.assertEqual(tflite_out.get("runtime"), "tflite")
        delegates = mod._probe_delegates()
        self.assertTrue(delegates.get("cpu-inference"))


if __name__ == "__main__":
    unittest.main()
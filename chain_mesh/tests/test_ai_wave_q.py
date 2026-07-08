"""Smoke tests for Wave Q — inference shim, bandwidth tenant, fleet gossip."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock


class TestAiWaveQ(unittest.TestCase):
    def test_bandwidth_bind_and_tenant_quota(self):
        from chain_mesh import bandwidth_tenant_quota as tenant

        tenant.bind_tenant_author(
            tenant_id="bw-test",
            blurt_author="uploader1",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            bytes_cap=1_000_000,
        )
        q = tenant.tenant_quota(
            tenant_id="bw-test",
            blurt_author="uploader1",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
        )
        self.assertEqual(q.get("bytes_cap"), 1_000_000)
        self.assertEqual(q.get("bytes_used"), 0)

    def test_bandwidth_tenant_cap_denies_over_budget(self):
        from chain_mesh import bandwidth_tenant_quota as tenant
        from chain_mesh import depin_credits as depin

        os.environ["BANDWIDTH_TENANT_ENFORCE"] = "1"
        os.environ["BANDWIDTH_CREDIT_ENFORCE"] = "0"
        tenant.bind_tenant_author(
            tenant_id="bw-cap",
            blurt_author="heavy",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            bytes_cap=1000,
        )
        tenant.record_tenant_bandwidth_usage(
            tenant_id="bw-cap",
            blurt_author="heavy",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            delta_bytes=900,
        )
        result = depin.check_bandwidth_allowed(
            "STONE1abcdefghijklmnopqrstuvwxyz12",
            200,
            blurt_author="heavy",
            tenant_id="bw-cap",
        )
        self.assertFalse(result.get("allowed"))
        self.assertIn("tenant", result.get("reason", "").lower())

    def test_fleet_gossip_accepts_signed_rejects_unsigned(self):
        from chain_mesh import ai_gossip_sign as gsign
        from chain_mesh import ai_routing as ai

        os.environ["AI_GOSSIP_SIGNING_KEY"] = "fleet-wave-q-key"
        os.environ.pop("AI_GOSSIP_ALLOW_UNSIGNED", None)
        signed = gsign.sign_snapshot(
            {
                "provider_id": "pi-fleet-ai",
                "node_id": "pi-fleet",
                "runtimes": ["llama.cpp"],
                "last_seen": gsign._now(),
            }
        )
        ok_result = ai.ingest_gossip_snapshots([signed])
        self.assertEqual(ok_result.get("recorded"), 1)

        bad_result = ai.ingest_gossip_snapshots(
            [
                {
                    "provider_id": "rogue-ai",
                    "node_id": "rogue",
                    "runtimes": ["cpu-inference"],
                    "last_seen": gsign._now(),
                }
            ]
        )
        self.assertEqual(bad_result.get("recorded"), 0)
        self.assertGreaterEqual(bad_result.get("rejected"), 1)
        os.environ["AI_GOSSIP_ALLOW_UNSIGNED"] = "1"
        os.environ.pop("AI_GOSSIP_SIGNING_KEY", None)

    def test_fleet_key_status_payload(self):
        from chain_mesh import ai_gossip_sign as gsign

        os.environ["AI_GOSSIP_SIGNING_KEY"] = "status-test-key"
        os.environ.pop("AI_GOSSIP_ALLOW_UNSIGNED", None)
        status = gsign.status_payload()
        self.assertTrue(status.get("fleet_key_configured"))
        self.assertTrue(status.get("require_fleet_key"))
        self.assertEqual(status.get("enforcement_mode"), "fleet_strict")
        os.environ.pop("AI_GOSSIP_SIGNING_KEY", None)
        os.environ["AI_GOSSIP_ALLOW_UNSIGNED"] = "1"

    def test_inference_shim_stub_completion(self):
        shim_path = "/root/ops/bloodstone-pi-fleet/scripts/ai-inference-shim.py"
        self.assertTrue(os.path.isfile(shim_path))
        with mock.patch.dict(os.environ, {"AI_FLOPS_PER_SEC": "100"}, clear=False):
            import importlib.util

            spec = importlib.util.spec_from_file_location("ai_inference_shim", shim_path)
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(mod)
            out = mod._stub_completion({"prompt": "hello mesh", "model": "test", "max_tokens": 8})
        self.assertIn("choices", out)
        self.assertTrue(out["choices"][0]["text"])


if __name__ == "__main__":
    unittest.main()
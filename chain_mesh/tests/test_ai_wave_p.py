"""Smoke tests for Wave P — multi-tenant quota + Blurt provider sync helpers."""

from __future__ import annotations

import os
import unittest


class TestWaveP(unittest.TestCase):
    def test_bind_and_tenant_quota(self):
        from chain_mesh import compute_tenant_quota as tenant

        tenant.bind_tenant_author(
            tenant_id="test-fleet",
            blurt_account="creator1",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            flops_cap=1_000_000,
        )
        q = tenant.tenant_quota(
            tenant_id="test-fleet",
            blurt_account="creator1",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
        )
        self.assertEqual(q.get("flops_cap"), 1_000_000)
        self.assertEqual(q.get("flops_used"), 0)

    def test_tenant_cap_denies_over_budget(self):
        from chain_mesh import compute_tenant_quota as tenant
        from chain_mesh import depin_credits as depin

        os.environ["COMPUTE_TENANT_ENFORCE"] = "1"
        os.environ["COMPUTE_CREDIT_ENFORCE"] = "0"
        tenant.bind_tenant_author(
            tenant_id="cap-test",
            blurt_account="limited",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            flops_cap=100,
        )
        tenant.record_tenant_compute_usage(
            tenant_id="cap-test",
            blurt_account="limited",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            delta_flops=90,
        )
        result = depin.check_compute_allowed(
            "STONE1abcdefghijklmnopqrstuvwxyz12",
            flops_budget=20,
            blurt_account="limited",
            tenant_id="cap-test",
        )
        self.assertFalse(result.get("allowed"))
        self.assertIn("tenant", result.get("reason", "").lower())

    def test_parse_provider_op(self):
        from chain_mesh import ai_provider as aip

        body = aip._parse_provider_op(
            {
                "v": "1",
                "provider_id": "registry-pi-ai",
                "node_id": "registry-pi",
                "runtimes": ["llama.cpp", "cpu-inference"],
            }
        )
        self.assertIsNotNone(body)
        self.assertIn("llama.cpp", body.get("runtimes"))


if __name__ == "__main__":
    unittest.main()
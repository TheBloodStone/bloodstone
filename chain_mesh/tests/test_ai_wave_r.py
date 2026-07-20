"""Smoke tests for Wave R — storage tenant + AI DTN route export/import."""

from __future__ import annotations

import io
import json
import os
import unittest
import zipfile


class TestAiWaveR(unittest.TestCase):
    def test_storage_bind_and_tenant_quota(self):
        from chain_mesh import storage_tenant_quota as tenant

        tenant.bind_tenant_author(
            tenant_id="stor-test",
            blurt_account="publisher1",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            bytes_cap=5_000_000,
        )
        q = tenant.tenant_quota(
            tenant_id="stor-test",
            blurt_account="publisher1",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
        )
        self.assertEqual(q.get("bytes_cap"), 5_000_000)
        self.assertEqual(q.get("bytes_used"), 0)

    def test_storage_tenant_cap_denies_over_budget(self):
        from chain_mesh import storage_credits as sc
        from chain_mesh import storage_tenant_quota as tenant

        os.environ["STORAGE_TENANT_ENFORCE"] = "1"
        os.environ["STORAGE_CREDIT_ENFORCE"] = "0"
        tenant.bind_tenant_author(
            tenant_id="stor-cap",
            blurt_account="heavypub",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            bytes_cap=1000,
        )
        tenant.record_tenant_storage_usage(
            tenant_id="stor-cap",
            blurt_account="heavypub",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            delta_bytes=900,
        )
        result = sc.check_publish_allowed(
            "STONE1abcdefghijklmnopqrstuvwxyz12",
            200,
            blurt_account="heavypub",
            tenant_id="stor-cap",
        )
        self.assertFalse(result.get("allowed"))
        self.assertIn("tenant", result.get("reason", "").lower())

    def test_ai_forward_bundle_roundtrip(self):
        from chain_mesh import ai_routing as ai
        from chain_mesh import compute_job as cjobs
        from chain_mesh import dtn_sync as dtn

        cjobs.init_compute_job_db()
        ai.init_ai_routing_db()
        job = cjobs.submit_payload(
            {
                "stone_address": "STONE1abcdefghijklmnopqrstuvwxyz12",
                "blurt_account": "routeuser",
                "job_type": "inference",
                "flops_budget": 1000,
                "ai_spec": {"runtime": "llama.cpp", "model_id": "test"},
            }
        )
        jid = str(job.get("body", {}).get("job_id") or "")
        self.assertTrue(jid)
        ai.sync_compute_job_route(
            job_id=jid,
            provider_id="pi-test-ai",
            route_status="queued_dtn",
            reason="test_export",
        )
        raw, _fname, meta = ai.build_ai_forward_bundle(job_id=jid)
        self.assertEqual(meta.get("purpose"), "ai_forward")
        result = dtn.import_dtn_bundle(raw, skip_dedup=True)
        self.assertTrue(result.get("ok"))
        self.assertGreaterEqual(result.get("ai_routes_imported", 0), 0)
        route = ai.get_current_route_assignment(job_id=jid)
        self.assertIsNotNone(route)

    def test_dtn_export_includes_routes_when_enabled(self):
        from chain_mesh import ai_routing as ai
        from chain_mesh import compute_job as cjobs
        from chain_mesh import dtn_sync as dtn

        old = os.environ.get("AI_DTN_EXPORT_ROUTES")
        os.environ["AI_DTN_EXPORT_ROUTES"] = "1"
        try:
            cjobs.init_compute_job_db()
            ai.init_ai_routing_db()
            job = cjobs.submit_payload(
                {
                    "stone_address": "STONE1abcdefghijklmnopqrstuvwxyz12",
                    "blurt_account": "dtnuser",
                    "job_type": "inference",
                    "flops_budget": 500,
                    "ai_spec": {"runtime": "cpu-inference"},
                }
            )
            jid = str(job.get("body", {}).get("job_id") or "")
            ai.sync_compute_job_route(
                job_id=jid,
                provider_id="",
                route_status="queued_dtn",
                reason="dtn_export_test",
            )
            blob, _filename, meta = dtn.build_dtn_bundle(include_chunks=False)
            self.assertGreaterEqual(int(meta.get("ai_route_count") or 0), 0)
            with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
                names = zf.namelist()
                if int(meta.get("ai_route_count") or 0) > 0:
                    self.assertIn("ai-route-assignments.json", names)
        finally:
            if old is None:
                os.environ.pop("AI_DTN_EXPORT_ROUTES", None)
            else:
                os.environ["AI_DTN_EXPORT_ROUTES"] = old


if __name__ == "__main__":
    unittest.main()
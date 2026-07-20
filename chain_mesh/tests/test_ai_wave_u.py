"""Smoke tests for Wave U — signed tenant fleet, dashboard UI, NPU inference, DTN auto-author."""

from __future__ import annotations

import io
import json
import os
import unittest
import zipfile


class TestAiWaveU(unittest.TestCase):
    def test_tenant_snapshot_sign_and_verify(self):
        from chain_mesh import tenant_dashboard as tdash
        from chain_mesh import tenant_fleet_sign as tsign
        from chain_mesh import tenant_fleet_sync as tfleet

        tdash.bind_all_rails(
            tenant_id="sign-test",
            blurt_account="signuser",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            flops_cap=400_000,
            bandwidth_bytes_cap=500_000,
            storage_bytes_cap=600_000,
        )
        snaps = tfleet.collect_tenant_snapshots(tenant_id="sign-test")
        self.assertGreaterEqual(len(snaps), 1)
        signed = snaps[0]
        self.assertTrue(signed.get("signature"))
        ok, reason = tsign.verify_snapshot(signed)
        self.assertTrue(ok, reason)

        tampered = dict(signed)
        tampered["rails"] = {"compute": {"flops_cap": 999_999_999}}
        ok2, _ = tsign.verify_snapshot(tampered)
        self.assertFalse(ok2)

    def test_ingest_rejects_bad_signature(self):
        from chain_mesh import tenant_dashboard as tdash
        from chain_mesh import tenant_fleet_sign as tsign
        from chain_mesh import tenant_fleet_sync as tfleet

        tdash.bind_all_rails(
            tenant_id="reject-test",
            blurt_account="rejectuser",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            flops_cap=1000,
            bandwidth_bytes_cap=2000,
            storage_bytes_cap=3000,
        )
        snaps = tfleet.collect_tenant_snapshots(tenant_id="reject-test")
        self.assertGreaterEqual(len(snaps), 1)
        bad = dict(snaps[0])
        bad["signature"] = "deadbeef"
        result = tfleet.ingest_tenant_snapshots([bad])
        self.assertGreaterEqual(result.get("rejected", 0), 1)

    def test_tenant_fleet_sign_status_payload(self):
        from chain_mesh import tenant_fleet_sign as tsign

        status = tsign.status_payload()
        self.assertTrue(status.get("ok"))
        self.assertEqual(status.get("format"), "bloodstone_tenant_snapshot/v1")
        self.assertIn("sign_enable", status)

    def test_dashboard_page_html(self):
        from chain_mesh import tenant_dashboard as tdash

        html = tdash.dashboard_page_html()
        self.assertTrue("Wave U" in html or "Wave V" in html)
        self.assertIn("/api/convergence/tenant/dashboard", html)

    def test_dtn_export_auto_author(self):
        from chain_mesh import api as cmap
        from chain_mesh import tenant_dashboard as tdash

        stone = "STONE1abcdefghijklmnopqrstuvwxyz12"
        tdash.bind_all_rails(
            tenant_id="auto-author",
            blurt_account="autoauthor",
            stone_address=stone,
            flops_cap=2000,
            bandwidth_bytes_cap=3000,
            storage_bytes_cap=4000,
        )
        os.environ["BANDWIDTH_TENANT_ENFORCE"] = "0"
        result = cmap.convergence_dtn_export_payload(
            stone_address=stone,
            blurt_account="",
            include_chunks=False,
        )
        self.assertTrue(result.get("ok"))

    def test_dtn_build_zip_auto_author(self):
        from chain_mesh import api as cmap
        from chain_mesh import tenant_dashboard as tdash

        stone = "STONE1abcdefghijklmnopqrstuvwxyz12"
        tdash.bind_all_rails(
            tenant_id="zip-author",
            blurt_account="zipauthor",
            stone_address=stone,
            flops_cap=2000,
            bandwidth_bytes_cap=3000,
            storage_bytes_cap=4000,
        )
        os.environ["BANDWIDTH_TENANT_ENFORCE"] = "0"
        blob, filename, meta = cmap.convergence_dtn_build_zip(
            stone_address=stone,
            blurt_account="",
            include_chunks=False,
        )
        self.assertGreater(len(blob), 0)
        self.assertTrue(filename.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
            self.assertIn("dtn-meta.json", zf.namelist())

    def test_api_fleet_sign_status(self):
        from chain_mesh import api as cmap

        status = cmap.convergence_tenant_fleet_sign_status_payload()
        self.assertTrue(status.get("ok"))


if __name__ == "__main__":
    unittest.main()
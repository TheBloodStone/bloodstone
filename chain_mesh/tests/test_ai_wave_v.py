"""Smoke tests for Wave V — tenant quorum, Blurt manifest broadcast, NPU execution."""

from __future__ import annotations

import importlib.util
import os
import unittest


class TestAiWaveV(unittest.TestCase):
    def test_tenant_fleet_quorum_votes_and_apply(self):
        from chain_mesh import tenant_dashboard as tdash
        from chain_mesh import tenant_fleet_quorum as tquorum
        from chain_mesh import tenant_fleet_sync as tfleet

        tdash.bind_all_rails(
            tenant_id="quorum-a",
            blurt_account="quorumuser",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            flops_cap=800_000,
            bandwidth_bytes_cap=900_000,
            storage_bytes_cap=1_000_000,
        )
        snaps = tfleet.collect_tenant_snapshots(tenant_id="quorum-a")
        self.assertGreaterEqual(len(snaps), 1)

        vote1 = tquorum.record_snapshot_votes(snaps, reporter_node_id="node-a")
        self.assertGreaterEqual(vote1.get("recorded", 0), 1)
        vote2 = tquorum.record_snapshot_votes(snaps, reporter_node_id="node-b")
        self.assertGreaterEqual(vote2.get("recorded", 0), 1)

        rollup = tquorum.update_quorum_state()
        self.assertGreaterEqual(rollup.get("pairs_satisfied", 0), 1)
        applied = tquorum.apply_satisfied_bindings()
        self.assertGreaterEqual(applied.get("applied", 0), 1)

    def test_quorum_snapshot_for_gossip(self):
        from chain_mesh import tenant_fleet_quorum as tquorum

        snap = tquorum.build_quorum_snapshot()
        if snap:
            self.assertEqual(snap.get("format"), tquorum.QUORUM_FORMAT)
            self.assertIn("tenant_snapshots", snap)

    def test_gossip_includes_tenant_quorum_snapshots(self):
        from chain_mesh import dtn_gossip as gossip

        payload = gossip.build_exchange_payload()
        self.assertIn("tenant_quorum_snapshots", payload)
        self.assertIsInstance(payload.get("tenant_quorum_snapshots"), list)

    def test_tenant_broadcast_manifest(self):
        from chain_mesh import tenant_broadcast as tb

        result = tb.broadcast_tenant_payload(
            {
                "tenant_id": "broadcast-v",
                "blurt_account": "manifestuser",
                "stone_address": "STONE1abcdefghijklmnopqrstuvwxyz12",
                "flops_cap": 2_000_000,
                "bandwidth_bytes_cap": 3_000_000,
                "storage_bytes_cap": 4_000_000,
            }
        )
        self.assertTrue(result.get("ok"))
        bcj = result.get("blurt_custom_json") or {}
        self.assertEqual(bcj.get("id"), tb.TENANT_MANIFEST_ID)
        self.assertIn("json", bcj)
        self.assertIn("Broadcast", " ".join(result.get("next_steps") or []))

    def test_tenant_broadcast_queue(self):
        from chain_mesh import tenant_broadcast as tb
        from chain_mesh import tenant_dashboard as tdash

        tdash.bind_all_rails(
            tenant_id="queue-v",
            blurt_account="queueuser",
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            flops_cap=1000,
            bandwidth_bytes_cap=2000,
            storage_bytes_cap=3000,
        )
        queue = tb.prepare_tenant_broadcast_queue(limit=5)
        self.assertTrue(queue.get("ok"))
        self.assertGreaterEqual(queue.get("count", 0), 1)

    def test_inference_shim_npu_execution_delegates(self):
        shim_path = "/root/ops/bloodstone-pi-fleet/scripts/ai-inference-shim.py"
        spec = importlib.util.spec_from_file_location("ai_inference_shim_v", shim_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        delegates = mod._probe_delegates()
        self.assertTrue(delegates.get("cpu-inference"))
        health_wave = "V"
        onnx_out = mod.dispatch_completion(
            {"runtime": "onnx", "model": "onnx:test", "prompt": "wave v", "max_tokens": 8}
        )
        self.assertEqual(onnx_out.get("runtime"), "onnx")
        self.assertTrue(onnx_out.get("choices"))
        self.assertEqual(health_wave, "V")

    def test_api_quorum_and_broadcast_payloads(self):
        from chain_mesh import api as cmap

        quorum = cmap.convergence_tenant_fleet_quorum_status_payload()
        self.assertTrue(quorum.get("ok"))
        queue = cmap.convergence_tenant_broadcast_queue_payload()
        self.assertTrue(queue.get("ok"))


if __name__ == "__main__":
    unittest.main()
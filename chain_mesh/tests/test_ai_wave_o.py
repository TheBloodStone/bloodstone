"""Smoke tests for Wave O — signed gossip + NPU detect."""

from __future__ import annotations

import os
import unittest


class TestAiWaveO(unittest.TestCase):
    def test_sign_and_verify_snapshot(self):
        from chain_mesh import ai_gossip_sign as gsign

        os.environ["AI_GOSSIP_SIGNING_KEY"] = "test-wave-o-secret"
        snap = gsign.sign_snapshot(
            {
                "provider_id": "pi-test-ai",
                "node_id": "pi-test",
                "runtimes": ["onnx"],
                "region": "lan",
                "last_seen": gsign._now(),
            },
            signer_node_id="pi-test",
        )
        self.assertIn("signature", snap)
        ok, reason = gsign.verify_snapshot(snap)
        self.assertTrue(ok, reason)

    def test_reject_tampered_snapshot(self):
        from chain_mesh import ai_gossip_sign as gsign

        os.environ["AI_GOSSIP_SIGNING_KEY"] = "test-wave-o-secret-2"
        snap = gsign.sign_snapshot(
            {
                "provider_id": "pi-tamper-ai",
                "node_id": "pi-tamper",
                "runtimes": ["cpu-inference"],
                "last_seen": gsign._now(),
            }
        )
        snap["load_ratio"] = 0.99
        ok, reason = gsign.verify_snapshot(snap)
        self.assertFalse(ok)
        self.assertIn("signature", reason)

    def test_npu_detect_disabled(self):
        from chain_mesh import ai_npu_detect as npu

        old = os.environ.get("AI_NPU_DETECT_ENABLE")
        os.environ["AI_NPU_DETECT_ENABLE"] = "0"
        try:
            result = npu.detect_npu_hardware()
            self.assertFalse(result.get("enabled"))
        finally:
            if old is None:
                os.environ.pop("AI_NPU_DETECT_ENABLE", None)
            else:
                os.environ["AI_NPU_DETECT_ENABLE"] = old

    def test_ingest_gossip_rejects_bad_signature_when_strict(self):
        from chain_mesh import ai_gossip_sign as gsign
        from chain_mesh import ai_routing as ai

        os.environ["AI_GOSSIP_SIGNING_KEY"] = "ingest-test-key"
        os.environ["AI_GOSSIP_ALLOW_UNSIGNED"] = "0"
        result = ai.ingest_gossip_snapshots(
            [
                {
                    "provider_id": "rogue-node-ai",
                    "node_id": "rogue-node",
                    "runtimes": ["cpu-inference"],
                    "last_seen": gsign._now(),
                }
            ]
        )
        self.assertEqual(result.get("recorded"), 0)
        self.assertGreaterEqual(result.get("rejected"), 1)
        os.environ["AI_GOSSIP_ALLOW_UNSIGNED"] = "1"


if __name__ == "__main__":
    unittest.main()
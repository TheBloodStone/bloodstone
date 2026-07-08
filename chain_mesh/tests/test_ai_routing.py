"""Smoke tests for Wave M/N AI routing."""

from __future__ import annotations

import json
import unittest


class TestAiRouting(unittest.TestCase):
    def test_score_provider_min_flops(self):
        from chain_mesh import ai_routing as ai

        job = {
            "region": "lan",
            "flops_budget": 1_000_000_000,
            "body": {"ai_spec": {"runtime": "llama.cpp", "min_flops_per_sec": 1_000_000_000}},
        }
        weak = {
            "provider_id": "weak-ai",
            "runtimes": '["llama.cpp"]',
            "flops_per_sec": 100_000,
            "load_ratio": 0,
            "offline_capable": 1,
            "source": "local",
            "region": "lan",
            "last_seen": ai._now(),
            "models_json": "[]",
        }
        strong = dict(weak)
        strong["provider_id"] = "strong-ai"
        strong["flops_per_sec"] = 2_000_000_000
        self.assertEqual(ai.score_provider(weak, job, offline_mode=True), -1)
        self.assertGreater(ai.score_provider(strong, job, offline_mode=True), -1)

    def test_pick_best_with_negative_score(self):
        from chain_mesh import ai_routing as ai

        provider = {"provider_id": "p1"}
        best = ai.pick_best_provider([(provider, -5.0)])
        self.assertIsNotNone(best)
        self.assertEqual(best[0]["provider_id"], "p1")

    def test_validate_ai_spec(self):
        from chain_mesh import ai_provider as aip

        spec = aip.validate_ai_spec(
            {"runtime": "llama.cpp", "max_tokens": 100},
            job_type="inference",
        )
        self.assertEqual(spec["runtime"], "llama.cpp")
        self.assertIsNone(aip.validate_ai_spec({}, job_type="batch"))

    def test_parse_ai_runtimes(self):
        from chain_mesh import ai_routing as ai

        self.assertEqual(ai._parse_ai_runtimes(["TFLite", "cpu-inference"]), ["tflite", "cpu-inference"])
        self.assertEqual(ai._parse_ai_runtimes("llama.cpp, onnx"), ["llama.cpp", "onnx"])

    def test_lan_ai_registry_synthesis(self):
        from chain_mesh import ai_provider as aip
        from chain_mesh import ai_routing as ai
        from chain_mesh import lan_registry as lan

        lan.register_lan_node(
            device_id="test-pixel-ai",
            public_ip="203.0.113.10",
            lan_ip="192.168.55.10",
            ai_runtimes=["tflite"],
            ai_inference_port=8090,
        )
        result = ai.discover_ai_providers()
        self.assertTrue(result.get("ok"))
        provider = aip.get_ai_provider(provider_id="test-pixel-ai-ai")
        self.assertIsNotNone(provider)
        endpoints = json.loads((provider or {}).get("endpoints_json") or "{}")
        self.assertIn("health_url", endpoints)
        self.assertIn("inference_url", endpoints)

    def test_coordinator_stub_complete(self):
        from chain_mesh import ai_routing as ai
        from chain_mesh import compute_job as cjobs

        cjobs.init_compute_job_db()
        manifest = cjobs.build_compute_job_manifest(
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            job_id="job-wave-n-stub-01",
            job_type="inference",
            flops_budget=1000,
            ai_spec={"runtime": "cpu-inference"},
        )
        cjobs.index_compute_job(body=manifest["body"])
        result = ai._coordinator_stub_complete(job_id="job-wave-n-stub-01")
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("output_asset_key"))
        job = cjobs.get_compute_job(job_id="job-wave-n-stub-01")
        self.assertEqual(job.get("status"), "completed")

    def test_ingest_ai_callback_completed(self):
        from chain_mesh import ai_routing as ai
        from chain_mesh import compute_job as cjobs

        cjobs.init_compute_job_db()
        manifest = cjobs.build_compute_job_manifest(
            stone_address="STONE1abcdefghijklmnopqrstuvwxyz12",
            job_id="job-wave-n-callback-01",
            job_type="inference",
            flops_budget=1000,
            ai_spec={"runtime": "cpu-inference"},
        )
        cjobs.index_compute_job(body=manifest["body"])
        output_key = "a" * 64
        result = ai.ingest_ai_callback(
            {
                "job_id": "job-wave-n-callback-01",
                "status": "completed",
                "output_asset_key": output_key,
                "provider_id": ai.COORDINATOR_AI_ID,
            }
        )
        self.assertTrue(result.get("ok"))
        job = cjobs.get_compute_job(job_id="job-wave-n-callback-01")
        self.assertEqual(job.get("status"), "completed")
        self.assertEqual(job.get("output_asset_key"), output_key)


if __name__ == "__main__":
    unittest.main()
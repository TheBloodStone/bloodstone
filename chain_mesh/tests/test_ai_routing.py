"""Smoke tests for Wave M AI routing."""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
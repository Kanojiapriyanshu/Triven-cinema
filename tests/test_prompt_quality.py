import unittest

from app.services.prompt_quality import evaluate_plan_prompt_coverage


class PromptQualityTests(unittest.TestCase):
    def test_reports_full_coverage_when_terms_are_preserved(self):
        report = evaluate_plan_prompt_coverage(
            "Astronaut walks across a red Martian desert with dust and mountains",
            [
                "An astronaut walks across a red Martian desert while fine dust moves near distant mountains."
            ],
        )
        self.assertGreaterEqual(report["coverage_score"], 0.9)
        self.assertEqual(report["missing_terms"], [])

    def test_reports_missing_terms(self):
        report = evaluate_plan_prompt_coverage(
            "Astronaut walks across a red Martian desert with dust and mountains",
            ["A person walks across an empty desert."],
        )
        self.assertLess(report["coverage_score"], 1.0)
        self.assertIn("astronaut", report["missing_terms"])


if __name__ == "__main__":
    unittest.main()

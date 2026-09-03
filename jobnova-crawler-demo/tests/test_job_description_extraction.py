import unittest
from tempfile import TemporaryDirectory

from job_description_extraction.evaluation import evaluate_text
from job_description_extraction.pipeline import HybridExtractor
from job_description_extraction.rules import RuleRegistry


SAMPLE_HTML = """
<html><head><script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "description": "<h2>About the role</h2><p>Build reliable data products for our analytics teams and customers.</p><h2>Responsibilities</h2><ul><li>Design batch and streaming pipelines using Python and SQL.</li><li>Test data quality and monitor production workflows.</li><li>Partner with analysts and platform engineers on trusted datasets.</li><li>Document lineage, ownership, and operational runbooks.</li></ul>"
}
</script></head>
<body><nav>Recommended jobs</nav><main>Page content</main><footer>Privacy policy</footer></body></html>
"""


class HybridExtractorTests(unittest.TestCase):
    def test_empty_extraction_has_no_contamination(self):
        metrics = evaluate_text("", "Required job description")
        self.assertEqual(0.0, metrics.completeness_recall)
        self.assertEqual(0.0, metrics.contamination_rate)
        self.assertFalse(metrics.full_extraction)

    def test_structured_data_wins_without_llm(self):
        with TemporaryDirectory() as temporary_directory:
            registry = RuleRegistry(f"{temporary_directory}/rules.json")
            extractor = HybridExtractor(registry=registry, confidence_threshold=0.4)

            result = extractor.extract("https://example.test/jobs/1", SAMPLE_HTML, mode="hybrid")

            self.assertTrue(result.successful)
            self.assertEqual("structured_data", result.strategy)
            self.assertIn("Design batch and streaming pipelines", result.description_text)
            self.assertNotIn("Recommended jobs", result.description_text)

    def test_metrics_detect_missing_and_extra_content(self):
        metrics = evaluate_text("build pipelines unrelated", "build reliable pipelines")
        self.assertLess(metrics.completeness_recall, 1.0)
        self.assertGreater(metrics.contamination_rate, 0.0)
        self.assertFalse(metrics.full_extraction)

    def test_metrics_require_structure_preservation(self):
        truth = "Responsibilities\n\n- Build pipelines\n- Test data"
        flattened = "Responsibilities Build pipelines Test data"
        metrics = evaluate_text(flattened, truth)
        self.assertEqual(1.0, metrics.accuracy_f1)
        self.assertLess(metrics.structure_recall, 0.95)
        self.assertFalse(metrics.full_extraction)


if __name__ == "__main__":
    unittest.main()

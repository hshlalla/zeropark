import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zeropark_gateway.catalog import get_reference_catalog, reference_by_id


class ReferenceCatalogTests(unittest.TestCase):
    def test_catalog_maps_capabilities_to_references(self) -> None:
        ids = {ref["id"] for ref in get_reference_catalog()}
        self.assertIn("crawl4ai", ids)
        self.assertIn("presenton", ids)

    def test_restricted_licenses_are_marked_no_copy(self) -> None:
        # Dify (restricted) and SearXNG (AGPL) must never be copied into the product.
        self.assertFalse(reference_by_id("dify").copy_allowed)
        self.assertFalse(reference_by_id("searxng").copy_allowed)
        # MIT/Apache references may be copied with attribution.
        self.assertTrue(reference_by_id("crawl4ai").copy_allowed)

    def test_unknown_reference_raises(self) -> None:
        with self.assertRaises(KeyError):
            reference_by_id("missing")


if __name__ == "__main__":
    unittest.main()

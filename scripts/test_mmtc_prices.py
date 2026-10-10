"""Checks that supplier outages or older PDFs cannot damage the published feed."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import mmtc_prices as sync


class PriceSyncTests(unittest.TestCase):
    def test_rejects_timestamp_regression_and_future_list(self):
        now = datetime(2026, 10, 10, 12, tzinfo=sync.IST)
        old = {"listTime": (now - timedelta(hours=1)).isoformat()}
        sync.validate_timestamp(now - timedelta(minutes=30), old, now)
        with self.assertRaises(ValueError):
            sync.validate_timestamp(now - timedelta(days=1), old, now)
        with self.assertRaises(ValueError):
            sync.validate_timestamp(now + timedelta(hours=1), old, now)

    def test_retries_supplier_failure(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"%PDF-valid"
        with patch.object(sync.urllib.request, "urlopen",
                          side_effect=[OSError("timeout"), response]) as fetch:
            with patch.object(sync.time, "sleep"):
                self.assertEqual(sync.fetch_pdf(), b"%PDF-valid")
        self.assertEqual(fetch.call_count, 2)

    def test_bad_supplier_response_leaves_feed_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "prices.json"
            original = '{"listTime":"2026-10-10T09:30:04+05:30"}\n'
            target.write_text(original)
            with patch.object(sync, "OUT", str(target)):
                with patch.object(sync, "fetch_pdf", side_effect=OSError("offline")):
                    with self.assertRaises(OSError):
                        sync.main()
            self.assertEqual(target.read_text(), original)

    def test_missing_weight_leaves_feed_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "prices.json"
            original = '{"listTime":"2026-10-10T09:30:04+05:30"}\n'
            target.write_text(original)
            with patch.object(sync, "OUT", str(target)):
                with patch.object(sync, "fetch_pdf", return_value=b"%PDF-test"):
                    with patch.object(sync, "read_pdf", return_value="GOLD\n10 October 2026 9:30:04 AM"):
                        with self.assertRaises(ValueError):
                            sync.main()
            self.assertEqual(target.read_text(), original)


if __name__ == "__main__":
    unittest.main()

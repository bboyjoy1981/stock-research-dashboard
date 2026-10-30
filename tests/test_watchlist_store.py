import json
import tempfile
import unittest
from pathlib import Path

from src.watchlist_store import load_watchlist, save_watchlist


class WatchlistStoreTests(unittest.TestCase):
    def test_roundtrip_normalizes_and_deduplicates_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "watchlist.json"
            save_watchlist(path, ["1", "000001", "600000"])
            self.assertEqual(load_watchlist(path), ["000001", "600000"])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["codes"], ["000001", "600000"])

    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_watchlist(Path(directory) / "missing.json"), [])


if __name__ == "__main__":
    unittest.main()

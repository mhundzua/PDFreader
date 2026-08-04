import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from organize import month_folder_name, sanitize, unique_path  # noqa: E402


class TestSanitize(unittest.TestCase):
    def test_removes_unsafe_characters(self):
        self.assertEqual(sanitize("A/B:C*D", "fallback"), "A_B_C_D")

    def test_collapses_whitespace(self):
        self.assertEqual(sanitize("  DD   214  ", "fallback"), "DD 214")

    def test_empty_uses_fallback(self):
        self.assertEqual(sanitize("", "fallback"), "fallback")
        self.assertEqual(sanitize(None, "fallback"), "fallback")


class TestMonthFolderName(unittest.TestCase):
    def test_full_date(self):
        self.assertEqual(month_folder_name("2026-08-04"), "2026-08 August")

    def test_year_month_only(self):
        self.assertEqual(month_folder_name("2025-01"), "2025-01 January")

    def test_missing_date(self):
        self.assertEqual(month_folder_name(None), "Unknown-Date")
        self.assertEqual(month_folder_name(""), "Unknown-Date")

    def test_unparseable_date(self):
        self.assertEqual(month_folder_name("not a date"), "Unknown-Date")


class TestUniquePath(unittest.TestCase):
    def test_no_collision(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "file.pdf"
            self.assertEqual(unique_path(path), path)

    def test_collision_increments(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "file.pdf"
            path.write_text("x")
            self.assertEqual(unique_path(path), Path(tmp) / "file (2).pdf")
            (Path(tmp) / "file (2).pdf").write_text("x")
            self.assertEqual(unique_path(path), Path(tmp) / "file (3).pdf")


if __name__ == "__main__":
    unittest.main()

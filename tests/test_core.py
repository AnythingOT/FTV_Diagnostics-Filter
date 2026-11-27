"""Tests for the parsing / filtering core. Run:  python -m unittest discover tests"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ft_diagnostic_filter import (build_matcher, main, parse_items,  # noqa: E402
                                  read_text, write_csv)

SAMPLE = ROOT / "samples" / "sample_export.xml"


def C(text, field="message"):
    return {"field": field, "op": "contains", "text": text}


def X(text, field="message"):
    return {"field": field, "op": "does not contain", "text": text}


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = parse_items(read_text(SAMPLE))

    def run_filter(self, filters, **kw):
        m = build_matcher(filters, **kw)
        return [i["message"] for i in self.items if m(i)]

    def test_parses_utf16_and_skips_garbage(self):
        self.assertEqual(len(self.items), 5)

    def test_gt_inside_attribute_not_truncated(self):
        self.assertIn("Level > 90 on Demo_Tank_3 DataLog", [i["message"] for i in self.items])

    def test_single_quotes_uppercase_keys_entities(self):
        last = self.items[-1]
        self.assertEqual(last["username"], "admin")
        self.assertEqual(last["message"], "User login & role change conveyor_a_speed")

    def test_contains(self):
        self.assertEqual(len(self.run_filter([C("DataLog")])), 3)

    def test_contains_and_exclude(self):
        self.assertEqual(self.run_filter([C("DataLog"), X("Off")]),
                         ["DataLogOn Conveyor_A_Speed_01", "Level > 90 on Demo_Tank_3 DataLog"])

    def test_any_mode(self):
        self.assertEqual(len(self.run_filter([C("Tank"), C("PLC")], include_mode="any")), 2)

    def test_all_mode_requires_every_term(self):
        self.assertEqual(self.run_filter([C("DataLog"), C("Tank")]),
                         ["Level > 90 on Demo_Tank_3 DataLog"])

    def test_case_sensitive(self):
        self.assertEqual(len(self.run_filter([C("Conveyor_A_Speed")], case_sensitive=True)), 2)
        self.assertEqual(len(self.run_filter([C("Conveyor_A_Speed")])), 3)

    def test_regex(self):
        self.assertEqual(len(self.run_filter([C(r"DataLog(On|Off)\b")], use_regex=True)), 2)

    def test_other_fields_and_any_field(self):
        self.assertEqual(self.run_filter([C("HMI-DEMO-02", "any field"), X("system", "username")]),
                         ["Level > 90 on Demo_Tank_3 DataLog"])

    def test_only_excludes_and_blank_rows(self):
        self.assertEqual(len(self.run_filter([X("DataLog"), C("   ")])), 2)

    def test_many_rows_each_keep_own_keyword(self):
        # guards the late-binding closure bug: every rule must use its own text
        rules = [C(w) for w in ("DataLog", "Conveyor", "Speed", "_A_", "01")] + [X("Tank"), X("Off")]
        self.assertEqual(self.run_filter(rules), ["DataLogOn Conveyor_A_Speed_01"])

    def test_write_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.csv"
            self.assertEqual(write_csv(out, self.items), 5)
            with out.open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(rows[2]["message"], "Level > 90 on Demo_Tank_3 DataLog")

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "cli.csv"
            rc = main([str(SAMPLE), "-c", "DataLog", "-x", "Off", "-o", str(out)])
            self.assertEqual(rc, 0)
            with out.open(encoding="utf-8-sig", newline="") as f:
                self.assertEqual(len(list(csv.DictReader(f))), 2)


if __name__ == "__main__":
    unittest.main()

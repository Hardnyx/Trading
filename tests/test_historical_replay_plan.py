"""The full-engine preflight must never infer readiness from partial evidence."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.historical_sources import MARKET_COMMIT, PROTOCOL, SERIES, archive, canonical
from scripts.historical_replay_plan import DEPENDENCIES, build_plan, write_plan
from scripts import historical_replay_plan as planner
from tests.test_historical_sources import record, nport
from scripts.historical_sources import parse_nport, sha
import base64


class HistoricalReplayPlan(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cuts = ["2022-10-31", "2022-11-30"]
        macro = {}
        for cut in self.cuts:
            pointer, _ = archive(self.root, f"macro/{cut}/DGS3MO.json.gz", record(cut))
            macro[cut] = {"DGS3MO": {**pointer, "status": "available"}}
        filing = {"accessionNumber": "0000000001-22-000001", "filingDate": "2022-11-29", "reportDate": "2022-09-30"}
        raw = nport()
        source = {"filing": filing, "raw_base64": base64.b64encode(raw).decode(), "raw_sha256": sha(raw)}
        pointer, _ = archive(self.root, "sec/one.json.gz", source)
        self.manifest = {"protocol": PROTOCOL, "source_market_commit": MARKET_COMMIT,
                         "cuts": self.cuts, "series_ids": ["DGS3MO"], "macro": macro,
                         "sec": {"documents": [{**pointer, "form": "NPORT-P", "accession": filing["accessionNumber"],
                                                 "normalized": parse_nport(raw, filing)}]}}
        self.save()

    def save(self):
        (self.root / "manifest.json").write_bytes(canonical(self.manifest) + b"\n")

    def build(self):
        return build_plan(self.root, self.cuts, SERIES[:1])

    def test_public_holdings_are_date_specific_and_never_sufficient_for_engine(self):
        plan = self.build()
        first, second = plan["matrix"]
        self.assertEqual(first["components"]["spy_holdings_source"]["status"], "blocked")
        self.assertEqual(second["components"]["spy_holdings_source"]["status"], "verified-source")
        # Even fully explicit tickers in a published filing do not certify the
        # whole universe, all other ETF holdings, financials, or model parameters.
        for row in plan["matrix"]:
            self.assertEqual(row["components"]["macro_vintages"]["status"], "verified-source")
            self.assertFalse(row["full_engine_replay_eligible"])
            self.assertIsNone(row["forecast"])
            self.assertIsNone(row["orders"])
            for name in list(DEPENDENCIES)[2:]:
                self.assertEqual(row["components"][name]["status"], "blocked")
                self.assertTrue(row["components"][name]["blockers"])
        self.assertFalse(plan["engine_dispatch_enabled"])
        self.assertFalse(plan["independent_holdout_claimed"])
        self.assertEqual(plan["summary"]["full_engine_executed_cuts"], 0)

    def test_reaudits_bytes_and_preserves_failed_cut_instead_of_skipping_it(self):
        pointer = self.manifest["macro"][self.cuts[0]]["DGS3MO"]
        (self.root / pointer["path"]).write_bytes(b"corrupt")
        # Forged readiness files must not bypass source verification.
        (self.root / "readiness.json").write_text('{"full_replay_ready":true}')
        plan = self.build()
        self.assertEqual(plan["cuts"], self.cuts)
        self.assertEqual(len(plan["matrix"]), 2)
        self.assertEqual(plan["summary"]["macro_records_verified"], 1)
        self.assertEqual(plan["matrix"][0]["components"]["macro_vintages"]["status"], "blocked")
        self.assertIn("dependency:macro_vintages", plan["matrix"][0]["components"]["return_forecasts"]["blockers"])
        self.assertEqual(len(plan["errors"]), 1)

    def test_rejects_market_series_and_calendar_substitutions(self):
        base = copy.deepcopy(self.manifest)
        for key, value in [("source_market_commit", "other"), ("series_ids", ["DGS10"]), ("cuts", self.cuts[:1])]:
            self.manifest = {**base, key: value}
            self.save()
            with self.assertRaises(ValueError):
                self.build()
        self.manifest = base
        self.save()
        for cuts in [[], self.cuts[::-1], [self.cuts[0], self.cuts[0]]]:
            with self.assertRaises(ValueError):
                build_plan(self.root, cuts, SERIES[:1])

    def test_tampered_holdings_cannot_become_a_verified_source(self):
        self.manifest["sec"]["documents"][0]["normalized"]["available_after_day"] = "2022-01-01"
        self.save()
        plan = self.build()
        self.assertEqual(plan["summary"]["sec_holdings_documents_verified"], 0)
        self.assertTrue(plan["errors"])
        self.assertTrue(all(r["components"]["spy_holdings_source"]["status"] == "blocked" for r in plan["matrix"]))

    def test_reports_are_deterministic_and_csv_covers_every_cut_component(self):
        a, b = self.build(), self.build()
        self.assertEqual(a, b)
        target = self.root / "report"
        write_plan(a, target)
        first = {p.name: p.read_bytes() for p in target.iterdir()}
        write_plan(b, target)
        self.assertEqual(first, {p.name: p.read_bytes() for p in target.iterdir()})
        self.assertEqual(json.loads((target / "coverage.json").read_bytes()), a)
        with (target / "coverage.csv").open(newline="") as source:
            rows = list(csv.DictReader(source))
        self.assertEqual(len(rows), len(self.cuts) * len(DEPENDENCIES))
        self.assertEqual({row["cut"] for row in rows}, set(self.cuts))

    def test_strict_cli_writes_evidence_then_refuses_full_engine_readiness(self):
        project = self.root / "project"
        (project / "docs").mkdir(parents=True)
        (project / "docs/protocolo-replay-integral-v1.json").write_bytes(canonical({
            "source_market_commit": MARKET_COMMIT, "expected_cuts": self.cuts}))
        (project / "dist/assets/js").mkdir(parents=True)
        (project / "dist/assets/js/kernel.mjs").write_text("export const version = 1;\n")
        output = self.root / "strict"
        args = ["historical_replay_plan.py", "--input", str(self.root), "--output", str(output), "--require-full-engine"]
        with patch.object(planner, "ROOT", project), patch.object(planner, "account_origins", return_value=self.cuts), \
                patch.object(planner, "SERIES", SERIES[:1]), patch.object(planner.subprocess, "check_output", return_value=b"{}"), \
                patch("sys.argv", args), patch("builtins.print"):
            self.assertEqual(planner.main(), 2)
        result = json.loads((output / "coverage.json").read_bytes())
        self.assertFalse(result["engine_dispatch_enabled"])
        self.assertEqual(result["summary"]["full_engine_executed_cuts"], 0)
        self.assertEqual(len(result["statistical_protocol_sha256"]), 64)
        self.assertIn("dist/assets/js/kernel.mjs", result["engine_source_sha256"])


if __name__ == "__main__":
    unittest.main()

"""v3 admission audit on synthetic captures; no scores, no network."""
import gzip
import hashlib
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from scripts import v3_admission as va


def sha(b):
    return hashlib.sha256(b).hexdigest()


def bundle(root, cut="2026-11-30"):
    base = root / va.CAPTURES
    (base / "inputs").mkdir(parents=True)
    (base / "origins").mkdir()
    market, vol = b'{"m":1}', b'{"v":1}'
    (base / f"inputs/{cut}.market.json.gz").write_bytes(gzip.compress(market))
    (base / f"inputs/{cut}.volatility.json.gz").write_bytes(gzip.compress(vol))
    proposal = json.dumps({"positions": [{"symbol": "SPY", "weight": .95}, {"symbol": "CASH", "weight": .05}], "trade_plan": {"total": 1}})
    policy, sources = json.dumps({"seed": 1}), json.dumps({"a.mjs": "0" * 64})
    capture = {"cut": cut, "input_market_archive": f"inputs/{cut}.market.json.gz",
               "input_volatility_archive": f"inputs/{cut}.volatility.json.gz",
               "proposal_json": proposal, "policy_json": policy, "source_hashes_json": sources,
               "evidence": {"market_sha256": sha(market), "risk_calibration_sha256": sha(vol), "inputs_sha256": "x",
                            "model_sha256": sha(sources.encode()), "policy_sha256": sha(policy.encode()),
                            "forecast_sha256": sha(proposal.encode())}}
    origin = base / f"origins/{cut}.json.gz"
    origin.write_bytes(gzip.compress(json.dumps(capture).encode()))
    files = {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in base.rglob("*.gz")}
    return origin.relative_to(root).as_posix(), files


class V3AdmissionTests(unittest.TestCase):
    def test_next_open_skips_weekends(self):
        self.assertEqual(va.earliest_open_utc("2026-11-27").isoformat(), "2026-11-30T13:30:00+00:00")
        self.assertEqual(va.horizon_end("2026-11-30"), date(2026, 12, 29))

    def test_admission_requires_reproduced_hashes_and_timely_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            origin, files = bundle(root)
            on_time = [(datetime(2026, 11, 30, 23, 50, tzinfo=timezone.utc), files)]
            row = va.admit_origin(root, origin, on_time)
            self.assertTrue(row["admitted"], row["reasons"])
            self.assertEqual(row["held_symbols"], ["SPY"])
            late = [(datetime(2026, 12, 1, 15, 0, tzinfo=timezone.utc), files)]
            self.assertIn("stamped after the next possible open", " ".join(va.admit_origin(root, origin, late)["reasons"]))
            self.assertFalse(va.admit_origin(root, origin, [])["admitted"])
            market = root / va.CAPTURES / "inputs/2026-11-30.market.json.gz"
            market.write_bytes(gzip.compress(b'{"m":2}'))
            self.assertIn("do not reproduce", " ".join(va.admit_origin(root, origin, on_time)["reasons"]))

    def test_cashflows_need_issuer_history_observed_after_horizon_and_stamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            admission = {"cut": "2026-11-30", "held_symbols": ["SPY"]}
            self.assertFalse(va.cashflows_ready(root, admission, [], today=date(2026, 12, 15))["ready"])
            folder = root / "data/distributions/histories/SPY"
            folder.mkdir(parents=True)
            history = folder / "h.json"
            history.write_text(json.dumps({"observed_at": "2027-01-02T02:00:00+00:00", "records": []}))
            stamps = [(datetime(2027, 1, 2, 3, 0, tzinfo=timezone.utc),
                       {history.relative_to(root).as_posix(): sha(history.read_bytes())})]
            self.assertTrue(va.cashflows_ready(root, admission, stamps, today=date(2027, 1, 5))["ready"])
            self.assertEqual(va.cashflows_ready(root, admission, [], today=date(2027, 1, 5))["missing_distribution_sources"], ["SPY"])

    def test_repository_audit_runs_without_scores(self):
        result = va.audit()
        self.assertFalse(result["scores_read"])
        self.assertEqual(result["admitted"], sum(r["admitted"] for r in result["rows"]))


if __name__ == "__main__":
    unittest.main()

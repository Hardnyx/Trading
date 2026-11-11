"""Independent as-of selection tests against Bloomberg collector v4's real warehouse."""
import copy
import sqlite3
import unittest

from scripts.historical_bloomberg_asof_replay import verify_asof_selection

CUT = "2024-12-31T16:00:00-05:00"
PUBLISHED = "2024-12-31T21:00:00Z"
RETRIEVED = "2026-11-11T14:00:00Z"


class IndependentAsOfReplayTests(unittest.TestCase):
    def setUp(self):
        # No Bloomberg package or private data is needed by CI.
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("CREATE TABLE pit_records(record_id TEXT PRIMARY KEY,record_json TEXT)")
        self.addCleanup(self.connection.close)

    def row(self, *, dataset="identifier_history", field="cusip", value="594918104",
            available=PUBLISHED, observation=None, valid_from="2020-01-01",
            valid_until="2030-01-01", vintage="v1", revision="v1", quality="VERIFIED_PIT",
            synthetic=False, effective=None, period=None):
        return dict(dataset_id=dataset, security_id="ID-1", field=field, value=value,
                    observation_date=observation, period_end=period, target_period=None,
                    member_id=None, valid_from=valid_from, valid_until=valid_until,
                    first_available_at=available, effective_at=effective,
                    vintage_id=vintage, revision_id=revision, quality_class=quality,
                    synthetic=synthetic, unit="identifier", currency=None, adjusted_basis=None)

    def store(self, record):
        from scripts.historical_bloomberg_asof_replay import canonical
        import hashlib
        raw = canonical(record)
        digest = hashlib.sha256(raw).hexdigest()
        self.connection.execute("INSERT INTO pit_records VALUES(?,?)", (digest, raw.decode()))
        self.connection.commit()
        return record

    def stage(self, rows):
        return dict(schema="bloomberg-trading-stage-v1", cutoff=CUT,
                    normalized_asof_records=rows)

    def test_selected_row_matches_stage(self):
        row = self.store(self.row())
        out = verify_asof_selection(self.connection, self.stage([row]))
        self.assertEqual(out["warehouse_asof_rows_independently_reselected"], 1)
        self.assertEqual(out["warehouse_records_examined_for_asof"], 1)
        self.assertTrue(out["stage_asof_selection_independently_recomputed"])
        self.assertFalse(out["vendor_publication_time_independently_authenticated"])
        self.assertFalse(out["historical_engine_replay_authorized"])

    def test_missing_entire_available_row_is_rejected(self):
        self.store(self.row())
        with self.assertRaisesRegex(ValueError, "selection differs"):
            verify_asof_selection(self.connection, self.stage([]))

    def test_older_revised_version_is_not_admissible(self):
        old = self.store(self.row(value="A", vintage="v1", available="2024-12-30T20:00:00Z"))
        new = self.store(self.row(value="B", vintage="v2", available=PUBLISHED))
        with self.assertRaisesRegex(ValueError, "selection differs"):
            verify_asof_selection(self.connection, self.stage([old]))
        out = verify_asof_selection(self.connection, self.stage([new]))
        self.assertEqual(out["warehouse_asof_rows_independently_reselected"], 1)
        self.assertEqual(out["warehouse_records_examined_for_asof"], 2)

    def test_silently_added_earlier_version_does_not_change_latest_selection(self):
        new = self.store(self.row(value="B", vintage="v2", available=PUBLISHED))
        self.store(self.row(value="A", vintage="v1", available="2024-12-30T20:00:00Z"))
        verify_asof_selection(self.connection, self.stage([new]))

    def test_cutoff_excludes_future_publication_and_observation(self):
        self.store(self.row(value="F", available="2025-01-01T00:00:00Z"))
        self.store(self.row(dataset="daily_prices", field="close", value=1.2,
                            observation="2025-01-02", valid_from=None, valid_until=None))
        out = verify_asof_selection(self.connection, self.stage([]))
        self.assertEqual(out["warehouse_asof_rows_independently_reselected"], 0)
        self.assertEqual(out["warehouse_asof_excluded_record_counts"]["future-observation"], 1)
        self.assertEqual(out["warehouse_asof_excluded_record_counts"]["missing-or-future-availability"], 1)

    def test_expired_and_future_identity_intervals_excluded(self):
        self.store(self.row(value="A", valid_until="2024-12-31"))
        self.store(self.row(value="B", valid_from="2025-01-01"))
        out = verify_asof_selection(self.connection, self.stage([]))
        self.assertEqual(out["warehouse_asof_excluded_record_counts"]["expired-identity"], 1)
        self.assertEqual(out["warehouse_asof_excluded_record_counts"]["future-identity"], 1)

    def test_same_order_different_values_is_rejected(self):
        self.store(self.row(value="A"))
        self.store(self.row(value="B"))
        with self.assertRaisesRegex(ValueError, "Conflicting Bloomberg values"):
            verify_asof_selection(self.connection, self.stage([]))

    def test_reconstructed_or_synthetic_rows_are_excluded(self):
        self.store(self.row(quality="RECONSTRUCTED_WITH_PROVENANCE"))
        self.store(self.row(quality="VERIFIED_PIT", synthetic=True))
        out = verify_asof_selection(self.connection, self.stage([]))
        self.assertEqual(out["warehouse_asof_excluded_record_counts"]["ineligible-quality-or-synthetic"], 2)

    def test_future_effective_event_excluded(self):
        self.store(self.row(effective="2025-01-01T00:00:00Z"))
        out = verify_asof_selection(self.connection, self.stage([]))
        self.assertEqual(out["warehouse_asof_excluded_record_counts"]["future-effective-event"], 1)

    def test_stage_extra_row_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "selection differs"):
            verify_asof_selection(self.connection, self.stage([self.row()]))

    def test_repeated_stage_row_is_rejected(self):
        row = self.store(self.row())
        with self.assertRaisesRegex(ValueError, "selection differs"):
            verify_asof_selection(self.connection, self.stage([row, copy.deepcopy(row)]))

    def test_wrong_record_digest_is_rejected_even_if_stage_matches(self):
        row = self.store(self.row())
        self.connection.execute("UPDATE pit_records SET record_id=?", ("0"*64,))
        self.connection.commit()
        with self.assertRaisesRegex(ValueError, "record digest"):
            verify_asof_selection(self.connection, self.stage([row]))

    def test_naive_cutoff_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "naive as-of timestamp"):
            verify_asof_selection(self.connection, self.stage([]) | {"cutoff": "2024-12-31T16:00:00"})


if __name__ == "__main__":
    unittest.main()

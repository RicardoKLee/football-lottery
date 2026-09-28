"""Tests for score safety, diagnostic-only adaptation and pool applicability."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scope_fixtures import regular_history, target_match, verified_snapshot
import model_core
import match_context


class HistoryScopeTests(unittest.TestCase):
    def normalize(self, raw, provider="fixture"):
        from history_adapter import normalize_history_record
        return normalize_history_record(raw, provider, raw.get("context", {}))

    def test_fractional_score_is_rejected(self):
        raw = regular_history()[0]
        raw["home_score"] = 1.5
        with self.assertRaisesRegex(ValueError, "invalid_regulation_score"):
            self.normalize(raw)

    def test_invalid_scores_are_not_coerced(self):
        for value in (True, False, -1, float("nan"), float("inf"), "1", None):
            for side in ("home_score", "away_score"):
                with self.subTest(value=value, side=side):
                    raw = regular_history()[0]
                    raw[side] = value
                    with self.assertRaisesRegex(ValueError, "invalid_regulation_score"):
                        self.normalize(raw)

    def test_final_score_without_explicit_regulation_is_rejected(self):
        for duration in ("EXTRA_TIME", "PENALTY_SHOOTOUT", "REGULAR", None):
            raw = regular_history()[0]
            del raw["home_score"], raw["away_score"]
            raw["score"] = {"duration": duration, "fullTime": {"home": 2, "away": 1}}
            with self.subTest(duration=duration), self.assertRaisesRegex(ValueError, "regulation_score_unknown"):
                self.normalize(raw)

    def test_explicit_regulation_wins_over_final_score(self):
        raw = regular_history()[0]
        raw.update(home_score=1, away_score=1)
        raw["score"] = {"duration": "EXTRA_TIME", "fullTime": {"home": 2, "away": 1}}
        result = self.normalize(raw)
        self.assertEqual((result["home_score"], result["away_score"]), (1, 1))

    def test_unconfirmed_provider_keys_are_not_guessed(self):
        for keys in ({"home": 1, "away": 1}, {"homeTeam": 1, "awayTeam": 1}):
            raw = regular_history()[0]
            del raw["home_score"], raw["away_score"]
            raw["score"] = {"regularTime": keys}
            with self.assertRaisesRegex(ValueError, "regulation_score_unknown"):
                self.normalize(raw, "football-data.org")

    def test_unknown_basis_and_missing_context_are_rejected(self):
        raw = regular_history()[0]
        raw["context"]["score_basis"] = "unknown"
        with self.assertRaises(ValueError):
            self.normalize(raw)
        del raw["context"]
        with self.assertRaises(ValueError):
            self.normalize(raw)

    def test_normalization_is_idempotent_and_keeps_neutral_context(self):
        raw = regular_history(venue="neutral")[0]
        original = copy.deepcopy(raw)
        raw["home_score"] = 2.0
        result = self.normalize(raw)
        self.assertEqual(self.normalize(result), result)
        self.assertEqual(result["context"], original["context"])
        self.assertEqual(result["competition_code"], "J1")
        self.assertIs(type(result["home_score"]), int)
        self.assertEqual(model_core.finished_matches_before([result])[0], result)

    def test_source_self_assertions_cannot_grant_verification(self):
        raw = regular_history()[0]
        raw["provenance_status"] = "verified"
        result = self.normalize(raw, "unconfirmed-provider")
        self.assertEqual(result["provenance_status"], "unverified")
        self.assertIn("history_source_unverified", result["quality_reasons"])

    def test_current_identity_status_and_competition_are_required(self):
        for field, value in (("match_id", "12"), ("status", "SCHEDULED"),
                             ("competition_code", " "), ("home_team", {"team_id": "1", "name": "A"})):
            raw = regular_history()[0]
            raw[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.normalize(raw)

    def test_timezone_is_not_inferred_and_input_is_not_mutated(self):
        raw = regular_history()[0]
        before = copy.deepcopy(raw)
        self.normalize(raw)
        self.assertEqual(raw, before)
        raw["kickoff_utc"] = "2026-09-01T12:00:00"
        with self.assertRaises(ValueError):
            self.normalize(raw)

    def test_prepare_preserves_row_context_and_rejects_mixed_type(self):
        from history_adapter import prepare_history
        home = regular_history()[0]
        neutral = regular_history(venue="neutral")[1]
        national = regular_history(team_type="national")[2]
        records, rejected = prepare_history([neutral, national, home], "fixture", home["context"])
        self.assertEqual([row["context"]["venue"] for row in records], ["home", "neutral"])
        self.assertEqual(rejected, [{"match_id": national["match_id"],
                                     "reason": "history_team_type_mismatch"}])

    def test_prepare_audits_every_rejection(self):
        from history_adapter import prepare_history
        good, bad, unfinished = regular_history()[:3]
        bad["home_score"] = 1.5
        unfinished["status"] = "SCHEDULED"
        records, rejected = prepare_history([good, bad, unfinished, None], "fixture", good["context"])
        self.assertEqual(len(records), 1)
        self.assertEqual(rejected, [
            {"match_id": bad["match_id"], "reason": "invalid_regulation_score"},
            {"match_id": unfinished["match_id"], "reason": "history_not_finished"},
            {"match_id": None, "reason": "invalid_history_record"}])

    def test_zero_usable_history_is_error_with_rejections(self):
        from history_adapter import prepare_history
        raw = regular_history()[0]
        raw["home_score"] = None
        with self.assertRaisesRegex(ValueError, "no_usable_history") as caught:
            prepare_history([raw], "fixture", raw["context"])
        self.assertEqual(caught.exception.rejected_records,
                         [{"match_id": raw["match_id"], "reason": "invalid_regulation_score"}])
        with self.assertRaisesRegex(ValueError, "no_usable_history"):
            model_core.finished_matches_before([])

    def test_model_entry_rejects_fractional_and_unmapped_provider_scores(self):
        raw = regular_history()[0]
        raw["home_score"] = 1.5
        with self.assertRaises(model_core.ModelDataError):
            model_core.normalize_history_match(raw)
        raw = {"id": 1, "utcDate": "2026-09-01T12:00:00Z", "status": "FINISHED",
               "homeTeam": {"id": 1, "name": "A"}, "awayTeam": {"id": 2, "name": "B"},
               "score": {"fullTime": {"home": 2, "away": 1}}}
        with self.assertRaises(model_core.ModelDataError):
            model_core.normalize_history_match(raw)


class SamplePoolTests(unittest.TestCase):
    def reasons(self, matches=None, target=None, pool=None):
        return match_context.sample_pool_reasons(
            regular_history() if matches is None else matches,
            target_match() if target is None else target,
            verified_snapshot()["sample_pool"] if pool is None else pool)

    def test_connected_declared_pool_is_applicable(self):
        self.assertEqual(self.reasons(), [])
        self.assertEqual(self.reasons(regular_history("national"), target_match("national"),
                         {"pool_id": "fixture:national", "team_type": "national", "competition_codes": ["J1"]}), [])

    def test_unknown_mixed_and_undeclared_samples_are_not_silently_filtered(self):
        for field, value, reason in (("team_type", "national", "history_team_type_mismatch"),
                                     ("team_type", "unknown", "history_team_type_unknown"),
                                     ("competition_code", "CUP", "history_competition_undeclared")):
            matches = regular_history()
            if field == "competition_code":
                matches[-1][field] = value
            else:
                matches[-1]["context"][field] = value
            with self.subTest(field=field, value=value):
                self.assertIn(reason, self.reasons(matches))

    def test_invalid_pool_or_target_is_rejected(self):
        for pool in ({}, {"pool_id": "p", "team_type": "club", "competition_codes": []},
                     {"pool_id": "p", "team_type": "unknown", "competition_codes": ["J1"]}):
            self.assertIn("sample_pool_invalid", self.reasons(pool=pool))
        self.assertIn("target_team_type_mismatch", self.reasons(target=target_match("national")))
        self.assertIn("target_competition_undeclared", self.reasons(target=target_match(competition_code="CUP")))

    def test_disconnected_graph_and_missing_team_are_rejected(self):
        matches = regular_history()
        for item in matches:
            item["home_team"]["team_id"] = "fixture:Alpha"
            item["away_team"]["team_id"] = "fixture:Gamma"
        other = copy.deepcopy(matches[0])
        other["home_team"]["team_id"] = "fixture:Beta"
        other["away_team"]["team_id"] = "other:Alpha"
        self.assertIn("history_pools_disconnected", self.reasons(matches + [other]))
        self.assertIn("history_pools_disconnected", self.reasons(matches))

    def test_future_and_equal_kickoff_edges_cannot_connect_pool(self):
        for date in ("2026-09-13T12:00:00Z", "2026-09-14T12:00:00Z"):
            matches = regular_history()
            for item in matches:
                item["kickoff_utc"] = date
            self.assertIn("history_pools_disconnected", self.reasons(matches))

    def test_cross_competition_connected_pool_requires_explicit_declaration(self):
        matches = regular_history()
        matches[0]["competition_code"] = "CUP"
        pool = verified_snapshot()["sample_pool"]
        pool["competition_codes"].append("CUP")
        self.assertEqual(self.reasons(matches, pool=pool), [])


if __name__ == "__main__":
    unittest.main()

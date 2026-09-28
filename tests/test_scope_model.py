import copy
import unittest

from model_core import (
    COMPETITION_NAMES,
    MODEL_NAME,
    ModelDataError,
    ModelParameters,
    build_elo_ratings,
    create_prediction,
    expected_home_result,
)
from scope_fixtures import regular_history, target_match, verified_snapshot


class NeutralModelTests(unittest.TestCase):
    def test_neutral_equal_strength_expectation(self):
        self.assertEqual(expected_home_result(1500, 1500, 0), 0.5)

    def test_single_neutral_draw_does_not_change_equal_elo(self):
        match = {
            "match_id": "fixture:1",
            "kickoff_utc": "2026-09-01T12:00:00Z",
            "status": "FINISHED",
            "competition_code": "J1",
            "home_team": {"team_id": "fixture:A", "name": "A", "aliases": []},
            "away_team": {"team_id": "fixture:B", "name": "B", "aliases": []},
            "home_score": 1,
            "away_score": 1,
            "context": {
                "team_type": "club",
                "competition_type": "league",
                "venue": "neutral",
                "score_basis": "regulation",
            },
        }
        ratings, counts = build_elo_ratings([match])
        self.assertEqual(ratings["fixture:A"], 1500.0)
        self.assertEqual(ratings["fixture:B"], 1500.0)

    def test_same_history_with_home_venue_changes_elo(self):
        match = {
            "match_id": "fixture:1",
            "kickoff_utc": "2026-09-01T12:00:00Z",
            "status": "FINISHED",
            "competition_code": "J1",
            "home_team": {"team_id": "fixture:A", "name": "A", "aliases": []},
            "away_team": {"team_id": "fixture:B", "name": "B", "aliases": []},
            "home_score": 1,
            "away_score": 1,
            "context": {
                "team_type": "club",
                "competition_type": "league",
                "venue": "home",
                "score_basis": "regulation",
            },
        }
        ratings, counts = build_elo_ratings([match])
        self.assertNotEqual(ratings["fixture:A"], 1500.0)
        self.assertNotEqual(ratings["fixture:B"], 1500.0)

    def _symmetric_history(self, team_type="club", venue="neutral"):
        history = []
        for i in range(1, 7):
            home = "fixture:A" if i % 2 == 1 else "fixture:B"
            away = "fixture:B" if i % 2 == 1 else "fixture:A"
            history.append({
                "match_id": f"fixture:hist-{i}",
                "kickoff_utc": f"2026-09-{i:02d}T12:00:00Z",
                "status": "FINISHED",
                "competition_code": "J1",
                "home_team": {"team_id": home, "name": home, "aliases": []},
                "away_team": {"team_id": away, "name": away, "aliases": []},
                "home_score": 1,
                "away_score": 1,
                "context": {
                    "team_type": team_type,
                    "competition_type": "league",
                    "venue": venue,
                    "score_basis": "regulation",
                },
            })
        return history

    def test_symmetric_history_and_neutral_target_has_equal_expected_goals(self):
        history = self._symmetric_history(venue="neutral")
        target = {
            "match_id": "fixture:target",
            "kickoff_utc": "2026-09-10T12:00:00Z",
            "competition_code": "J1",
            "home_team": {"team_id": "fixture:A", "name": "A", "aliases": []},
            "away_team": {"team_id": "fixture:B", "name": "B", "aliases": []},
            "context": {
                "team_type": "club",
                "competition_type": "league",
                "venue": "neutral",
                "score_basis": "regulation",
            },
        }
        snapshot = verified_snapshot()
        prediction = create_prediction(history, target, snapshot)
        self.assertEqual(
            prediction["expected_goals"]["home"],
            prediction["expected_goals"]["away"],
        )
        self.assertEqual(
            prediction["probabilities"]["had"]["H"],
            prediction["probabilities"]["had"]["A"],
        )

    def test_unknown_venue_target_is_insufficient_with_venue_unknown_reason(self):
        history = self._symmetric_history(venue="home")
        target = {
            "match_id": "fixture:target",
            "kickoff_utc": "2026-09-10T12:00:00Z",
            "competition_code": "J1",
            "home_team": {"team_id": "fixture:A", "name": "A", "aliases": []},
            "away_team": {"team_id": "fixture:B", "name": "B", "aliases": []},
            "context": {
                "team_type": "club",
                "competition_type": "league",
                "venue": "unknown",
                "score_basis": "regulation",
            },
        }
        snapshot = verified_snapshot()
        prediction = create_prediction(history, target, snapshot)
        self.assertEqual(prediction["quality"]["status"], "insufficient")
        self.assertIn("venue_unknown", prediction["quality"]["missing_data"])

    def test_non_five_league_and_cup_and_national_not_rejected_by_whitelist(self):
        history = regular_history(team_type="club")
        target = target_match(team_type="club", venue="neutral", competition_code="J1")
        snapshot = verified_snapshot()
        prediction = create_prediction(history, target, snapshot)
        self.assertEqual(prediction["match"]["competition_code"], "J1")
        self.assertEqual(prediction["model"]["name"], "football-elo-poisson")

        nat_history = regular_history(team_type="national")
        for m in nat_history:
            m["competition_code"] = "CUP-X"
            m["context"]["competition_type"] = "cup"
        nat_target = target_match(team_type="national", venue="neutral", competition_code="CUP-X")
        nat_target["context"]["competition_type"] = "cup"
        nat_snapshot = {
            "provider": "fixture",
            "source_url": "https://example.invalid/fixture",
            "fetched_at": "2026-09-13T10:00:00Z",
            "provenance_status": "verified",
            "sample_pool": {
                "pool_id": "fixture:CUP-X",
                "team_type": "national",
                "competition_codes": ["CUP-X"],
            },
        }
        nat_pred = create_prediction(nat_history, nat_target, nat_snapshot)
        self.assertEqual(nat_pred["match"]["competition_code"], "CUP-X")
        self.assertEqual(nat_pred["model"]["parameters"]["profile"], "national-baseline")


if __name__ == "__main__":
    unittest.main()

import copy
import unittest

from backtest_model import run_walk_forward
from model_core import ModelParameters
from scope_fixtures import regular_history


class WalkForwardScopeTests(unittest.TestCase):
    def test_non_top_five_runs_without_future_data(self):
        report = run_walk_forward(
            regular_history(), "J1", min_training_matches=4,
            parameters=ModelParameters(min_team_matches=1)
        )
        self.assertIn("football_elo_poisson", report["metrics"])
        self.assertGreater(len(report["audit"]), 0)
        for item in report["audit"]:
            self.assertLess(item["latest_training_kickoff_utc"], item["target_kickoff_utc"])

    def test_neutral_target_passes_neutral_to_simple_elo(self):
        history = regular_history(venue="neutral")
        report = run_walk_forward(
            history, "J1", min_training_matches=4,
            parameters=ModelParameters(min_team_matches=1)
        )
        self.assertEqual(report["competition_code"], "J1")

    def test_same_kickoff_matches_do_not_train_each_other(self):
        history = regular_history()
        # Duplicate match with same kickoff
        extra = copy.deepcopy(history[4])
        extra["match_id"] = "fixture:extra"
        combined = history + [extra]
        report = run_walk_forward(
            combined, "J1", min_training_matches=4,
            parameters=ModelParameters(min_team_matches=1)
        )
        for item in report["audit"]:
            self.assertLess(item["latest_training_kickoff_utc"], item["target_kickoff_utc"])

    def test_no_eligible_matches_raises_value_error(self):
        with self.assertRaises(ValueError):
            run_walk_forward(regular_history()[:3], "J1", min_training_matches=10)


if __name__ == "__main__":
    unittest.main()

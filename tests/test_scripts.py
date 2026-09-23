#!/usr/bin/env python3

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import backtest_model
import contracts
import fetch_lottery_data
import fetch_match_data
import generate_betting_recommendation as betting
import generate_betting_recommendation_strict as strict_betting
import model_core
import simulate_stochastic_prediction as stochastic

NOW = datetime(2026, 8, 25, 8, 0, tzinfo=timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def make_history():
    matches = []
    results = [
        ("1", "2", 2, 0),
        ("3", "1", 1, 1),
        ("2", "3", 1, 0),
        ("1", "3", 3, 1),
        ("2", "1", 1, 2),
        ("3", "2", 0, 0),
        ("1", "2", 1, 0),
        ("2", "3", 2, 1),
        ("3", "1", 0, 2),
    ]
    names = {"1": "Alpha FC", "2": "Beta FC", "3": "Gamma FC"}
    for index, (home_id, away_id, home_goals, away_goals) in enumerate(results):
        matches.append(
            {
                "id": f"history-{index}",
                "utcDate": iso(NOW - timedelta(days=90 - index * 7)),
                "status": "FINISHED",
                "homeTeam": {"id": int(home_id), "name": names[home_id]},
                "awayTeam": {"id": int(away_id), "name": names[away_id]},
                "score": {"fullTime": {"home": home_goals, "away": away_goals}},
            }
        )
    return matches


def make_prediction(match_id="sporttery:1001", quality="sufficient", home_probability=0.60):
    away_probability = 0.16
    draw_probability = 1.0 - home_probability - away_probability
    score = {
        "0-0": 0.08,
        "1-0": 0.22,
        "1-1": 0.18,
        "2-0": 0.16,
        "2-1": 0.16,
        "0-1": 0.08,
        "1-2": 0.07,
        "0-2": 0.05,
    }
    ttg = {"s0": 0.08, "s1": 0.30, "s2": 0.39, "s3": 0.16, "s4": 0.05, "s5": 0.01, "s6": 0.005, "s7": 0.005}
    return {
        "schema_version": "2.0",
        "kind": "model_prediction",
        "model": {"name": "club-league-elo-poisson", "version": "2.0.0", "parameters": {}},
        "match": {
            "match_id": match_id,
            "lottery_match_id": match_id,
            "competition_code": "PL",
            "competition_name": "Premier League",
            "kickoff_utc": iso(NOW + timedelta(hours=8)),
            "home_team": {"team_id": "65", "name": "Manchester City FC", "aliases": ["曼城"]},
            "away_team": {"team_id": "66", "name": "Manchester United FC", "aliases": ["曼联"]},
        },
        "data_snapshot": {
            "provider": "football-data.org",
            "source_url": "https://api.football-data.org/v4/competitions/PL/matches",
            "fetched_at": iso(NOW - timedelta(minutes=10)),
        },
        "expected_goals": {"home": 1.8, "away": 0.9},
        "probabilities": {
            "had": {"H": home_probability, "D": draw_probability, "A": away_probability},
            "score": score,
            "ttg": ttg,
        },
        "quality": {
            "status": quality,
            "missing_data": [] if quality == "sufficient" else ["insufficient_home_history"],
        },
    }


def make_odds_snapshot(fetched_at=None, available=True):
    fetched_at = fetched_at or NOW - timedelta(seconds=30)
    return {
        "schema_version": "2.0",
        "kind": "odds_snapshot",
        "provider": "china-sporttery",
        "source_url": fetch_lottery_data.SPORTTERY_API_URL,
        "source_mode": "live",
        "fetched_at": iso(fetched_at),
        "requested_date": "2026-08-25",
        "matches": [
            {
                "match_id": "sporttery:1001",
                "provider_match_id": "1001",
                "match_num": "周二001",
                "competition": "英超",
                "match_date": "2026-08-25",
                "kickoff_utc": iso(NOW + timedelta(hours=8)),
                "cutoff_utc": iso(NOW + timedelta(hours=7, minutes=55)),
                "cutoff_is_estimated": True,
                "sale_status": "listed_by_official_api" if available else "closed",
                "is_available": available,
                "availability_reasons": [] if available else ["sale_closed"],
                "odds_observed_at": iso(fetched_at),
                "home_team": {"name": "曼城", "provider_id": None},
                "away_team": {"name": "曼联", "provider_id": None},
                "odds": {
                    "had": {"h": 2.00, "d": 3.60, "a": 5.50},
                    "hhad": None,
                    "ttg": None,
                    "hafu": None,
                    "crs": None,
                },
            }
        ],
    }


class TestContracts(unittest.TestCase):
    def test_should_accept_complete_model_prediction(self):
        prediction = make_prediction()

        result = contracts.validate_model_prediction(prediction)

        self.assertIs(result, prediction)

    def test_should_reject_prediction_when_probability_distribution_is_invalid(self):
        prediction = make_prediction()
        prediction["probabilities"]["had"]["H"] = 0.9

        with self.assertRaises(contracts.ContractError):
            contracts.validate_model_prediction(prediction)

    def test_should_reject_odds_snapshot_when_required_time_is_missing(self):
        snapshot = make_odds_snapshot()
        del snapshot["fetched_at"]

        with self.assertRaises(contracts.ContractError):
            contracts.validate_odds_snapshot(snapshot)


class TestClubModel(unittest.TestCase):
    def test_should_apply_home_advantage_to_equal_ratings(self):
        home_expectation = model_core.expected_home_result(1500.0, 1500.0, home_advantage_elo=60.0)

        self.assertGreater(home_expectation, 0.5)

    def test_should_build_club_elo_from_finished_matches(self):
        ratings, counts = model_core.build_elo_ratings(make_history(), home_advantage_elo=60.0)

        self.assertEqual(set(ratings), {"1", "2", "3"})
        self.assertGreater(counts["1"], 0)
        self.assertGreater(ratings["1"], ratings["3"])

    def test_should_resolve_team_by_stable_id_or_exact_alias_only(self):
        teams = model_core.collect_teams(make_history())

        by_id = model_core.resolve_team("1", teams)
        by_name = model_core.resolve_team("Alpha FC", teams)

        self.assertEqual(by_id["team_id"], "1")
        self.assertEqual(by_name["team_id"], "1")
        with self.assertRaises(model_core.TeamResolutionError):
            model_core.resolve_team("Alpha", teams)

    def test_should_reject_malformed_finished_history_instead_of_silently_dropping_it(self):
        malformed = make_history()
        malformed[0]["score"]["fullTime"]["home"] = None

        with self.assertRaises(model_core.ModelDataError):
            model_core.finished_matches_before(malformed)

    def test_should_merge_current_registry_for_team_without_league_history(self):
        history_teams = model_core.collect_teams(make_history())
        registry = [{"team_id": "4", "name": "Promoted FC", "aliases": ["升班马"]}]

        teams = fetch_match_data.merge_team_registry(history_teams, registry)

        self.assertEqual(model_core.resolve_team("4", teams)["name"], "Promoted FC")

    def test_should_create_structured_club_prediction_without_world_cup_fields(self):
        prediction = model_core.create_prediction(
            history_matches=make_history(),
            match={
                "match_id": "future-1",
                "competition_code": "PL",
                "competition_name": "Premier League",
                "season": "2026",
                "kickoff_utc": iso(NOW + timedelta(hours=8)),
                "home_team": {"team_id": "1", "name": "Alpha FC", "aliases": ["阿尔法"]},
                "away_team": {"team_id": "2", "name": "Beta FC", "aliases": ["贝塔"]},
            },
            data_snapshot={
                "provider": "fixture",
                "source_url": "tests",
                "fetched_at": iso(NOW),
            },
            parameters=model_core.ModelParameters(min_team_matches=2),
        )

        contracts.validate_model_prediction(prediction)
        serialized = json.dumps(prediction, ensure_ascii=False).lower()
        self.assertNotIn("world cup", serialized)
        self.assertNotIn("wc2026", serialized)
        self.assertNotIn("average_age", serialized)
        self.assertAlmostEqual(sum(prediction["probabilities"]["had"].values()), 1.0, places=9)
        self.assertAlmostEqual(sum(prediction["probabilities"]["score"].values()), 1.0, places=9)
        self.assertAlmostEqual(sum(prediction["probabilities"]["ttg"].values()), 1.0, places=9)


class TestLotteryData(unittest.TestCase):
    def raw_match(self, sale_status=None):
        match = {
            "matchId": "1001",
            "matchNumStr": "周三001",
            "matchDate": "2026-08-26",
            "matchTime": "20:00:00",
            "homeTeamAbbName": "曼城",
            "awayTeamAbbName": "曼联",
            "leagueAbbName": "英超",
            "had": {"h": "2.00", "d": "3.60", "a": "5.50"},
        }
        if sale_status is not None:
            match["sellStatus"] = sale_status
        return {"success": True, "value": {"matchInfoList": [{"businessDate": "2026-08-26", "subMatchList": [match]}]}}

    def test_should_treat_future_match_listed_by_live_official_api_as_available(self):
        snapshot = fetch_lottery_data.parse_odds_data(
            self.raw_match(), fetched_at=NOW, source_mode="live", now=NOW
        )

        self.assertEqual(snapshot["matches"][0]["sale_status"], "listed_by_official_api")
        self.assertTrue(snapshot["matches"][0]["is_available"])

    def test_should_fail_closed_when_file_snapshot_has_no_sale_status(self):
        snapshot = fetch_lottery_data.parse_odds_data(
            self.raw_match(), fetched_at=NOW, source_mode="file", now=NOW
        )

        self.assertFalse(snapshot["matches"][0]["is_available"])
        self.assertIn("sale_status_unknown", snapshot["matches"][0]["availability_reasons"])

    def test_should_reject_explicitly_closed_match(self):
        snapshot = fetch_lottery_data.parse_odds_data(
            self.raw_match("0"), fetched_at=NOW, source_mode="live", now=NOW
        )

        self.assertFalse(snapshot["matches"][0]["is_available"])
        self.assertIn("sale_closed", snapshot["matches"][0]["availability_reasons"])

    def test_should_filter_available_matches_by_date(self):
        snapshot = fetch_lottery_data.parse_odds_data(
            self.raw_match(), fetched_at=NOW, source_mode="live", now=NOW
        )

        matches = fetch_lottery_data.filter_matches(
            snapshot["matches"], date="2026-08-26", available_only=True
        )

        self.assertEqual(len(matches), 1)

    def test_should_record_invalid_provider_match_without_crashing(self):
        raw = {"success": True, "value": {"matchInfoList": [{"businessDate": "2026-08-26", "subMatchList": [None]}]}}

        snapshot = fetch_lottery_data.parse_odds_data(raw, fetched_at=NOW, now=NOW)

        self.assertEqual(snapshot["matches"], [])
        self.assertEqual(len(snapshot["parse_errors"]), 1)


class TestBettingAnalysis(unittest.TestCase):
    def test_should_calculate_normalized_market_probabilities(self):
        margin, payout, implied = betting.calculate_market_margin_and_implied_probs(
            {"h": 2.0, "d": 3.5, "a": 4.5}
        )

        self.assertGreater(margin, 0)
        self.assertLess(payout, 1)
        self.assertAlmostEqual(sum(implied.values()), 1.0, places=9)

    def test_should_return_no_recommendation_when_odds_snapshot_is_stale(self):
        snapshot = make_odds_snapshot(fetched_at=NOW - timedelta(hours=1))

        report = betting.analyze_daily(
            snapshot, [make_prediction()], now=NOW, max_odds_age_seconds=900
        )

        self.assertEqual(report["recommendations"], [])
        self.assertTrue(any(item["reason"] == "odds_snapshot_stale" for item in report["rejections"]))

    def test_should_return_no_recommendation_when_prediction_is_insufficient(self):
        report = betting.analyze_daily(
            make_odds_snapshot(), [make_prediction(quality="insufficient")], now=NOW
        )

        self.assertEqual(report["recommendations"], [])
        self.assertTrue(any(item["reason"] == "prediction_quality_insufficient" for item in report["rejections"]))

    def test_should_use_real_odds_and_keep_unallocated_cash(self):
        report = betting.analyze_daily(
            make_odds_snapshot(),
            [make_prediction()],
            now=NOW,
            bankroll=200.0,
            probability_haircut=0.02,
            min_ev_low=0.05,
        )

        self.assertEqual(len(report["recommendations"]), 1)
        recommendation = report["recommendations"][0]
        self.assertEqual(recommendation["odds"], 2.0)
        self.assertGreater(recommendation["ev_low"], 0.05)
        self.assertGreater(report["bankroll"]["cash_reserved"], 0.0)
        self.assertLess(report["bankroll"]["staked"], 200.0)

    def test_should_not_create_odds_when_match_cannot_be_mapped(self):
        prediction = make_prediction(match_id="different-id")
        prediction["match"]["lottery_match_id"] = "different-id"
        prediction["match"]["home_team"]["aliases"] = []
        prediction["match"]["away_team"]["aliases"] = []

        report = betting.analyze_daily(make_odds_snapshot(), [prediction], now=NOW)

        self.assertEqual(report["recommendations"], [])
        self.assertTrue(any(item["reason"] == "prediction_not_found" for item in report["rejections"]))

    def test_should_not_trust_available_flag_when_sale_status_is_closed(self):
        snapshot = make_odds_snapshot()
        snapshot["matches"][0]["sale_status"] = "closed"
        snapshot["matches"][0]["is_available"] = True

        report = betting.analyze_daily(snapshot, [make_prediction()], now=NOW)

        self.assertEqual(report["recommendations"], [])
        self.assertTrue(any(item["reason"] == "match_not_available" for item in report["rejections"]))

    def test_should_not_evaluate_incomplete_market(self):
        snapshot = make_odds_snapshot()
        snapshot["matches"][0]["odds"]["had"] = {"h": 2.0, "d": 3.6}

        report = betting.analyze_daily(snapshot, [make_prediction()], now=NOW)

        self.assertEqual(report["recommendations"], [])
        self.assertTrue(any(item["reason"] == "no_selection_above_ev_threshold" for item in report["rejections"]))

    def test_should_cap_total_exposure_without_forcing_full_bankroll(self):
        bets = [
            {"bet_id": str(index), "kelly_fraction": 0.10, "odds": 2.0}
            for index in range(10)
        ]

        allocated, summary = betting.allocate_bankroll(
            bets, bankroll=200.0, unit=2.0, max_total_exposure=0.20
        )

        self.assertLessEqual(summary["staked"], 40.0)
        self.assertGreaterEqual(summary["cash_reserved"], 160.0)
        self.assertTrue(all(item["stake"] % 2 == 0 for item in allocated))

    def test_should_reject_negative_conservative_ev_threshold(self):
        with self.assertRaises(ValueError):
            betting.analyze_daily(
                make_odds_snapshot(), [make_prediction()], now=NOW, min_ev_low=-0.01
            )

    def test_should_build_parlays_from_different_matches_only(self):
        bets = [
            {"bet_id": "a", "match_id": "m1", "probability": 0.6, "conservative_probability": 0.57, "odds": 2.0},
            {"bet_id": "b", "match_id": "m1", "probability": 0.4, "conservative_probability": 0.37, "odds": 3.0},
            {"bet_id": "c", "match_id": "m2", "probability": 0.55, "conservative_probability": 0.52, "odds": 2.1},
        ]

        parlays = betting.build_two_leg_parlays(bets, min_ev_low=0.0)

        self.assertTrue(parlays)
        for parlay in parlays:
            self.assertEqual(len(set(parlay["match_ids"])), 2)


class TestStochasticPrediction(unittest.TestCase):
    def test_should_be_reproducible_when_seed_is_supplied(self):
        first = stochastic.run_monte_carlo_simulation(
            "Alpha FC", "Beta FC", 1.6, 1.0, num_samples=500, seed=42
        )
        second = stochastic.run_monte_carlo_simulation(
            "Alpha FC", "Beta FC", 1.6, 1.0, num_samples=500, seed=42
        )

        self.assertEqual(first, second)
        self.assertEqual(first["parameters"]["seed"], 42)
        self.assertAlmostEqual(sum(first["probabilities"].values()), 1.0, places=9)


class TestWalkForwardBacktest(unittest.TestCase):
    def test_should_evaluate_only_with_matches_before_target_kickoff(self):
        report = backtest_model.run_walk_forward(
            make_history(),
            competition_code="PL",
            min_training_matches=3,
            parameters=model_core.ModelParameters(min_team_matches=1),
        )

        self.assertGreater(report["evaluated_matches"], 0)
        self.assertEqual(report["method"], "walk_forward")
        self.assertTrue(
            all(
                item["latest_training_kickoff_utc"] < item["target_kickoff_utc"]
                for item in report["audit"]
            )
        )

    def test_should_exclude_other_match_with_same_kickoff_from_training(self):
        history = make_history()
        history[4]["utcDate"] = history[3]["utcDate"]

        report = backtest_model.run_walk_forward(
            history,
            competition_code="PL",
            min_training_matches=3,
            parameters=model_core.ModelParameters(min_team_matches=1),
        )

        self.assertTrue(
            all(
                item["latest_training_kickoff_utc"] < item["target_kickoff_utc"]
                for item in report["audit"]
            )
        )

    def test_should_report_model_and_simple_elo_metrics(self):
        report = backtest_model.run_walk_forward(
            make_history(),
            competition_code="PL",
            min_training_matches=3,
            parameters=model_core.ModelParameters(min_team_matches=1),
        )

        for model_name in ("club_league_elo_poisson", "simple_home_elo"):
            metrics = report["metrics"][model_name]
            self.assertGreaterEqual(metrics["log_loss"], 0.0)
            self.assertGreaterEqual(metrics["brier_score"], 0.0)
            self.assertGreaterEqual(metrics["ranked_probability_score"], 0.0)
            self.assertTrue(0.0 <= metrics["expected_calibration_error"] <= 1.0)


class TestPredictionFileIO(unittest.TestCase):
    def test_should_write_json_atomically(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "prediction.json")

            contracts.write_json(path, make_prediction())

            with open(path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            self.assertEqual(loaded["kind"], "model_prediction")

    def test_should_reject_markdown_as_prediction_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "prediction.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("# prediction")

            with self.assertRaises(contracts.ContractError):
                strict_betting.load_predictions([path])


if __name__ == "__main__":
    unittest.main()

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
                "match_id": f"fixture:history-{index}",
                "kickoff_utc": iso(NOW - timedelta(days=90 - index * 7)),
                "status": "FINISHED",
                "competition_code": "PL",
                "context": {"team_type": "club", "competition_type": "league",
                            "venue": "home", "score_basis": "regulation"},
                "home_team": {"team_id": f"fixture:{home_id}", "name": names[home_id]},
                "away_team": {"team_id": f"fixture:{away_id}", "name": names[away_id]},
                "home_score": home_goals, "away_score": away_goals,
                "synthetic": True,
            }
        )
    return matches


def make_prediction(match_id="sporttery:1001", quality="sufficient", home_probability=0.60, provenance_status="unverified"):
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
        "kind": "model_prediction",
        "model": {"name": "football-elo-poisson", "parameters": {}},
        "match": {
            "match_id": match_id,
            "lottery_match_id": match_id,
            "competition_code": "PL",
            "competition_name": "Premier League",
            "kickoff_utc": iso(NOW + timedelta(hours=8)),
            "context": {"team_type": "club", "competition_type": "league", "venue": "home", "score_basis": "regulation"},
            "home_team": {"team_id": "football-data.org:65", "name": "Manchester City FC", "aliases": ["曼城"]},
            "away_team": {"team_id": "football-data.org:66", "name": "Manchester United FC", "aliases": ["曼联"]},
        },
        "data_snapshot": {
            "provider": "football-data.org",
            "source_url": "https://api.football-data.org/v4/competitions/PL/matches",
            "fetched_at": iso(NOW - timedelta(minutes=10)),
            "provenance_status": provenance_status,
            "sample_pool": {"pool_id": "fixture:PL", "team_type": "club", "competition_codes": ["PL"]},
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
                "official_listing": {
                    "status": "confirmed" if available else "unknown",
                    "source_url": fetch_lottery_data.SPORTTERY_API_URL,
                    "observed_at": iso(fetched_at),
                    "provider_match_id": "1001",
                },
                "market_status": {
                    "had": "open" if available else "closed",
                    "hhad": "open" if available else "closed",
                    "ttg": "open" if available else "closed",
                    "crs": "open" if available else "closed",
                },
                "match_num": "周二001",
                "competition": "英超",
                "match_date": "2026-08-25",
                "kickoff_utc": iso(NOW + timedelta(hours=8)),
                "cutoff_utc": iso(NOW + timedelta(hours=7, minutes=55)),
                "cutoff_is_estimated": True,
                "sale_status": "open" if available else "closed",
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

        self.assertEqual(set(ratings), {"fixture:1", "fixture:2", "fixture:3"})
        self.assertGreater(counts["fixture:1"], 0)
        self.assertGreater(ratings["fixture:1"], ratings["fixture:3"])

    def test_should_resolve_team_by_stable_id_or_exact_alias_only(self):
        teams = model_core.collect_teams(make_history())

        by_id = model_core.resolve_team("fixture:1", teams)
        by_name = model_core.resolve_team("Alpha FC", teams)

        self.assertEqual(by_id["team_id"], "fixture:1")
        self.assertEqual(by_name["team_id"], "fixture:1")
        with self.assertRaises(model_core.TeamResolutionError):
            model_core.resolve_team("Alpha", teams)

    def test_should_reject_malformed_finished_history_instead_of_silently_dropping_it(self):
        malformed = make_history()
        malformed[0]["home_score"] = None

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
                "match_id": "fixture:future-1",
                "competition_code": "PL",
                "competition_name": "Premier League",
                "season": "2026",
                "kickoff_utc": iso(NOW + timedelta(hours=8)),
                "context": {"team_type": "club", "competition_type": "league", "venue": "home", "score_basis": "regulation"},
                "home_team": {"team_id": "fixture:1", "name": "Alpha FC", "aliases": ["阿尔法"]},
                "away_team": {"team_id": "fixture:2", "name": "Beta FC", "aliases": ["贝塔"]},
            },
            data_snapshot={
                "provider": "fixture",
                "source_url": "https://example.invalid/fixture",
                "fetched_at": iso(NOW),
                "provenance_status": "verified",
                "sample_pool": {"pool_id": "fixture:PL", "team_type": "club", "competition_codes": ["PL"]},
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
            self.raw_match("open"), fetched_at=NOW, source_mode="live", now=NOW
        )

        self.assertEqual(snapshot["matches"][0]["sale_status"], "open")
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
            self.raw_match("open"), fetched_at=NOW, source_mode="live", now=NOW
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
            snapshot, [make_prediction(provenance_status="verified")], now=NOW, max_odds_age_seconds=900
        )

        self.assertEqual(report["recommendations"], [])
        self.assertTrue(any(item["reason"] == "odds_snapshot_stale" for item in report["rejections"]))

    def test_should_return_no_recommendation_when_prediction_is_insufficient(self):
        report = betting.analyze_daily(
            make_odds_snapshot(), [make_prediction(quality="insufficient", provenance_status="verified")], now=NOW
        )

        self.assertEqual(report["recommendations"], [])
        self.assertTrue(any(item["reason"] == "prediction_quality_insufficient" for item in report["rejections"]))

    def test_should_use_real_odds_and_keep_unallocated_cash(self):
        report = betting.analyze_daily(
            make_odds_snapshot(),
            [make_prediction(provenance_status="verified")],
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
        prediction = make_prediction(match_id="fixture:different-id", provenance_status="verified")
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

        report = betting.analyze_daily(snapshot, [make_prediction(provenance_status="verified")], now=NOW)

        self.assertEqual(report["recommendations"], [])
        self.assertTrue(any(item["reason"] == "match_not_available" for item in report["rejections"]))

    def test_should_not_evaluate_incomplete_market(self):
        snapshot = make_odds_snapshot()
        snapshot["matches"][0]["odds"]["had"] = {"h": 2.0, "d": 3.6}

        report = betting.analyze_daily(snapshot, [make_prediction(provenance_status="verified")], now=NOW)

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

    def test_should_build_four_leg_mixed_parlays_with_handicap_labels(self):
        bets = [
            {"bet_id": "m1:had:h", "match_id": "m1", "match_num": "周二001", "home_team": "TeamA", "market": "had", "option": "h", "probability": 0.6, "conservative_probability": 0.57, "odds": 2.0},
            {"bet_id": "m2:hhad:h", "match_id": "m2", "match_num": "周二002", "home_team": "TeamB", "market": "hhad", "option": "h", "goal_line": -1, "probability": 0.5, "conservative_probability": 0.47, "odds": 2.5},
            {"bet_id": "m3:ttg:s2", "match_id": "m3", "match_num": "周二003", "home_team": "TeamC", "market": "ttg", "option": "s2", "probability": 0.45, "conservative_probability": 0.42, "odds": 3.4},
            {"bet_id": "m4:crs:1-0", "match_id": "m4", "match_num": "周二004", "home_team": "TeamD", "market": "crs", "option": "1-0", "probability": 0.35, "conservative_probability": 0.32, "odds": 5.0},
        ]
        parlays = betting.build_multi_leg_parlays(bets, leg_count=4, min_ev_low=0.0)
        self.assertEqual(len(parlays), 1)
        p = parlays[0]
        self.assertEqual(p["type"], "4_leg_parlay")
        self.assertEqual(len(p["legs"]), 4)
        self.assertEqual(len(set(p["match_ids"])), 4)
        self.assertAlmostEqual(p["odds"], 2.0 * 2.5 * 3.4 * 5.0, places=2)
        # Verify leg labels include market and goal_line
        self.assertIn("周二001 TeamA(HAD-h)", p["leg_labels"])
        self.assertIn("周二002 TeamB(HHAD(-1)-h)", p["leg_labels"])
        self.assertIn("周二003 TeamC(TTG-s2)", p["leg_labels"])
        self.assertIn("周二004 TeamD(CRS-1-0)", p["leg_labels"])

    def test_should_enforce_sporttery_mixed_parlay_leg_limits(self):
        # Sporttery: CRS allows max 4 legs
        bets = [
            {"bet_id": f"m{i}:had:h", "match_id": f"m{i}", "market": "had", "option": "h", "probability": 0.7, "conservative_probability": 0.65, "odds": 1.8}
            for i in range(1, 5)
        ]
        bets.append(
            {"bet_id": "m5:crs:1-0", "match_id": "m5", "market": "crs", "option": "1-0", "probability": 0.5, "conservative_probability": 0.45, "odds": 4.0}
        )
        # 5-leg parlay containing CRS should be rejected by official max allowed legs limit
        parlays = betting.build_multi_leg_parlays(bets, leg_count=5, min_ev_low=0.0)
        self.assertEqual(len(parlays), 0)

    def test_should_render_subsections_in_markdown_for_singles_and_parlays(self):
        report = {
            "generated_at": "2026-08-25T08:00:00Z",
            "policy": {"probability_haircut": 0.03, "min_ev_low": 0.05, "max_divergence_ratio": 2.0, "max_single_odds": 70.0, "max_total_exposure": 0.5},
            "recommendations": [
                {"match_num": "周二001", "home_team": "TeamA", "away_team": "TeamB", "market": "had", "option": "h", "odds": 2.0, "probability": 0.6, "conservative_probability": 0.57, "ev_low": 0.14, "kelly_fraction": 0.05, "stake": 10.0},
                {"type": "two_leg_parlay", "leg_labels": ["周二001 TeamA(HAD-h)", "周二002 TeamB(HAD-h)"], "odds": 4.0, "probability": 0.36, "conservative_probability": 0.32, "ev_low": 0.28, "kelly_fraction": 0.02, "stake": 4.0},
                {"type": "4_leg_parlay", "leg_labels": ["周二001 TeamA(HAD-h)", "周二002 TeamB(HAD-h)", "周二003 TeamC(HAD-h)", "周二004 TeamD(HAD-h)"], "odds": 16.0, "probability": 0.13, "conservative_probability": 0.10, "ev_low": 0.60, "kelly_fraction": 0.01, "stake": 2.0},
            ],
            "rejections": [],
            "bankroll": {"total": 200, "staked": 16, "cash_reserved": 184},
        }
        md = betting.render_markdown(report)
        self.assertIn("### 单关投注建议", md)
        self.assertIn("### 2 串 1 混合过关建议", md)
        self.assertIn("### 4 串 1 混合过关建议", md)

    def test_strict_betting_cli_parlays_enabled_by_default(self):
        args = strict_betting.parse_args([])
        self.assertTrue(args.include_parlays)
        self.assertEqual(args.parlay_legs, [2, 4])

        args_disabled = strict_betting.parse_args(["--no-parlays"])
        self.assertFalse(args_disabled.include_parlays)

    def test_should_filter_non_single_bets_and_record_rejections_while_retaining_in_parlays(self):
        # 2 matches where HAD has positive EV, but Match 1 has had single_status=False, Match 2 has had single_status=True
        snap = make_odds_snapshot()
        match1 = dict(snap["matches"][0])
        match1["match_id"] = "sporttery:1001"
        match1["single_status"] = {"had": False, "hhad": False, "ttg": False, "crs": True}
        match1["odds"]["had"] = {"h": 2.10, "d": 3.40, "a": 3.80}

        match2 = dict(snap["matches"][0])
        match2["match_id"] = "sporttery:1002"
        match2["provider_match_id"] = "1002"
        match2["match_num"] = "周二002"
        match2["home_team"] = {"name": "TeamB", "provider_id": "2"}
        match2["away_team"] = {"name": "TeamC", "provider_id": "3"}
        match2["single_status"] = {"had": True, "hhad": False, "ttg": False, "crs": True}
        match2["odds"]["had"] = {"h": 2.10, "d": 3.40, "a": 3.80}

        snap["matches"] = [match1, match2]

        pred1 = make_prediction(match_id="sporttery:1001", provenance_status="verified", home_probability=0.65)
        pred2 = make_prediction(match_id="sporttery:1002", provenance_status="verified", home_probability=0.65)
        pred2["match"]["match_id"] = "sporttery:1002"
        pred2["match"]["lottery_match_id"] = "sporttery:1002"
        pred2["match"]["home_team"]["name"] = "TeamB"
        pred2["match"]["away_team"]["name"] = "TeamC"

        report = betting.analyze_daily(
            snap, [pred1, pred2], now=NOW, include_parlays=[2], probability_haircut=0.02
        )

        # Single recommendations should ONLY contain Match 2 (Match 1 was filtered out because single_status['had'] == False)
        singles = [r for r in report["recommendations"] if not str(r.get("type", "")).endswith("_leg_parlay")]
        self.assertEqual(len(singles), 1)
        self.assertEqual(singles[0]["match_id"], "sporttery:1002")

        # Rejection record MUST contain single_betting_not_allowed for Match 1
        filtered_rejections = [r for r in report["rejections"] if r.get("reason") == "single_betting_not_allowed"]
        self.assertEqual(len(filtered_rejections), 1)
        self.assertEqual(filtered_rejections[0]["match_id"], "sporttery:1001")
        self.assertIn("未开通单关固定奖", filtered_rejections[0]["detail"])

        # BUT Match 1 should still be present in 2-leg parlay!
        parlays = [r for r in report["recommendations"] if r.get("type") == "two_leg_parlay"]
        self.assertEqual(len(parlays), 1)
        self.assertIn("sporttery:1001", parlays[0]["match_ids"])
        self.assertIn("sporttery:1002", parlays[0]["match_ids"])

        # Markdown should contain the single filter explanation note
        md = betting.render_markdown(report)
        self.assertIn("单关销售限制说明", md)
        self.assertIn("未开通单关固定奖", md)

    def test_should_reject_market_divergence_above_threshold(self):
        snapshot = make_odds_snapshot()
        # Market implies ~8% home win prob, but model predicts 60% (divergence > 6x)
        snapshot["matches"][0]["odds"]["had"] = {"h": 10.0, "d": 2.0, "a": 1.9}
        prediction = make_prediction(provenance_status="verified", home_probability=0.60)

        report = betting.analyze_daily(
            snapshot, [prediction], now=NOW, max_divergence_ratio=2.0
        )

        self.assertEqual(report["recommendations"], [])
        self.assertTrue(any(item["reason"] == "no_selection_above_ev_threshold" for item in report["rejections"]))
        h_eval = next(e for e in report["evaluations"] if e["option"] == "h")
        self.assertIn("market_divergence_too_high", h_eval["rejection_reasons"])
        self.assertFalse(h_eval["eligible"])

    def test_should_reject_odds_above_ceiling(self):
        snapshot = make_odds_snapshot()
        snapshot["matches"][0]["odds"]["had"] = {"h": 25.0, "d": 3.0, "a": 1.4}
        prediction = make_prediction(provenance_status="verified", home_probability=0.60)

        report = betting.analyze_daily(
            snapshot, [prediction], now=NOW, max_single_odds=20.0, max_divergence_ratio=100.0
        )

        self.assertEqual(report["recommendations"], [])
        h_eval = next(e for e in report["evaluations"] if e["option"] == "h")
        self.assertIn("odds_above_ceiling", h_eval["rejection_reasons"])
        self.assertFalse(h_eval["eligible"])

    def test_should_recommend_best_option_per_market_category_and_rank_by_sharpe(self):
        snapshot = make_odds_snapshot()
        # Provide both HAD and TTG
        snapshot["matches"][0]["odds"]["had"] = {"h": 1.90, "d": 3.40, "a": 4.00}
        snapshot["matches"][0]["odds"]["ttg"] = {
            "s0": 10.0, "s1": 4.5, "s2": 3.4, "s3": 3.9,
            "s4": 5.5, "s5": 11.0, "s6": 25.0, "s7": 30.0,
        }
        prediction = make_prediction(provenance_status="verified", home_probability=0.65)

        report = betting.analyze_daily(
            snapshot, [prediction], now=NOW, probability_haircut=0.02, min_ev_low=0.05
        )

        # Should recommend best pick for each market category (both HAD and TTG)
        self.assertEqual(len(report["recommendations"]), 2)
        # Higher Sharpe ratio pick ranked first
        self.assertEqual(report["recommendations"][0]["market"], "had")
        self.assertEqual(report["recommendations"][0]["option"], "h")
        self.assertEqual(report["recommendations"][1]["market"], "ttg")

    def test_should_include_all_eligible_options_when_requested(self):
        snapshot = make_odds_snapshot()
        snapshot["matches"][0]["odds"]["had"] = {"h": 1.90, "d": 3.40, "a": 4.00}
        snapshot["matches"][0]["odds"]["ttg"] = {
            "s0": 10.0, "s1": 4.5, "s2": 3.4, "s3": 3.9,
            "s4": 5.5, "s5": 11.0, "s6": 25.0, "s7": 30.0,
        }
        prediction = make_prediction(provenance_status="verified", home_probability=0.65)

        report = betting.analyze_daily(
            snapshot, [prediction], now=NOW, probability_haircut=0.02, min_ev_low=0.05, all_eligible=True
        )

        self.assertGreaterEqual(len(report["recommendations"]), 2)
        markets = {r["market"] for r in report["recommendations"]}
        self.assertIn("had", markets)
        self.assertIn("ttg", markets)

    def test_should_recommend_ttg_and_crs_single_bets(self):
        snapshot = make_odds_snapshot()
        # Single allowed for TTG and CRS
        snapshot["matches"][0]["single_status"] = {"had": False, "hhad": False, "ttg": True, "crs": True}
        snapshot["matches"][0]["odds"]["ttg"] = {
            "s0": 20.0, "s1": 4.5, "s2": 3.4, "s3": 3.9,
            "s4": 5.5, "s5": 11.0, "s6": 25.0, "s7": 30.0,
        }
        crs_odds = {
            **{opt: 25.0 for opt in ["1-0", "2-0", "2-1", "3-0", "3-1", "3-2", "4-0", "4-1", "4-2", "5-0", "5-1", "5-2"]},
            **{opt: 25.0 for opt in ["0-0", "1-1", "2-2", "3-3"]},
            **{opt: 25.0 for opt in ["0-1", "0-2", "1-2", "0-3", "1-3", "2-3", "0-4", "1-4", "2-4", "0-5", "1-5", "2-5"]},
            **{"胜其他": 30.0, "平其他": 30.0, "负其他": 30.0},
        }
        crs_odds["0-0"] = 20.0
        snapshot["matches"][0]["odds"]["crs"] = crs_odds
        prediction = make_prediction(provenance_status="verified")

        report = betting.analyze_daily(
            snapshot, [prediction], now=NOW, probability_haircut=0.02, min_ev_low=0.05, bankroll=200.0, unit=2.0
        )

        recs = report["recommendations"]
        markets = {r["market"] for r in recs}
        self.assertIn("ttg", markets)
        self.assertIn("crs", markets)
        for r in recs:
            self.assertGreaterEqual(r["stake"], 2.0)
            self.assertEqual(r["stake"] % 2.0, 0.0)

    def test_should_build_and_prioritize_mixed_parlays_across_markets(self):
        bets = [
            {"bet_id": "m1:had:h", "match_id": "m1", "match_num": "周二001", "home_team": "TeamA", "market": "had", "option": "h", "probability": 0.6, "conservative_probability": 0.57, "odds": 2.0},
            {"bet_id": "m1:ttg:s2", "match_id": "m1", "match_num": "周二001", "home_team": "TeamA", "market": "ttg", "option": "s2", "probability": 0.5, "conservative_probability": 0.47, "odds": 2.2},
            {"bet_id": "m2:hhad:h", "match_id": "m2", "match_num": "周二002", "home_team": "TeamB", "market": "hhad", "option": "h", "goal_line": -1, "probability": 0.55, "conservative_probability": 0.52, "odds": 2.1},
            {"bet_id": "m2:crs:1-0", "match_id": "m2", "match_num": "周二002", "home_team": "TeamB", "market": "crs", "option": "1-0", "probability": 0.35, "conservative_probability": 0.32, "odds": 5.0},
        ]
        parlays = betting.build_multi_leg_parlays(bets, leg_count=2, min_ev_low=0.0)
        self.assertGreater(len(parlays), 0)
        # Verify cross-market mixed parlays are marked as is_mixed
        mixed = [p for p in parlays if p["is_mixed"]]
        self.assertGreater(len(mixed), 0)
        # Verify mixed parlays appear ahead of single-market parlays
        first = parlays[0]
        self.assertTrue(first["is_mixed"])
        self.assertIn("mix_label", first)
        self.assertIn("market_mix", first)
        # Verify cross-match independence
        for p in parlays:
            self.assertEqual(len(set(p["match_ids"])), 2)

    def test_should_render_categorized_markdown_for_had_ttg_and_crs(self):
        report = {
            "generated_at": "2026-08-25T08:00:00Z",
            "policy": {"probability_haircut": 0.03, "min_ev_low": 0.05, "max_divergence_ratio": 2.0, "max_single_odds": 70.0, "max_total_exposure": 0.5},
            "recommendations": [
                {"match_num": "周二001", "home_team": "TeamA", "away_team": "TeamB", "market": "had", "option": "h", "odds": 2.0, "probability": 0.6, "conservative_probability": 0.57, "ev_low": 0.14, "kelly_fraction": 0.05, "stake": 10.0},
                {"match_num": "周二002", "home_team": "TeamC", "away_team": "TeamD", "market": "ttg", "option": "s2", "odds": 3.4, "probability": 0.45, "conservative_probability": 0.42, "ev_low": 0.12, "kelly_fraction": 0.02, "stake": 4.0},
                {"match_num": "周二003", "home_team": "TeamE", "away_team": "TeamF", "market": "crs", "option": "1-0", "odds": 6.5, "probability": 0.25, "conservative_probability": 0.22, "ev_low": 0.15, "kelly_fraction": 0.01, "stake": 2.0},
                {"type": "two_leg_parlay", "is_mixed": True, "mix_label": "HAD+TTG", "leg_labels": ["周二001 TeamA(HAD-h)", "周二002 TeamC(TTG-s2)"], "odds": 6.8, "probability": 0.27, "conservative_probability": 0.24, "ev_low": 0.20, "kelly_fraction": 0.02, "stake": 4.0},
            ],
            "rejections": [],
            "bankroll": {"total": 200, "staked": 20, "cash_reserved": 180},
        }
        md = betting.render_markdown(report)
        self.assertIn("### 单关投注建议", md)
        self.assertIn("#### 胜平负 / 让球胜平负单关", md)
        self.assertIn("#### 总进球数单关 (TTG)", md)
        self.assertIn("#### 比分单关 (CRS)", md)
        self.assertIn("### 2 串 1 混合过关建议", md)
        self.assertIn("混合过关·HAD+TTG", md)


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
        history[4]["kickoff_utc"] = history[3]["kickoff_utc"]

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

        for model_name in ("football_elo_poisson", "simple_home_elo"):
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

import unittest
from datetime import datetime, timezone

from contracts import utc_iso, utc_now
from model_core import calculate_disciplinary_risk, create_prediction, ModelParameters
from generate_betting_recommendation import (
    analyze_daily,
    build_multi_leg_parlays,
    build_system_bets,
    evaluate_match,
    get_disciplinary_haircut,
    render_markdown,
    SYSTEM_BET_DEFINITIONS,
)


class DisciplinaryAndSystemBetsTests(unittest.TestCase):
    def test_calculate_disciplinary_risk_unobserved(self):
        result = calculate_disciplinary_risk()
        self.assertEqual(result["status"], "unobserved")
        self.assertEqual(result["home"]["disciplinary_haircut"], 0.0)
        self.assertEqual(result["away"]["disciplinary_haircut"], 0.0)
        self.assertEqual(result["referee"]["name"], "unknown")

    def test_calculate_disciplinary_risk_observed_strict_referee(self):
        result = calculate_disciplinary_risk(
            home_red_cards_per_match=0.20,
            home_yellow_cards_per_match=2.50,
            away_red_cards_per_match=0.05,
            away_yellow_cards_per_match=1.20,
            referee_cards_per_match=5.50,
            referee_name="Strict Mike",
        )
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["referee"]["name"], "Strict Mike")
        self.assertGreater(result["referee"]["strictness_factor"], 1.0)
        self.assertGreater(result["home"]["red_card_probability"], result["away"]["red_card_probability"])
        self.assertGreater(result["home"]["disciplinary_haircut"], 0.0)

    def test_prediction_disciplinary_data_injection(self):
        history = [
            {
                "match_id": "hist:001",
                "kickoff_utc": "2026-09-01T12:00:00Z",
                "home_team": {"team_id": "team:a", "name": "Team A"},
                "away_team": {"team_id": "team:b", "name": "Team B"},
                "home_score": 2,
                "away_score": 1,
                "status": "FINISHED",
                "competition_code": "PL",
                "context": {"team_type": "club", "competition_type": "league", "venue": "home", "score_basis": "regulation"},
            },
            {
                "match_id": "hist:002",
                "kickoff_utc": "2026-09-08T12:00:00Z",
                "home_team": {"team_id": "team:b", "name": "Team B"},
                "away_team": {"team_id": "team:a", "name": "Team A"},
                "home_score": 0,
                "away_score": 1,
                "status": "FINISHED",
                "competition_code": "PL",
                "context": {"team_type": "club", "competition_type": "league", "venue": "home", "score_basis": "regulation"},
            },
        ]
        match = {
            "match_id": "PL:team:a:team:b:2026-09-20",
            "competition_code": "PL",
            "kickoff_utc": "2026-09-20T12:00:00Z",
            "home_team": {"team_id": "team:a", "name": "Team A"},
            "away_team": {"team_id": "team:b", "name": "Team B"},
            "context": {"team_type": "club", "competition_type": "league", "venue": "home", "score_basis": "regulation"},
        }
        snapshot = {
            "provider": "file",
            "source_url": "test",
            "fetched_at": "2026-09-19T12:00:00Z",
            "provenance_status": "verified",
            "sample_pool": {"pool_id": "test", "team_type": "club", "competition_codes": ["PL"]},
        }
        pred = create_prediction(
            history_matches=history,
            match=match,
            data_snapshot=snapshot,
            parameters=ModelParameters(min_team_matches=1),
            disciplinary={
                "home_red_cards_per_match": 0.25,
                "home_yellow_cards_per_match": 3.0,
                "away_red_cards_per_match": 0.04,
                "away_yellow_cards_per_match": 1.0,
                "referee_cards_per_match": 5.0,
                "referee_name=":"John Strict",
            },
        )
        self.assertIn("disciplinary", pred["inputs"])
        self.assertEqual(pred["inputs"]["disciplinary"]["status"], "observed")
        self.assertGreater(pred["inputs"]["disciplinary"]["home"]["disciplinary_haircut"], 0.0)

    def test_evaluate_match_applies_disciplinary_haircut(self):
        match = {
            "match_id": "test:001",
            "match_num": "001",
            "competition": "PL",
            "home_team": {"name": "Team A"},
            "away_team": {"name": "Team B"},
            "market_status": {"had": "open", "hhad": "closed", "ttg": "closed", "crs": "closed"},
            "odds": {
                "had": {"h": 2.0, "d": 3.2, "a": 4.0},
            },
        }
        # Model predicts Team A high win prob
        pred = {
            "probabilities": {
                "had": {"H": 0.60, "D": 0.25, "A": 0.15},
                "score": {"1-0": 0.60, "0-0": 0.25, "0-1": 0.15},
                "ttg": {f"s{i}": (1.0 if i == 1 else 0.0) for i in range(8)},
            },
            "inputs": {
                "disciplinary": {
                    "status": "observed",
                    "home": {"disciplinary_haircut": 0.06},
                    "away": {"disciplinary_haircut": 0.01},
                }
            },
        }
        evals = evaluate_match(match, pred, probability_haircut=0.03, min_ev_low=0.05)
        h_eval = next(item for item in evals if item["option"] == "h")
        self.assertEqual(h_eval["probability_haircut"], 0.03)
        self.assertEqual(h_eval["disciplinary_haircut"], 0.06)
        self.assertAlmostEqual(h_eval["total_haircut"], 0.09)
        # conservative_probability = 0.60 - 0.09 = 0.51
        self.assertAlmostEqual(h_eval["conservative_probability"], 0.51)
        # EV_low = 0.51 * 2.0 - 1.0 = 0.02, which is < min_ev_low (0.05)
        # Base EV_low without disciplinary would be (0.60 - 0.03) * 2.0 - 1.0 = 0.14 >= 0.05
        # So disciplinary_risk_rejected should be triggered!
        self.assertIn("disciplinary_risk_rejected", h_eval["rejection_reasons"])
        self.assertIn("ev_below_threshold", h_eval["rejection_reasons"])
        self.assertFalse(h_eval["eligible"])

    def test_max_match_repetition_decentralized_pairing(self):
        bets = [
            {"bet_id": "b1", "match_id": "m1", "match_num": "001", "home_team": "T1", "market": "had", "option": "h", "odds": 2.0, "probability": 0.70, "conservative_probability": 0.65, "ev_low": 0.30},
            {"bet_id": "b2", "match_id": "m2", "match_num": "002", "home_team": "T2", "market": "had", "option": "h", "odds": 2.0, "probability": 0.65, "conservative_probability": 0.60, "ev_low": 0.20},
            {"bet_id": "b3", "match_id": "m3", "match_num": "003", "home_team": "T3", "market": "had", "option": "h", "odds": 2.0, "probability": 0.60, "conservative_probability": 0.55, "ev_low": 0.10},
            {"bet_id": "b4", "match_id": "m4", "match_num": "004", "home_team": "T4", "market": "had", "option": "h", "odds": 2.0, "probability": 0.58, "conservative_probability": 0.53, "ev_low": 0.06},
        ]
        # All pairs: (m1,m2), (m1,m3), (m1,m4), (m2,m3), (m2,m4), (m3,m4)
        all_parlays = build_multi_leg_parlays(bets, leg_count=2, min_ev_low=0.0)
        # Without repetition limit, top 3 all contain m1:
        top_3_m1_count = sum(1 for p in all_parlays[:3] if "m1" in p["match_ids"])
        self.assertEqual(top_3_m1_count, 3)

        # With max_match_repetition=1: m1 can only be picked ONCE
        decentralized = build_multi_leg_parlays(bets, leg_count=2, min_ev_low=0.0, max_match_repetition=1)
        m1_count = sum(1 for p in decentralized if "m1" in p["match_ids"])
        self.assertEqual(m1_count, 1)
        # Second parlay in decentralized must not contain m1 or m2!
        self.assertEqual(decentralized[0]["match_ids"], ["m1", "m2"])
        self.assertEqual(decentralized[1]["match_ids"], ["m3", "m4"])

    def test_build_system_bets_3_in_4_and_4_in_11(self):
        bets = [
            {"bet_id": "b1", "match_id": "m1", "match_num": "001", "home_team": "T1", "market": "had", "option": "h", "odds": 2.0, "probability": 0.70, "conservative_probability": 0.65, "ev_low": 0.30},
            {"bet_id": "b2", "match_id": "m2", "match_num": "002", "home_team": "T2", "market": "had", "option": "h", "odds": 2.0, "probability": 0.70, "conservative_probability": 0.65, "ev_low": 0.30},
            {"bet_id": "b3", "match_id": "m3", "match_num": "003", "home_team": "T3", "market": "had", "option": "h", "odds": 2.0, "probability": 0.70, "conservative_probability": 0.65, "ev_low": 0.30},
            {"bet_id": "b4", "match_id": "m4", "match_num": "004", "home_team": "T4", "market": "had", "option": "h", "odds": 2.0, "probability": 0.70, "conservative_probability": 0.65, "ev_low": 0.30},
        ]
        # 3 in 4
        sys_3_4 = build_system_bets(bets[:3], system_types=["3_in_4"], unit=2.0)
        self.assertEqual(len(sys_3_4), 1)
        item34 = sys_3_4[0]
        self.assertEqual(item34["system_name"], "3串4")
        self.assertEqual(item34["bet_count"], 4)  # 3 of 2-leg + 1 of 3-leg
        self.assertEqual(item34["cost"], 8.0)
        self.assertEqual(item34["tolerance_matches"], 1)
        self.assertIn("all_hit", item34["scenarios"])
        self.assertIn("miss_1", item34["scenarios"])
        # In 3-in-4 with each leg odds=2.0:
        # All hit: 3 * (2*2*2) + 1 * (2*2*2*2) = 3 * 8 + 1 * 16 = 40.0
        self.assertEqual(item34["scenarios"]["all_hit"]["payout"], 40.0)
        # Miss 1: exactly 1 2-leg parlay hits = 2 * 2 * 2 = 8.0
        self.assertEqual(item34["scenarios"]["miss_1"]["min_payout"], 8.0)

        # 4 in 11
        sys_4_11 = build_system_bets(bets, system_types=["4_in_11"], unit=2.0)
        self.assertEqual(len(sys_4_11), 1)
        item411 = sys_4_11[0]
        self.assertEqual(item411["system_name"], "4串11")
        self.assertEqual(item411["bet_count"], 11)  # 6 of 2-leg + 4 of 3-leg + 1 of 4-leg
        self.assertEqual(item411["cost"], 22.0)
        self.assertEqual(item411["tolerance_matches"], 2)
        self.assertIsNotNone(item411["scenarios"]["miss_2"])
        # Miss 2: exactly 1 of 2-leg hits = 2 * 2 * 2 = 8.0
        self.assertEqual(item411["scenarios"]["miss_2"]["min_payout"], 8.0)

    def test_render_markdown_with_system_bets(self):
        report = {
            "generated_at": "2026-09-30T12:00:00Z",
            "policy": {
                "probability_haircut": 0.03,
                "min_ev_low": 0.05,
                "max_match_repetition": 1,
                "include_system_bets": True,
            },
            "recommendations": [
                {
                    "type": "single",
                    "match_num": "001",
                    "home_team": "Team A",
                    "away_team": "Team B",
                    "market": "had",
                    "option": "h",
                    "odds": 2.0,
                    "probability": 0.65,
                    "conservative_probability": 0.60,
                    "ev_low": 0.20,
                    "kelly_fraction": 0.05,
                    "stake": 10.0,
                }
            ],
            "system_bets": [
                {
                    "system_name": "4串11",
                    "tolerance_matches": 2,
                    "leg_labels": ["001 T1(HAD-h)", "002 T2(HAD-h)", "003 T3(HAD-h)", "004 T4(HAD-h)"],
                    "bet_count": 11,
                    "cost": 22.0,
                    "ev_low": 0.25,
                    "scenarios": {
                        "all_hit": {"payout": 140.0, "roi": 6.4},
                        "miss_1": {"min_payout": 24.0},
                        "miss_2": {"min_payout": 8.0},
                    },
                }
            ],
            "rejections": [],
            "bankroll": {"total": 200, "staked": 10, "cash_reserved": 190},
        }
        md = render_markdown(report)
        self.assertIn("### 容错系统过关建议（System Bets / 多串过关）", md)
        self.assertIn("4串11", md)
        self.assertIn("容错 2 场", md)
        self.assertIn("11 注", md)
        self.assertIn("22 元", md)


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timedelta, timezone

from contracts import utc_iso, utc_now
from generate_betting_recommendation import (
    analyze_daily,
    evaluate_match,
    market_reasons,
    recommendation_reasons,
    render_markdown,
)
from scope_fixtures import target_match, verified_snapshot
from model_core import create_prediction
from test_scripts import make_odds_snapshot


class MarketScopeTests(unittest.TestCase):
    def test_missing_market_status_is_unknown(self):
        self.assertIn("market_sale_unknown", market_reasons({}, "had"))

    def test_closed_market_status_is_closed(self):
        self.assertIn("market_closed", market_reasons({"market_status": {"had": "closed"}}, "had"))

    def test_open_market_status_has_no_reasons(self):
        self.assertEqual(market_reasons({"market_status": {"had": "open"}}, "had"), [])

    def test_match_open_had_closed_does_not_evaluate_had(self):
        now = utc_now()
        odds_match = {
            "match_id": "sporttery:1001",
            "provider_match_id": "1001",
            "match_num": "001",
            "competition": "J1",
            "official_listing": {
                "status": "confirmed",
                "source_url": "https://example.invalid",
                "observed_at": utc_iso(now),
                "provider_match_id": "1001",
            },
            "market_status": {
                "had": "closed",
                "hhad": "open",
                "ttg": "open",
                "crs": "open",
            },
            "home_team": {"name": "Alpha"},
            "away_team": {"name": "Beta"},
            "odds": {
                "had": {"h": 2.0, "d": 3.0, "a": 3.5},
                "hhad": {"goal_line": -1, "h": 3.0, "d": 3.2, "a": 2.1},
                "ttg": {f"s{i}": 4.0 for i in range(8)},
                "crs": {
                    **{opt: 15.0 for opt in ["1-0", "2-0", "2-1", "3-0", "3-1", "3-2", "4-0", "4-1", "4-2", "5-0", "5-1", "5-2"]},
                    **{opt: 15.0 for opt in ["0-0", "1-1", "2-2", "3-3"]},
                    **{opt: 15.0 for opt in ["0-1", "0-2", "1-2", "0-3", "1-3", "2-3", "0-4", "1-4", "2-4", "0-5", "1-5", "2-5"]},
                    **{"胜其他": 20.0, "平其他": 20.0, "负其他": 20.0},
                },
            },
        }
        pred = {
            "probabilities": {
                "had": {"H": 0.5, "D": 0.3, "A": 0.2},
                "score": {"1-0": 0.5, "0-0": 0.3, "0-1": 0.2},
                "ttg": {f"s{i}": (1.0 if i == 1 else 0.0) for i in range(8)},
            }
        }
        evals = evaluate_match(odds_match, pred)
        self.assertFalse(any(item["market"] == "had" for item in evals))
        self.assertTrue(any(item["market"] == "hhad" for item in evals))

    def test_recommendation_reasons_detects_unknown_context(self):
        pred = {
            "quality": {"status": "sufficient", "missing_data": []},
            "match": {
                "context": {
                    "team_type": "club",
                    "competition_type": "league",
                    "venue": "unknown",
                    "score_basis": "regulation",
                }
            },
            "data_snapshot": {
                "provenance_status": "verified",
                "sample_pool": {"pool_id": "test", "team_type": "club", "competition_codes": ["J1"]},
            },
        }
        reasons = recommendation_reasons(pred)
        self.assertIn("venue_unknown", reasons)

    def test_markdown_title_is_sporttery_football(self):
        report = {
            "generated_at": "2026-09-27T12:00:00Z",
            "policy": {"probability_haircut": 0.03, "min_ev_low": 0.05},
            "recommendations": [],
            "rejections": [],
            "bankroll": {"total": 200, "staked": 0, "cash_reserved": 200},
        }
        md = render_markdown(report)
        self.assertIn("# 竞彩足球投注分析（2026-09-27）", md)
        self.assertNotIn("五大联赛", md)


if __name__ == "__main__":
    unittest.main()

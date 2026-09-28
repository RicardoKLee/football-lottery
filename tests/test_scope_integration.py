import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import fetch_match_data
import generate_betting_recommendation as betting
import generate_betting_recommendation_strict as strict_betting
from contracts import utc_iso, validate_model_prediction, validate_odds_snapshot
from scope_fixtures import regular_history, verified_snapshot


class ScopeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_j1_history_file(self, path, provenance_status="verified"):
        history_matches = regular_history(team_type="club", venue="home")
        snapshot = verified_snapshot()
        snapshot["provenance_status"] = provenance_status
        payload = {
            "matches": history_matches,
            "provider": snapshot["provider"],
            "source_url": snapshot["source_url"],
            "fetched_at": snapshot["fetched_at"],
            "provenance_status": provenance_status,
            "sample_pool": snapshot["sample_pool"],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    def _create_j1_odds_file(self, path, official_status="confirmed", had_status="open"):
        fetched_at = "2026-09-13T11:50:00Z"
        payload = {
            "kind": "odds_snapshot",
            "provider": "china-sporttery",
            "source_url": "https://example.invalid/sporttery",
            "source_mode": "file",
            "fetched_at": fetched_at,
            "requested_date": "2026-09-13",
            "matches": [
                {
                    "match_id": "sporttery:20260913001",
                    "provider_match_id": "20260913001",
                    "official_listing": {
                        "status": official_status,
                        "source_url": "https://example.invalid/sporttery/match/20260913001",
                        "observed_at": fetched_at,
                        "provider_match_id": "20260913001",
                    },
                    "market_status": {
                        "had": had_status,
                        "hhad": "closed",
                        "ttg": "closed",
                        "crs": "closed",
                    },
                    "match_num": "周日001",
                    "competition": "日职联",
                    "match_date": "2026-09-13",
                    "kickoff_utc": "2026-09-13T12:00:00Z",
                    "cutoff_utc": "2026-09-13T11:55:00Z",
                    "cutoff_is_estimated": True,
                    "odds_observed_at": fetched_at,
                    "is_available": (official_status == "confirmed" and had_status == "open"),
                    "availability_reasons": [] if (official_status == "confirmed" and had_status == "open") else ["market_closed"],
                    "sale_status": "open" if official_status == "confirmed" else "closed",
                    "home_team": {"name": "Alpha", "aliases": ["Alpha FC"]},
                    "away_team": {"name": "Beta", "aliases": ["Beta FC"]},
                    "odds": {
                        "had": {"h": 2.10, "d": 3.20, "a": 3.40},
                        "hhad": {"goal_line": -1, "h": 4.10, "d": 3.50, "a": 1.70},
                        "ttg": {f"s{i}": 4.0 for i in range(8)},
                        "crs": {
                            **{opt: 15.0 for opt in ["1-0", "2-0", "2-1", "3-0", "3-1", "3-2", "4-0", "4-1", "4-2", "5-0", "5-1", "5-2"]},
                            **{opt: 15.0 for opt in ["0-0", "1-1", "2-2", "3-3"]},
                            **{opt: 15.0 for opt in ["0-1", "0-2", "1-2", "0-3", "1-3", "2-3", "0-4", "1-4", "2-4", "0-5", "1-5", "2-5"]},
                            **{"胜其他": 20.0, "平其他": 20.0, "负其他": 20.0},
                        },
                    },
                }
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    def test_end_to_end_cli_pipeline_with_non_top_five_competition(self):
        history_path = os.path.join(self.dir_path, "j1_history.json")
        self._create_j1_history_file(history_path, provenance_status="verified")

        pred_path = os.path.join(self.dir_path, "prediction.json")
        fetch_args = fetch_match_data.parse_args([
            "--competition", "J1",
            "--competition-name", "日职联",
            "--team-type", "club",
            "--competition-type", "league",
            "--venue", "neutral",
            "--history-file", history_path,
            "--home-team", "fixture:Alpha",
            "--away-team", "fixture:Beta",
            "--kickoff", "2026-09-13T12:00:00Z",
            "--lottery-match-id", "sporttery:20260913001",
            "--season", "2026",
            "--output", pred_path,
        ])
        pred = fetch_match_data.run(fetch_args)
        fetch_match_data.write_json(pred_path, pred)
        self.assertTrue(os.path.exists(pred_path))
        self.assertEqual(pred["match"]["competition_code"], "J1")
        self.assertEqual(pred["match"]["competition_name"], "日职联")
        self.assertEqual(pred["match"]["context"]["venue"], "neutral")
        self.assertEqual(pred["match"]["context"]["score_basis"], "regulation")
        self.assertEqual(pred["quality"]["status"], "sufficient")
        validate_model_prediction(pred)

        odds_path = os.path.join(self.dir_path, "j1_odds.json")
        self._create_j1_odds_file(odds_path, official_status="confirmed", had_status="open")

        now = datetime(2026, 9, 13, 11, 52, tzinfo=timezone.utc)
        betting_args = strict_betting.parse_args([
            "--predictions", pred_path,
            "--lottery-file", odds_path,
            "--date", "2026-09-13",
            "--output-dir", self.dir_path,
        ])
        report = strict_betting.run(betting_args, now=now)

        self.assertEqual(report["kind"], "betting_report")
        self.assertEqual(report["requested_date"], "2026-09-13")

        # Only open market (HAD) should be evaluated; closed markets (HHAD, TTG, CRS) skipped
        evaluated_markets = {item["market"] for item in report["evaluations"]}
        self.assertEqual(evaluated_markets, {"had"})
        self.assertEqual(len(report["recommendations"]), 1)
        self.assertGreater(report["bankroll"]["staked"], 0.0)

        # Markdown output must render with proper title and content
        md = betting.render_markdown(report, "2026-09-13")
        self.assertIn("竞彩足球投注分析", md)

    def test_integration_rejection_when_unconfirmed_or_closed(self):
        history_path = os.path.join(self.dir_path, "j1_history.json")
        self._create_j1_history_file(history_path, provenance_status="verified")

        pred_path = os.path.join(self.dir_path, "prediction.json")
        fetch_args = fetch_match_data.parse_args([
            "--competition", "J1",
            "--competition-name", "日职联",
            "--venue", "neutral",
            "--history-file", history_path,
            "--home-team", "fixture:Alpha",
            "--away-team", "fixture:Beta",
            "--kickoff", "2026-09-13T12:00:00Z",
            "--lottery-match-id", "sporttery:20260913001",
            "--season", "2026",
            "--output", pred_path,
        ])
        pred = fetch_match_data.run(fetch_args)
        fetch_match_data.write_json(pred_path, pred)

        # Case A: official_listing status is unknown
        odds_path_unknown = os.path.join(self.dir_path, "odds_unknown.json")
        self._create_j1_odds_file(odds_path_unknown, official_status="unknown", had_status="open")

        now = datetime(2026, 9, 13, 11, 52, tzinfo=timezone.utc)
        betting_args_unknown = strict_betting.parse_args([
            "--predictions", pred_path,
            "--lottery-file", odds_path_unknown,
            "--date", "2026-09-13",
        ])
        report_unknown = strict_betting.run(betting_args_unknown, now=now)

        # Plan-mandated exact assertion block for integration rejection
        self.assertEqual(report_unknown["recommendations"], [])
        self.assertTrue(report_unknown["rejections"])
        self.assertEqual(report_unknown["bankroll"]["staked"], 0.0)
        self.assertTrue(any(r.get("reason") == "match_not_officially_listed" for r in report_unknown["rejections"]))

        # Case B: all markets closed
        odds_path_closed = os.path.join(self.dir_path, "odds_closed.json")
        self._create_j1_odds_file(odds_path_closed, official_status="confirmed", had_status="closed")

        betting_args_closed = strict_betting.parse_args([
            "--predictions", pred_path,
            "--lottery-file", odds_path_closed,
            "--date", "2026-09-13",
        ])
        report_closed = strict_betting.run(betting_args_closed, now=now)
        self.assertEqual(report_closed["recommendations"], [])
        self.assertTrue(report_closed["rejections"])
        self.assertEqual(report_closed["bankroll"]["staked"], 0.0)
        self.assertTrue(any(r.get("reason") in ("market_closed", "match_not_available") for r in report_closed["rejections"]))

    def test_cli_main_generates_json_and_markdown_files(self):
        history_path = os.path.join(self.dir_path, "j1_history.json")
        self._create_j1_history_file(history_path, provenance_status="verified")
        pred_path = os.path.join(self.dir_path, "prediction.json")

        exit_code_fetch = fetch_match_data.main([
            "--competition", "J1",
            "--competition-name", "日职联",
            "--history-file", history_path,
            "--home-team", "fixture:Alpha",
            "--away-team", "fixture:Beta",
            "--kickoff", "2026-09-13T12:00:00Z",
            "--lottery-match-id", "sporttery:20260913001",
            "--season", "2026",
            "--output", pred_path,
        ])
        self.assertEqual(exit_code_fetch, 0)
        self.assertTrue(os.path.exists(pred_path))

        odds_path = os.path.join(self.dir_path, "j1_odds.json")
        self._create_j1_odds_file(odds_path, official_status="confirmed", had_status="closed")

        json_out = os.path.join(self.dir_path, "output_betting.json")
        md_out = os.path.join(self.dir_path, "output_betting.md")

        exit_code_betting = strict_betting.main([
            "--predictions", pred_path,
            "--lottery-file", odds_path,
            "--date", "2026-09-13",
            "--json-output", json_out,
            "--markdown-output", md_out,
        ])
        self.assertEqual(exit_code_betting, 0)
        self.assertTrue(os.path.exists(json_out))
        self.assertTrue(os.path.exists(md_out))

        with open(json_out, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["kind"], "betting_report")
        self.assertEqual(data["requested_date"], "2026-09-13")

        with open(md_out, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("竞彩足球投注分析", content)


if __name__ == "__main__":
    unittest.main()

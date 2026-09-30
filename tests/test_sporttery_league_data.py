import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from contracts import validate_context
import fetch_sporttery_league_data as league_fetcher


class TestSportteryLeagueData(unittest.TestCase):
    def test_parse_match_results_regulation_scores(self):
        raw_api_value = {
            "matchList": [
                {
                    "matchDate": "2026-05-10",
                    "subMatchList": [
                        {
                            "homeAbbCnName": "沃夫斯堡",
                            "awayAbbCnName": "拜仁",
                            "uniformHomeTeamId": 323,
                            "uniformAwayTeamId": 197,
                            "uniformMatchId": 2390963,
                            "gmMatchId": 2039617,
                            "matchDate": "2026-05-10",
                            "matchTime": "00:30",
                            "sectionsNo1": "0:0",
                            "sectionsNo999": "0:1",
                            "wbsjMatchSc": "Played",
                            "wbsjMatchScDesc": "已完成",
                            "gameweek": "33",
                        },
                        {
                            "homeAbbCnName": "汉堡",
                            "awayAbbCnName": "弗赖堡",
                            "uniformHomeTeamId": 258,
                            "uniformAwayTeamId": 196,
                            "uniformMatchId": 2390984,
                            "gmMatchId": 2039637,
                            "matchDate": "2026-05-10",
                            "matchTime": "21:30",
                            "sectionsNo1": "1:1",
                            "sectionsNo999": "3:2",
                            "wbsjMatchSc": "Played",
                            "wbsjMatchScDesc": "已完成",
                            "gameweek": "33",
                        },
                        # Not played match should be skipped
                        {
                            "homeAbbCnName": "未来主队",
                            "awayAbbCnName": "未来客队",
                            "uniformHomeTeamId": 999,
                            "uniformAwayTeamId": 888,
                            "uniformMatchId": 1111111,
                            "matchDate": "2026-05-20",
                            "matchTime": "21:30",
                            "sectionsNo999": "",
                            "wbsjMatchSc": "Fixture",
                            "wbsjMatchScDesc": "未开始",
                        },
                    ],
                }
            ]
        }

        snapshot = league_fetcher.parse_match_results(
            raw_api_value,
            league_id=1803,
            season_id=13419,
            competition_code="BL1",
            competition_name="德甲",
            team_type="club",
        )

        self.assertEqual(snapshot["provider"], "china-sporttery")
        self.assertEqual(snapshot["provenance_status"], "verified")
        self.assertEqual(snapshot["sample_pool"]["competition_codes"], ["BL1"])
        self.assertEqual(snapshot["count"], 2)
        self.assertEqual(snapshot["skipped_unplayed_or_invalid"], 1)

        m1 = snapshot["matches"][0]
        self.assertEqual(m1["home_team"]["name"], "沃夫斯堡")
        self.assertEqual(m1["away_team"]["name"], "拜仁")
        self.assertEqual(m1["home_score"], 0)
        self.assertEqual(m1["away_score"], 1)
        self.assertEqual(m1["context"]["score_basis"], "regulation")
        self.assertEqual(m1["context"]["venue"], "home")
        validate_context(m1["context"])

        m2 = snapshot["matches"][1]
        self.assertEqual(m2["home_score"], 3)
        self.assertEqual(m2["away_score"], 2)

    def test_parse_args(self):
        args = league_fetcher.parse_args(["--list-leagues"])
        self.assertTrue(args.list_leagues)

        args2 = league_fetcher.parse_args(["--league-id", "1803", "--season-id", "13419", "--standings"])
        self.assertEqual(args2.league_id, "1803")
        self.assertEqual(args2.season_id, "13419")
        self.assertTrue(args2.standings)

    @patch("fetch_sporttery_league_data.fetch_api_json")
    def test_fetch_league_catalog(self, mock_fetch):
        mock_fetch.return_value = {"hot": [{"uniformLeagueId": 1803, "leagueAbbCnName": "德甲"}]}
        catalog = league_fetcher.fetch_league_catalog()
        self.assertIn("hot", catalog)
        self.assertEqual(catalog["hot"][0]["leagueAbbCnName"], "德甲")


if __name__ == "__main__":
    unittest.main()

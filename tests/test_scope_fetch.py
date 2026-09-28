import json
import os
import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from contracts import ContractError
from fetch_match_data import (
    FootballDataClient,
    ProviderError,
    fetch_live_history,
    load_history_file,
    parse_args,
    run,
)


class ScopeCliTests(unittest.TestCase):
    def test_any_competition_is_parseable(self):
        args = parse_args(["--competition", "J1", "--list-teams"])
        self.assertEqual(args.competition, "J1")

    def test_season_flag_requests_explicit_season(self):
        mock_client = MagicMock()
        mock_client.competition_matches.return_value = ({"matches": []}, "https://api.football-data.org/v4/competitions/J1/matches?season=2025")
        fetch_live_history(mock_client, "J1", "2026-09-13T12:00:00Z", seasons=1, season=2025)
        mock_client.competition_matches.assert_called_once_with("J1", 2025)

    def test_unverified_competition_requires_explicit_season(self):
        mock_client = MagicMock()
        with self.assertRaises(ContractError) as ctx:
            fetch_live_history(mock_client, "UNKNOWN-CUP", "2026-09-13T12:00:00Z", seasons=1, season=None)
        self.assertEqual(str(ctx.exception), "explicit_season_required")

    def test_load_history_file_does_not_assert_provenance_verified(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json") as f:
            json.dump([{"match_id": "fixture:1", "status": "FINISHED"}], f)
            temp_path = f.name
        try:
            matches, snapshot = load_history_file(temp_path)
            self.assertEqual(snapshot["provenance_status"], "unverified")
        finally:
            os.unlink(temp_path)

    def test_http_error_raises_provider_error(self):
        client = FootballDataClient("test-token")
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                "https://api.football-data.org/v4/test", 403, "Forbidden", {}, None
            )
            with self.assertRaises(ProviderError):
                client.get_json("/test")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from contracts import ContractError, load_json, utc_iso, utc_now, write_json
from model_core import (
    SUPPORTED_COMPETITIONS,
    ModelDataError,
    ModelParameters,
    TeamResolutionError,
    collect_teams,
    create_prediction,
    resolve_team,
)

FOOTBALL_DATA_API_BASE = "https://api.football-data.org/v4"
FOOTBALL_DATA_TOKEN_ENV = "FOOTBALL_DATA_API_TOKEN"


class ProviderError(RuntimeError):
    pass


class FootballDataClient:
    def __init__(self, token, timeout=20):
        if not token:
            raise ProviderError(f"Set {FOOTBALL_DATA_TOKEN_ENV} before using the live provider")
        self.token = token
        self.timeout = timeout

    def get_json(self, path, params=None):
        query = urllib.parse.urlencode(params or {})
        url = f"{FOOTBALL_DATA_API_BASE}{path}"
        if query:
            url = f"{url}?{query}"
        request = urllib.request.Request(
            url,
            headers={
                "X-Auth-Token": self.token,
                "User-Agent": "football-lottery/2.0",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8")), url
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raise ProviderError(f"football-data.org request failed for {url}: {exc}") from exc

    def competition_matches(self, competition_code, season):
        return self.get_json(
            f"/competitions/{competition_code}/matches",
            {"season": str(season), "status": "FINISHED"},
        )

    def competition_teams(self, competition_code, season):
        return self.get_json(
            f"/competitions/{competition_code}/teams", {"season": str(season)}
        )


def season_start_year(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.year if value.month >= 7 else value.year - 1


def load_aliases(path):
    if not path:
        return {}
    payload = load_json(path)
    aliases = payload.get("aliases", payload) if isinstance(payload, dict) else None
    if not isinstance(aliases, dict):
        raise ContractError("Alias file must contain an object mapping aliases to team IDs")
    return {str(alias): str(team_id) for alias, team_id in aliases.items()}


def load_history_file(path):
    payload = load_json(path)
    if isinstance(payload, list):
        matches = payload
        fetched_at = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
        source_url = os.path.abspath(path)
    elif isinstance(payload, dict) and isinstance(payload.get("matches"), list):
        matches = payload["matches"]
        fetched_at = payload.get("fetched_at") or datetime.fromtimestamp(
            os.path.getmtime(path), tz=timezone.utc
        )
        source_url = payload.get("source_url") or os.path.abspath(path)
    else:
        raise ContractError("History file must be an array or an object containing matches")
    return matches, {
        "provider": "file",
        "source_url": str(source_url),
        "fetched_at": utc_iso(fetched_at),
    }


def fetch_live_history(client, competition_code, kickoff, seasons):
    start = season_start_year(kickoff)
    all_matches = []
    source_urls = []
    for season in range(start - seasons + 1, start + 1):
        payload, source_url = client.competition_matches(competition_code, season)
        matches = payload.get("matches")
        if not isinstance(matches, list):
            raise ProviderError(f"Provider response for season {season} has no matches array")
        all_matches.extend(matches)
        source_urls.append(source_url)
    return all_matches, {
        "provider": "football-data.org",
        "source_url": ",".join(source_urls),
        "fetched_at": utc_iso(utc_now()),
    }


def list_live_teams(client, competition_code, season):
    payload, source_url = client.competition_teams(competition_code, season)
    teams = []
    for team in payload.get("teams", []):
        team_id = team.get("id")
        name = team.get("name")
        if team_id is None or not name:
            continue
        aliases = [value for value in (team.get("shortName"), team.get("tla")) if value]
        teams.append({"team_id": str(team_id), "name": str(name), "aliases": aliases})
    return {
        "schema_version": "2.0",
        "kind": "club_registry",
        "competition_code": competition_code,
        "season": str(season),
        "provider": "football-data.org",
        "source_url": source_url,
        "fetched_at": utc_iso(utc_now()),
        "teams": sorted(teams, key=lambda team: team["name"]),
    }


def merge_team_registry(history_teams, registry_teams):
    merged = {
        str(team_id): {
            "team_id": str(team["team_id"]),
            "name": str(team["name"]),
            "aliases": list(team.get("aliases") or []),
        }
        for team_id, team in history_teams.items()
    }
    for team in registry_teams:
        team_id = str(team.get("team_id", ""))
        name = team.get("name")
        if not team_id or not name:
            continue
        existing = merged.setdefault(
            team_id, {"team_id": team_id, "name": str(name), "aliases": []}
        )
        for alias in [str(name), *(team.get("aliases") or [])]:
            if alias and alias not in existing["aliases"]:
                existing["aliases"].append(alias)
    return merged


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Build a five-league club prediction from football-data.org history."
    )
    parser.add_argument("--competition", required=True, choices=sorted(SUPPORTED_COMPETITIONS))
    parser.add_argument("--history-file", help="Explicit football-data.org or normalized history JSON")
    parser.add_argument("--aliases-file", help="JSON map from exact aliases to provider team IDs")
    parser.add_argument("--list-teams", action="store_true", help="List current provider team IDs")
    parser.add_argument("--home-team", help="Provider team ID or exact provider name/alias")
    parser.add_argument("--away-team", help="Provider team ID or exact provider name/alias")
    parser.add_argument("--home-alias", action="append", default=[], help="Additional display alias")
    parser.add_argument("--away-alias", action="append", default=[], help="Additional display alias")
    parser.add_argument("--match-id", help="Stable upcoming match ID")
    parser.add_argument("--lottery-match-id", help="Matching normalized Sporttery match ID")
    parser.add_argument("--kickoff", help="Upcoming kickoff ISO datetime")
    parser.add_argument("--season", type=int, help="Season start year; inferred from kickoff by default")
    parser.add_argument("--history-seasons", type=int, default=2, choices=range(1, 6))
    parser.add_argument("--min-team-matches", type=int, default=5)
    parser.add_argument("--home-advantage-elo", type=float, default=60.0)
    parser.add_argument("--form-window", type=int, default=10)
    parser.add_argument("--form-decay", type=float, default=0.85)
    parser.add_argument("--output", help="Write prediction JSON to this path")
    return parser.parse_args(argv)


def run(args):
    if args.history_seasons < 1:
        raise ContractError("history-seasons must be positive")
    token = os.environ.get(FOOTBALL_DATA_TOKEN_ENV)
    client = FootballDataClient(token) if not args.history_file else None

    reference_time = args.kickoff or utc_now()
    season = args.season or season_start_year(reference_time)
    if args.list_teams:
        if client is None:
            history, snapshot = load_history_file(args.history_file)
            return {
                "schema_version": "2.0",
                "kind": "club_registry",
                "competition_code": args.competition,
                "season": str(season),
                **snapshot,
                "teams": sorted(collect_teams(history).values(), key=lambda team: team["name"]),
            }
        return list_live_teams(client, args.competition, season)

    if not args.home_team or not args.away_team or not args.kickoff:
        raise ContractError("--home-team, --away-team and --kickoff are required for prediction")
    if args.history_file:
        history, snapshot = load_history_file(args.history_file)
    else:
        history, snapshot = fetch_live_history(
            client, args.competition, args.kickoff, args.history_seasons
        )

    teams = collect_teams(history)
    if client is not None:
        current_registry = list_live_teams(client, args.competition, season)
        teams = merge_team_registry(teams, current_registry["teams"])
    aliases = load_aliases(args.aliases_file)
    home_team = resolve_team(args.home_team, teams, aliases=aliases)
    away_team = resolve_team(args.away_team, teams, aliases=aliases)
    home_team = {
        **home_team,
        "aliases": list(dict.fromkeys([*home_team.get("aliases", []), *args.home_alias])),
    }
    away_team = {
        **away_team,
        "aliases": list(dict.fromkeys([*away_team.get("aliases", []), *args.away_alias])),
    }
    match_id = args.match_id or (
        f"football-data:{args.competition}:{home_team['team_id']}:{away_team['team_id']}:"
        f"{str(args.kickoff)[:10]}"
    )
    prediction = create_prediction(
        history_matches=history,
        match={
            "match_id": match_id,
            "lottery_match_id": args.lottery_match_id,
            "competition_code": args.competition,
            "competition_name": SUPPORTED_COMPETITIONS[args.competition],
            "season": str(season),
            "kickoff_utc": args.kickoff,
            "home_team": home_team,
            "away_team": away_team,
        },
        data_snapshot=snapshot,
        parameters=ModelParameters(
            home_advantage_elo=args.home_advantage_elo,
            form_window=args.form_window,
            form_decay=args.form_decay,
            min_team_matches=args.min_team_matches,
        ),
    )
    return prediction


def main(argv=None):
    args = parse_args(argv)
    try:
        result = run(args)
        if args.output:
            write_json(args.output, result)
            print(json.dumps({"status": "success", "output": args.output}, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ContractError, ModelDataError, TeamResolutionError, ProviderError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

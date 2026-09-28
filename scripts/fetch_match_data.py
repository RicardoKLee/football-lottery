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
    COMPETITION_NAMES,
    ModelDataError,
    ModelParameters,
    TeamResolutionError,
    collect_teams,
    create_prediction,
    resolve_team,
)

FOOTBALL_DATA_API_BASE = "https://api.football-data.org/v4"
FOOTBALL_DATA_TOKEN_ENV = "FOOTBALL_DATA_API_TOKEN"
VERIFIED_JULY_SEASON_COMPETITIONS = set()


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
        source_url = os.path.abspath(path)
        snapshot = {
            "provider": "file",
            "source_url": str(source_url),
            "fetched_at": utc_iso(datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)),
            "provenance_status": "unverified",
            "sample_pool": {
                "pool_id": f"file:{os.path.basename(path)}",
                "team_type": "club",
                "competition_codes": list(dict.fromkeys(
                    str(m.get("competition_code")) for m in matches if isinstance(m, dict) and m.get("competition_code")
                )) or ["unknown"],
            },
        }
    elif isinstance(payload, dict) and isinstance(payload.get("matches"), list):
        matches = payload["matches"]
        source_url = payload.get("source_url") or os.path.abspath(path)
        fetched_at = payload.get("fetched_at") or utc_iso(
            datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
        )
        sample_pool = payload.get("sample_pool") or {
            "pool_id": f"file:{os.path.basename(path)}",
            "team_type": payload.get("context", {}).get("team_type", "club") if isinstance(payload.get("context"), dict) else "club",
            "competition_codes": list(dict.fromkeys(
                str(m.get("competition_code")) for m in matches if isinstance(m, dict) and m.get("competition_code")
            )) or ["unknown"],
        }
        snapshot = {
            "provider": str(payload.get("provider", "file")),
            "source_url": str(source_url),
            "fetched_at": utc_iso(fetched_at),
            "provenance_status": str(payload.get("provenance_status", "unverified")),
            "sample_pool": sample_pool,
        }
    else:
        raise ContractError("History file must be an array or an object containing matches")
    return matches, snapshot


def fetch_live_history(client, competition_code, kickoff, seasons, season=None):
    if season is not None:
        start = season
    elif competition_code in VERIFIED_JULY_SEASON_COMPETITIONS:
        start = season_start_year(kickoff)
    else:
        raise ContractError("explicit_season_required")
    all_matches = []
    source_urls = []
    for s in range(start - seasons + 1, start + 1):
        payload, source_url = client.competition_matches(competition_code, s)
        matches = payload.get("matches")
        if not isinstance(matches, list):
            raise ProviderError(f"Provider response for season {s} has no matches array")
        all_matches.extend(matches)
        source_urls.append(source_url)
    return all_matches, {
        "provider": "football-data.org",
        "source_url": ",".join(source_urls),
        "fetched_at": utc_iso(utc_now()),
        "provenance_status": "unverified",
        "sample_pool": {
            "pool_id": f"football-data.org:{competition_code}",
            "team_type": "club",
            "competition_codes": [competition_code],
        },
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
        description="Build a football prediction from history data."
    )
    parser.add_argument("--competition", required=True, help="Competition code (e.g. PL, PD, J1)")
    parser.add_argument("--competition-name", help="Display name for the competition")
    parser.add_argument("--team-type", choices=("club", "national", "unknown"), default="club")
    parser.add_argument("--competition-type", choices=("league", "cup", "other", "unknown"), default="league")
    parser.add_argument("--venue", choices=("home", "neutral", "unknown"), default="home")
    parser.add_argument("--context-file", help="Path to JSON file with match context object")
    parser.add_argument("--history-file", help="Explicit history JSON file")
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
    if not args.competition or not args.competition.strip():
        raise ContractError("competition is required and cannot be blank")
    if args.history_seasons < 1:
        raise ContractError("history-seasons must be positive")
    token = os.environ.get(FOOTBALL_DATA_TOKEN_ENV)
    client = FootballDataClient(token) if not args.history_file else None

    if args.context_file:
        context = load_json(args.context_file)
    else:
        context = {
            "team_type": args.team_type,
            "competition_type": args.competition_type,
            "venue": args.venue,
            "score_basis": "regulation",
        }

    reference_time = args.kickoff or utc_now()
    if args.season is not None:
        season = args.season
    elif args.competition in VERIFIED_JULY_SEASON_COMPETITIONS:
        season = season_start_year(reference_time)
    else:
        season = args.season

    if args.list_teams:
        if client is None:
            history, snapshot = load_history_file(args.history_file)
            return {
                "kind": "club_registry",
                "competition_code": args.competition,
                "season": str(season if season is not None else "unknown"),
                **snapshot,
                "teams": sorted(collect_teams(history).values(), key=lambda team: team["name"]),
            }
        if season is None:
            raise ContractError("explicit_season_required")
        return list_live_teams(client, args.competition, season)

    if not args.home_team or not args.away_team or not args.kickoff:
        raise ContractError("--home-team, --away-team and --kickoff are required for prediction")
    if args.history_file:
        history, snapshot = load_history_file(args.history_file)
    else:
        history, snapshot = fetch_live_history(
            client, args.competition, args.kickoff, args.history_seasons, season=season
        )

    teams = collect_teams(history)
    if client is not None:
        if season is None:
            raise ContractError("explicit_season_required")
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
    provider_prefix = "file" if args.history_file else "football-data.org"
    match_id = args.match_id or (
        f"{provider_prefix}:{args.competition}:{home_team['team_id']}:{away_team['team_id']}:"
        f"{str(args.kickoff)[:10]}"
    )
    prediction = create_prediction(
        history_matches=history,
        match={
            "match_id": match_id,
            "lottery_match_id": args.lottery_match_id,
            "competition_code": args.competition,
            "competition_name": args.competition_name or COMPETITION_NAMES.get(args.competition, args.competition),
            "season": str(season if season is not None else "unknown"),
            "kickoff_utc": args.kickoff,
            "context": context,
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

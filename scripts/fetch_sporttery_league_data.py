#!/usr/bin/env python3
"""Fetch official football league history, fixtures, and standings from www.sporttery.cn."""

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from contracts import ContractError, parse_datetime, utc_iso, utc_now, write_json
from fetch_lottery_data import BUSINESS_TIMEZONE, _get_physical_source_ip

SPORTTERY_WEBAPI_BASE = "https://webapi.sporttery.cn"
LEAGUE_LIST_URL = f"{SPORTTERY_WEBAPI_BASE}/gateway/uniform/football/league/getLeagueListV1.qry"
MATCH_RESULT_URL = f"{SPORTTERY_WEBAPI_BASE}/gateway/uniform/football/league/getMatchResultV1.qry"
TABLES_URL = f"{SPORTTERY_WEBAPI_BASE}/gateway/uniform/football/league/getTablesV2.qry"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class SportteryApiError(RuntimeError):
    pass


def fetch_api_json(url, timeout=15):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": "https://www.sporttery.cn/",
            "Accept": "application/json, text/plain, */*",
        },
    )

    def _do_fetch(source_ip=None):
        if source_ip:
            orig_create_connection = socket.create_connection

            def custom_create_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
                return orig_create_connection(address, timeout=timeout, source_address=(source_ip, 0))

            socket.create_connection = custom_create_connection
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            finally:
                socket.create_connection = orig_create_connection
        else:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))

    try:
        data = _do_fetch()
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, socket.error):
        source_ip = _get_physical_source_ip()
        if source_ip:
            try:
                data = _do_fetch(source_ip=source_ip)
            except Exception as retry_exc:
                raise SportteryApiError(f"Sporttery API request failed: {retry_exc}") from retry_exc
        else:
            raise SportteryApiError(f"Sporttery API request failed for {url}")

    if not isinstance(data, dict):
        raise SportteryApiError(f"Unexpected response format from {url}")
    if data.get("errorCode") not in ("0", 0):
        error_msg = data.get("errorMessage") or data.get("errorMsg") or f"errorCode={data.get('errorCode')}"
        raise SportteryApiError(f"Sporttery API error: {error_msg}")
    return data.get("value")


def fetch_league_catalog():
    value = fetch_api_json(LEAGUE_LIST_URL)
    if not isinstance(value, dict):
        raise SportteryApiError("Invalid league catalog data received")
    return value


def _combine_beijing_time(match_date, match_time):
    if not match_date or not match_time:
        return None
    try:
        text = f"{match_date}T{match_time}:00" if len(match_time) == 5 else f"{match_date}T{match_time}"
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=BUSINESS_TIMEZONE).astimezone(timezone.utc)
    except Exception:
        return None


def parse_match_results(raw_value, league_id, season_id, competition_code=None, competition_name=None, team_type="club"):
    if not isinstance(raw_value, dict):
        raise ContractError("Match result response value must be a dictionary")

    day_list = raw_value.get("matchList") or []
    matches = []
    skipped = 0

    for day in day_list:
        sub_list = day.get("subMatchList") or []
        for sub in sub_list:
            if not isinstance(sub, dict):
                continue
            # Only finished/played matches
            status_desc = str(sub.get("wbsjMatchScDesc") or "").strip()
            status_code = str(sub.get("wbsjMatchSc") or "").strip().lower()
            if status_code != "played" and status_desc != "已完成":
                skipped += 1
                continue

            # Regulation score is stored in sectionsNo999, e.g. "0:1"
            reg_score_text = str(sub.get("sectionsNo999") or "").strip()
            if not reg_score_text or ":" not in reg_score_text:
                skipped += 1
                continue

            try:
                home_str, away_str = reg_score_text.split(":", 1)
                home_score = int(home_str.strip())
                away_score = int(away_str.strip())
            except ValueError:
                skipped += 1
                continue

            home_name = str(sub.get("homeAbbCnName") or "").strip()
            away_name = str(sub.get("awayAbbCnName") or "").strip()
            home_team_id = sub.get("uniformHomeTeamId")
            away_team_id = sub.get("uniformAwayTeamId")
            match_id_num = sub.get("uniformMatchId") or sub.get("gmMatchId")

            if not home_name or not away_name or not match_id_num:
                skipped += 1
                continue

            kickoff_dt = _combine_beijing_time(sub.get("matchDate"), sub.get("matchTime"))
            kickoff_str = utc_iso(kickoff_dt) if kickoff_dt else f"{sub.get('matchDate')}T00:00:00Z"

            match_item = {
                "match_id": f"china-sporttery:{match_id_num}",
                "kickoff_utc": kickoff_str,
                "status": "FINISHED",
                "competition_code": str(competition_code or league_id),
                "competition_name": str(competition_name or "unknown"),
                "context": {
                    "team_type": team_type,
                    "competition_type": "league",
                    "venue": "home",
                    "score_basis": "regulation",
                },
                "home_team": {
                    "team_id": f"china-sporttery:{home_team_id}" if home_team_id else f"china-sporttery:team:{home_name}",
                    "name": home_name,
                    "aliases": [home_name],
                },
                "away_team": {
                    "team_id": f"china-sporttery:{away_team_id}" if away_team_id else f"china-sporttery:team:{away_name}",
                    "name": away_name,
                    "aliases": [away_name],
                },
                "home_score": home_score,
                "away_score": away_score,
                "half_score": sub.get("sectionsNo1"),
                "gm_match_id": sub.get("gmMatchId"),
                "gameweek": sub.get("gameweek"),
            }
            matches.append(match_item)

    matches.sort(key=lambda m: (m["kickoff_utc"], m["match_id"]))

    pool_id = f"china-sporttery:league:{league_id}:season:{season_id}"
    snapshot = {
        "provider": "china-sporttery",
        "source_url": f"{MATCH_RESULT_URL}?seasonId={season_id}&uniformLeagueId={league_id}",
        "fetched_at": utc_iso(utc_now()),
        "provenance_status": "verified",
        "sample_pool": {
            "pool_id": pool_id,
            "team_type": team_type,
            "competition_codes": [str(competition_code or league_id)],
        },
        "matches": matches,
        "count": len(matches),
        "skipped_unplayed_or_invalid": skipped,
    }
    return snapshot


def fetch_league_history(league_id, season_id, competition_code=None, competition_name=None, team_type="club", full_season=True):
    from datetime import timedelta
    url = f"{MATCH_RESULT_URL}?seasonId={season_id}&uniformLeagueId={league_id}"
    raw_value = fetch_api_json(url)
    if not isinstance(raw_value, dict):
        raise SportteryApiError("Invalid match result response format")

    s_start = raw_value.get("seasonStartDate")
    s_end = raw_value.get("seasonEndDate")

    if full_season and s_start and s_end:
        try:
            start_dt = datetime.strptime(s_start, "%Y-%m-%d")
            end_dt = datetime.strptime(s_end, "%Y-%m-%d")
            all_days = {}
            # Prepopulate with initial response
            for day in raw_value.get("matchList") or []:
                d_str = day.get("matchDate")
                if d_str:
                    all_days[d_str] = day

            cur = start_dt
            while cur <= end_dt:
                next_cur = min(cur + timedelta(days=60), end_dt)
                w_url = f"{url}&startDate={cur.strftime('%Y-%m-%d')}&endDate={next_cur.strftime('%Y-%m-%d')}"
                try:
                    w_data = fetch_api_json(w_url)
                    for day in w_data.get("matchList") or []:
                        d_str = day.get("matchDate")
                        if not d_str:
                            continue
                        if d_str not in all_days:
                            all_days[d_str] = day
                        else:
                            existing_ids = {s.get("uniformMatchId") for s in all_days[d_str].get("subMatchList", [])}
                            for sub in day.get("subMatchList") or []:
                                if sub.get("uniformMatchId") not in existing_ids:
                                    all_days[d_str].setdefault("subMatchList", []).append(sub)
                except Exception:
                    pass
                cur = next_cur + timedelta(days=1)
            raw_value = {**raw_value, "matchList": list(all_days.values())}
        except Exception:
            pass

    return parse_match_results(
        raw_value,
        league_id=league_id,
        season_id=season_id,
        competition_code=competition_code,
        competition_name=competition_name,
        team_type=team_type,
    )


def fetch_league_standings(league_id, season_id):
    url = f"{TABLES_URL}?seasonId={season_id}&uniformLeagueId={league_id}"
    raw_value = fetch_api_json(url)
    if not isinstance(raw_value, dict):
        raise SportteryApiError("Invalid standings response format")
    return {
        "provider": "china-sporttery",
        "source_url": url,
        "fetched_at": utc_iso(utc_now()),
        "uniform_league_id": str(league_id),
        "season_id": str(season_id),
        "total_tables": raw_value.get("totalTables", []),
        "home_tables": raw_value.get("homeTables", []),
        "away_tables": raw_value.get("awayTables", []),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Fetch official football league history, fixtures, and standings from www.sporttery.cn"
    )
    parser.add_argument("--list-leagues", action="store_true", help="List all available leagues and seasons")
    parser.add_argument("--league-id", help="Uniform league ID (e.g. 72 for Premier League, 1803 for Bundesliga)")
    parser.add_argument("--season-id", help="Season ID from league catalog")
    parser.add_argument("--competition-code", help="Standardized competition code to use in contract (e.g. PL, BL1, J1)")
    parser.add_argument("--competition-name", help="Standardized competition display name")
    parser.add_argument("--team-type", choices=("club", "national"), default="club")
    parser.add_argument("--standings", action="store_true", help="Fetch league standings instead of match history")
    parser.add_argument("--output", help="Write output JSON to this path")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.list_leagues:
            catalog = fetch_league_catalog()
            if args.output:
                write_json(args.output, catalog)
                print(json.dumps({"status": "success", "output": args.output}, ensure_ascii=False))
            else:
                print(json.dumps(catalog, ensure_ascii=False, indent=2))
            return 0

        if not args.league_id:
            print(json.dumps({"status": "error", "message": "--league-id is required when not listing leagues"}, ensure_ascii=False))
            return 1

        season_id = args.season_id
        if not season_id:
            catalog = fetch_league_catalog()
            # Try to resolve latest season for this league
            resolved_season = None
            for section in ("hot", "other"):
                for item in catalog.get(section, []):
                    if str(item.get("uniformLeagueId")) == str(args.league_id):
                        seasons = item.get("seasonList") or []
                        if seasons:
                            resolved_season = seasons[0].get("seasonId")
                            break
            if not resolved_season:
                for country_group in catalog.get("normal", []):
                    for country in country_group.get("countryList", []):
                        for item in country.get("leagueList", []):
                            if str(item.get("uniformLeagueId")) == str(args.league_id):
                                seasons = item.get("seasonList") or []
                                if seasons:
                                    resolved_season = seasons[0].get("seasonId")
                                    break
            if not resolved_season:
                print(json.dumps({"status": "error", "message": f"Could not infer latest season for league {args.league_id}, please provide --season-id"}, ensure_ascii=False))
                return 1
            season_id = resolved_season

        if args.standings:
            result = fetch_league_standings(args.league_id, season_id)
        else:
            result = fetch_league_history(
                args.league_id,
                season_id,
                competition_code=args.competition_code,
                competition_name=args.competition_name,
                team_type=args.team_type,
            )

        if args.output:
            write_json(args.output, result)
            print(json.dumps({"status": "success", "output": args.output, "count": result.get("count")}, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (SportteryApiError, ContractError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

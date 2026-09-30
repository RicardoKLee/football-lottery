#!/usr/bin/env python3

import argparse
import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from contracts import (
    BUSINESS_TIMEZONE,
    ContractError,
    load_json,
    normalize_name,
    parse_datetime,
    utc_iso,
    utc_now,
    validate_odds_snapshot,
    write_json,
)

SPORTTERY_API_URL = (
    "https://webapi.sporttery.cn/gateway/jc/football/"
    "getMatchCalculatorV1.qry?category=c&isFix=0&pcOrWap=1"
)
DEFAULT_CUTOFF_BUFFER_MINUTES = 5
OPEN_SALE_STATUSES = {
    "1",
    "2",
    "true",
    "open",
    "selling",
    "on_sale",
    "available",
    "在售",
    "销售中",
}
CLOSED_SALE_STATUSES = {
    "0",
    "false",
    "closed",
    "stopped",
    "stop",
    "off_sale",
    "停售",
    "已停售",
}


class LotteryProviderError(RuntimeError):
    pass


def _get_physical_source_ip():
    try:
        out = subprocess.check_output(["route", "-n", "get", "default"], text=True, timeout=2)
        for line in out.splitlines():
            if "interface:" in line:
                iface = line.split(":")[1].strip()
                addr = subprocess.check_output(["ipconfig", "getifaddr", iface], text=True, timeout=2).strip()
                if addr:
                    return addr
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.0.1", 80))
        addr = s.getsockname()[0]
        s.close()
        return addr
    except Exception:
        pass
    return None


def fetch_raw_lottery_data(timeout=20):
    request = urllib.request.Request(
        SPORTTERY_API_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": "https://m.sporttery.cn/",
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
        payload = _do_fetch()
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        source_ip = _get_physical_source_ip()
        if source_ip:
            try:
                payload = _do_fetch(source_ip=source_ip)
            except Exception as retry_exc:
                raise LotteryProviderError(f"Sporttery request failed: {retry_exc}") from retry_exc
        else:
            raise LotteryProviderError(f"Sporttery request failed: {exc}") from exc
    return payload, utc_now()


def _positive_float(value):
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 1.0 else None


def _goal_line(value):
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _market(raw, keys):
    if not isinstance(raw, dict):
        return None
    parsed = {key: _positive_float(raw.get(key)) for key in keys}
    return parsed if all(value is not None for value in parsed.values()) else None


def _parse_crs(raw):
    if not isinstance(raw, dict):
        return None
    parsed = {}
    for key, value in raw.items():
        odds = _positive_float(value)
        if odds is None:
            continue
        if key.startswith("s") and len(key) == 6 and key[1:3].isdigit() and key[4:6].isdigit():
            parsed[f"{int(key[1:3])}-{int(key[4:6])}"] = odds
    aliases = {"s1sh": "胜其他", "s1sd": "平其他", "s1sa": "负其他"}
    for source_key, target_key in aliases.items():
        odds = _positive_float(raw.get(source_key))
        if odds is not None:
            parsed[target_key] = odds
    return parsed or None


def _combine_local(match_date, match_time):
    if not match_date or not match_time:
        raise ContractError("Lottery match is missing matchDate or matchTime")
    text = f"{match_date}T{match_time}"
    parsed = datetime.fromisoformat(text)
    return parsed.replace(tzinfo=BUSINESS_TIMEZONE).astimezone(timezone.utc)


def _provider_time(value, date_hint):
    if not value:
        return None
    text = str(value).strip()
    try:
        if "T" in text or (len(text) >= 10 and text[4:5] == "-"):
            return parse_datetime(text)
        return _combine_local(date_hint, text)
    except (ValueError, ContractError):
        return None


def _sale_state(match, source_mode):
    raw_status = None
    for key in ("sellStatus", "saleStatus", "matchStatus", "status"):
        if match.get(key) not in (None, ""):
            raw_status = str(match[key]).strip()
            break
    if raw_status is None:
        return "unknown", False, ["sale_status_unknown"]
    normalized = raw_status.casefold()
    if normalized in OPEN_SALE_STATUSES:
        return raw_status, True, []
    if normalized in CLOSED_SALE_STATUSES:
        return raw_status, False, ["sale_closed"]
    return raw_status, False, ["sale_status_unknown"]


def _parse_match(match, business_date, fetched_at, source_mode, now):
    if not isinstance(match, dict):
        raise ContractError("Lottery match must be an object")
    provider_match_id = match.get("matchId")
    home_name = match.get("homeTeamAbbName") or match.get("homeTeamAllName")
    away_name = match.get("awayTeamAbbName") or match.get("awayTeamAllName")
    match_date = match.get("matchDate") or business_date
    if provider_match_id is None or not home_name or not away_name:
        raise ContractError("Lottery match is missing ID or team name")
    kickoff = _combine_local(match_date, match.get("matchTime"))
    exact_cutoff = None
    for key in ("sellEndTime", "saleEndTime", "stopTime", "endTime"):
        exact_cutoff = _provider_time(match.get(key), match_date)
        if exact_cutoff:
            break
    cutoff = exact_cutoff or kickoff - timedelta(minutes=DEFAULT_CUTOFF_BUFFER_MINUTES)
    sale_status, sale_open, reasons = _sale_state(match, source_mode)

    had = _market(match.get("had"), ("h", "d", "a"))
    hhad_raw = match.get("hhad") or {}
    hhad_values = _market(hhad_raw, ("h", "d", "a"))
    hhad = None
    if hhad_values:
        hhad = {"goal_line": _goal_line(hhad_raw.get("goalLine")), **hhad_values}
        if hhad["goal_line"] is None:
            hhad = None
    ttg = _market(match.get("ttg"), tuple(f"s{index}" for index in range(8)))
    hafu = _market(match.get("hafu"), ("hh", "hd", "ha", "dh", "dd", "da", "ah", "ad", "aa"))
    crs = _parse_crs(match.get("crs"))
    if not any((had, hhad, ttg, hafu, crs)):
        reasons.append("odds_missing")
    if cutoff <= now:
        reasons.append("cutoff_passed")
    is_available = sale_open and not reasons

    observed_at = None
    for key in ("oddsUpdateTime", "updateTime", "lastUpdateTime"):
        observed_at = _provider_time(match.get(key), match_date)
        if observed_at:
            break
    observed_at = observed_at or fetched_at
    official_listing = match.get("official_listing")
    if not isinstance(official_listing, dict):
        listing_status = "confirmed" if (sale_open and provider_match_id) else "unknown"
        official_listing = {
            "status": listing_status,
            "source_url": SPORTTERY_API_URL,
            "provider_match_id": str(provider_match_id),
            "observed_at": utc_iso(fetched_at),
        }
    market_status = match.get("market_status")
    if not isinstance(market_status, dict):
        pool_list = match.get("poolList")
        if isinstance(pool_list, list) and pool_list:
            pool_map = {
                str(p.get("poolCode", "")).lower(): str(p.get("poolStatus", "")).lower()
                for p in pool_list
                if isinstance(p, dict)
            }
            market_status = {}
            for m, parsed_val in (("had", had), ("hhad", hhad), ("ttg", ttg), ("crs", crs)):
                p_status = pool_map.get(m)
                if p_status == "selling" and parsed_val is not None:
                    market_status[m] = "open"
                elif p_status is not None:
                    market_status[m] = "closed"
                else:
                    market_status[m] = "open" if (sale_open and parsed_val is not None) else "closed"
        else:
            market_status = {
                "had": "open" if (sale_open and had is not None) else "unknown",
                "hhad": "open" if (sale_open and hhad is not None) else "unknown",
                "ttg": "open" if (sale_open and ttg is not None) else "unknown",
                "crs": "open" if (sale_open and crs is not None) else "unknown",
            }
    single_status = match.get("single_status")
    if not isinstance(single_status, dict):
        pool_list = match.get("poolList")
        if isinstance(pool_list, list) and pool_list:
            single_map = {}
            for p in pool_list:
                if isinstance(p, dict):
                    p_code = str(p.get("poolCode", "")).lower()
                    is_single = bool(p.get("single") == 1 or p.get("bettingSingle") == 1)
                    single_map[p_code] = is_single
            single_status = {
                "had": bool(single_map.get("had", False)),
                "hhad": bool(single_map.get("hhad", False)),
                "ttg": bool(single_map.get("ttg", False)),
                "crs": bool(single_map.get("crs", True)),
            }
        else:
            single_status = {
                "had": False,
                "hhad": False,
                "ttg": False,
                "crs": True,
            }
    return {
        "match_id": f"sporttery:{provider_match_id}",
        "provider_match_id": str(provider_match_id),
        "match_num": str(match.get("matchNumStr") or ""),
        "competition": str(match.get("leagueAbbName") or match.get("leagueAllName") or "unknown"),
        "business_date": str(business_date or match_date),
        "match_date": str(match_date),
        "official_listing": official_listing,
        "market_status": market_status,
        "single_status": single_status,
        "kickoff_utc": utc_iso(kickoff),
        "cutoff_utc": utc_iso(cutoff),
        "cutoff_is_estimated": exact_cutoff is None,
        "sale_status": sale_status,
        "is_available": is_available,
        "availability_reasons": list(dict.fromkeys(reasons)),
        "odds_observed_at": utc_iso(observed_at),
        "home_team": {
            "name": str(home_name),
            "provider_id": str(match.get("homeTeamId")) if match.get("homeTeamId") is not None else None,
        },
        "away_team": {
            "name": str(away_name),
            "provider_id": str(match.get("awayTeamId")) if match.get("awayTeamId") is not None else None,
        },
        "odds": {"had": had, "hhad": hhad, "ttg": ttg, "hafu": hafu, "crs": crs},
    }


def parse_odds_data(raw_data, fetched_at=None, source_mode="live", now=None, requested_date=None):
    fetched_at = parse_datetime(fetched_at or utc_now())
    now = parse_datetime(now or utc_now())
    if source_mode not in {"live", "file"}:
        raise ContractError("source_mode must be live or file")
    if not isinstance(raw_data, dict) or raw_data.get("success") is not True:
        raise ContractError("Sporttery payload does not report success")
    value = raw_data.get("value")
    if not isinstance(value, dict) or not isinstance(value.get("matchInfoList"), list):
        raise ContractError("Sporttery payload has no matchInfoList")

    matches = []
    errors = []
    for day in value["matchInfoList"]:
        if not isinstance(day, dict):
            raise ContractError("Each matchInfoList item must be an object")
        business_date = day.get("businessDate")
        sub_matches = day.get("subMatchList") or []
        if not isinstance(sub_matches, list):
            raise ContractError("subMatchList must be an array")
        for raw_match in sub_matches:
            try:
                matches.append(
                    _parse_match(raw_match, business_date, fetched_at, source_mode, now)
                )
            except ContractError as exc:
                match_id = raw_match.get("matchId") if isinstance(raw_match, dict) else None
                errors.append({"match_id": match_id, "reason": str(exc)})
    snapshot = {
        "kind": "odds_snapshot",
        "provider": "china-sporttery",
        "source_url": SPORTTERY_API_URL,
        "source_mode": source_mode,
        "fetched_at": utc_iso(fetched_at),
        "requested_date": requested_date,
        "parse_errors": errors,
        "matches": matches,
    }
    return validate_odds_snapshot(snapshot)


def filter_matches(matches, date=None, team=None, match_id=None, available_only=False):
    filtered = []
    target_date = date.replace("-", "") if date else None
    target_team = normalize_name(team) if team else None
    target_match_id = str(match_id) if match_id is not None else None
    for match in matches:
        if target_match_id and target_match_id not in {
            str(match.get("match_id")),
            str(match.get("provider_match_id")),
        }:
            continue
        if target_date:
            dates = {
                str(match.get("match_date", "")).replace("-", ""),
                str(match.get("business_date", "")).replace("-", ""),
            }
            if target_date not in dates:
                continue
        if target_team:
            names = {
                normalize_name(match.get("home_team", {}).get("name")),
                normalize_name(match.get("away_team", {}).get("name")),
            }
            if target_team not in names:
                continue
        if available_only and not match.get("is_available"):
            continue
        filtered.append(match)
    return filtered


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Fetch current China Sporttery football odds.")
    parser.add_argument("--date", help="Match or business date, YYYY-MM-DD or YYYYMMDD")
    parser.add_argument("--team", help="Exact normalized team name")
    parser.add_argument("--match-id", help="Sporttery match ID")
    parser.add_argument("--available-only", action="store_true")
    parser.add_argument("--input", help="Explicit raw or normalized JSON snapshot; never auto-loaded")
    parser.add_argument("--output", help="Write normalized odds snapshot to this path")
    return parser.parse_args(argv)


def run(args):
    if args.input:
        payload = load_json(args.input)
        if payload.get("kind") == "odds_snapshot":
            snapshot = validate_odds_snapshot(payload)
            snapshot = {**snapshot, "source_mode": "file"}
        else:
            fetched_at = payload.get("fetched_at") or datetime.fromtimestamp(
                os.path.getmtime(args.input), tz=timezone.utc
            )
            snapshot = parse_odds_data(
                payload, fetched_at=fetched_at, source_mode="file", requested_date=args.date
            )
    else:
        payload, fetched_at = fetch_raw_lottery_data()
        snapshot = parse_odds_data(
            payload, fetched_at=fetched_at, source_mode="live", requested_date=args.date
        )
    filtered = filter_matches(
        snapshot["matches"],
        date=args.date,
        team=args.team,
        match_id=args.match_id,
        available_only=args.available_only,
    )
    return {**snapshot, "matches": filtered, "count": len(filtered)}


def main(argv=None):
    args = parse_args(argv)
    try:
        result = run(args)
        if args.output:
            write_json(args.output, result)
            print(json.dumps({"status": "success", "output": args.output, "count": result["count"]}, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ContractError, LotteryProviderError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

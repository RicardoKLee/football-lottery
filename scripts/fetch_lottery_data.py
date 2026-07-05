#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import urllib.request
import json
import argparse
from datetime import datetime

def fetch_raw_lottery_data():
    """
    Fetch the live football match and odds data from China Sporttery official API.
    """
    import os
    # Check for local cache file first to support offline running and bypass network block
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lottery_data_20260703.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                print(f"Loading lottery data from local cache: {cache_path}")
                return json.load(f)
        except Exception as e:
            sys.stderr.write(f"Error loading local lottery cache: {e}\n")

    url = "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry?category=c&isFix=0&pcOrWap=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://m.sporttery.cn/"
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read().decode('utf-8')
            return json.loads(content)
    except Exception as e:
        sys.stderr.write(f"Error fetching lottery data: {e}\n")
        return None

def parse_odds_data(raw_data):
    """
    Parse raw sporttery JSON into a cleaner, structured format.
    """
    if not raw_data or not raw_data.get("success") or "value" not in raw_data:
        return []
    
    match_info_list = raw_data["value"].get("matchInfoList", [])
    parsed_matches = []
    
    for day_info in match_info_list:
        business_date = day_info.get("businessDate") # YYYY-MM-DD
        sub_matches = day_info.get("subMatchList", [])
        
        for match in sub_matches:
            match_id = match.get("matchId")
            match_num_str = match.get("matchNumStr") # e.g., "周六001"
            match_date = match.get("matchDate") # YYYY-MM-DD
            match_time = match.get("matchTime") # HH:MM:SS
            
            home_team = match.get("homeTeamAbbName") or match.get("homeTeamAllName")
            away_team = match.get("awayTeamAbbName") or match.get("awayTeamAllName")
            league_name = match.get("leagueAbbName") or match.get("leagueAllName")
            
            # 1. HAD (胜平负)
            had_raw = match.get("had") or {}
            had = {
                "h": float(had_raw.get("h")) if had_raw.get("h") else None,
                "d": float(had_raw.get("d")) if had_raw.get("d") else None,
                "a": float(had_raw.get("a")) if had_raw.get("a") else None,
            } if had_raw.get("h") else None
            
            # 2. HHAD (让球胜平负)
            hhad_raw = match.get("hhad") or {}
            hhad = {
                "goal_line": int(float(hhad_raw.get("goalLine"))) if hhad_raw.get("goalLine") else None,
                "h": float(hhad_raw.get("h")) if hhad_raw.get("h") else None,
                "d": float(hhad_raw.get("d")) if hhad_raw.get("d") else None,
                "a": float(hhad_raw.get("a")) if hhad_raw.get("a") else None,
            } if hhad_raw.get("h") else None
            
            # 3. TTG (总进球数)
            ttg_raw = match.get("ttg") or {}
            ttg = {
                "s0": float(ttg_raw.get("s0")) if ttg_raw.get("s0") else None,
                "s1": float(ttg_raw.get("s1")) if ttg_raw.get("s1") else None,
                "s2": float(ttg_raw.get("s2")) if ttg_raw.get("s2") else None,
                "s3": float(ttg_raw.get("s3")) if ttg_raw.get("s3") else None,
                "s4": float(ttg_raw.get("s4")) if ttg_raw.get("s4") else None,
                "s5": float(ttg_raw.get("s5")) if ttg_raw.get("s5") else None,
                "s6": float(ttg_raw.get("s6")) if ttg_raw.get("s6") else None,
                "s7": float(ttg_raw.get("s7")) if ttg_raw.get("s7") else None,
            } if ttg_raw.get("s0") else None
            
            # 4. HAFU (半全场)
            hafu_raw = match.get("hafu") or {}
            hafu = {
                "hh": float(hafu_raw.get("hh")) if hafu_raw.get("hh") else None,
                "hd": float(hafu_raw.get("hd")) if hafu_raw.get("hd") else None,
                "ha": float(hafu_raw.get("ha")) if hafu_raw.get("ha") else None,
                "dh": float(hafu_raw.get("dh")) if hafu_raw.get("dh") else None,
                "dd": float(hafu_raw.get("dd")) if hafu_raw.get("dd") else None,
                "da": float(hafu_raw.get("da")) if hafu_raw.get("da") else None,
                "ah": float(hafu_raw.get("ah")) if hafu_raw.get("ah") else None,
                "ad": float(hafu_raw.get("ad")) if hafu_raw.get("ad") else None,
                "aa": float(hafu_raw.get("aa")) if hafu_raw.get("aa") else None,
            } if hafu_raw.get("hh") else None
            
            # 5. CRS (比分)
            crs_raw = match.get("crs") or {}
            crs = {}
            if crs_raw.get("s00s00"):
                # Map specific score odds
                for k, v in crs_raw.items():
                    if k.startswith("s") and len(k) == 6 and k[3].isdigit():
                        # Format: s01s00 -> "1-0" or s00s00 -> "0-0"
                        h_score = int(k[1:3])
                        a_score = int(k[4:6])
                        crs[f"{h_score}-{a_score}"] = float(v)
                # Map others
                if crs_raw.get("s1sh"): crs["胜其他"] = float(crs_raw["s1sh"])
                if crs_raw.get("s1sd"): crs["平其他"] = float(crs_raw["s1sd"])
                if crs_raw.get("s1sa"): crs["负其他"] = float(crs_raw["s1sa"])
            
            parsed_matches.append({
                "match_id": match_id,
                "match_num_str": match_num_str,
                "business_date": business_date,
                "match_date": match_date,
                "match_time": match_time,
                "home_team": home_team,
                "away_team": away_team,
                "league_name": league_name,
                "odds": {
                    "had": had,
                    "hhad": hhad,
                    "ttg": ttg,
                    "hafu": hafu,
                    "crs": crs if crs else None
                }
            })
            
    return parsed_matches

def filter_matches(matches, date=None, team=None, match_id=None):
    """
    Filter parsed matches based on date, team, or match_id.
    """
    filtered = []
    for m in matches:
        # Filter by match_id
        if match_id and str(m["match_id"]) != str(match_id):
            continue
            
        # Filter by date (supports YYYY-MM-DD or YYYYMMDD)
        if date:
            clean_date = date.replace("-", "")
            m_date_clean = m["match_date"].replace("-", "")
            m_bdate_clean = m["business_date"].replace("-", "")
            if clean_date != m_date_clean and clean_date != m_bdate_clean:
                continue
                
        # Filter by team (fuzzy matching)
        if team:
            team_lower = team.lower()
            h_lower = m["home_team"].lower()
            a_lower = m["away_team"].lower()
            if team_lower not in h_lower and team_lower not in a_lower:
                continue
                
        filtered.append(m)
    return filtered

def main():
    parser = argparse.ArgumentParser(description="Fetch and parse China Sporttery football odds.")
    parser.add_argument("--date", type=str, help="Filter by match date (YYYY-MM-DD or YYYYMMDD)")
    parser.add_argument("--team", type=str, help="Filter by team name (fuzzy match)")
    parser.add_argument("--match-id", type=str, help="Filter by specific match ID")
    parser.add_argument("--output", type=str, help="Save output JSON to a file")
    
    args = parser.parse_args()
    
    raw_data = fetch_raw_lottery_data()
    if not raw_data:
        print(json.dumps({"status": "error", "message": "Failed to fetch data from Sporttery API"}, ensure_ascii=False))
        sys.exit(1)
        
    matches = parse_odds_data(raw_data)
    filtered_matches = filter_matches(matches, date=args.date, team=args.team, match_id=args.match_id)
    
    result = {
        "status": "success",
        "count": len(filtered_matches),
        "matches": filtered_matches
    }
    
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"Successfully saved {len(filtered_matches)} matches to {args.output}")
        except Exception as e:
            print(json.dumps({"status": "error", "message": f"Failed to save output file: {e}"}, ensure_ascii=False))
            sys.exit(1)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

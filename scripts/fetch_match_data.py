#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import urllib.request
import json
import math

# 2-letter Country Codes mapping with multi-language aliases, 2026 Group Stage info, and estimated Market Values (Transfermarkt 2026)
COUNTRY_METADATA = {
    "ES": {
        "names": ["spain", "西班牙", "es", "esp"],
        "en": "Spain",
        "cn": "西班牙",
        "market_value_eur": 950000000,
        "wc2026": {
            "group": "Group H",
            "fixtures": [
                {"date": "2026-06-15", "opponent": "CV", "stadium": "Mercedes-Benz Stadium (Atlanta)", "altitude_m": 320, "result": "0-0"},
                {"date": "2026-06-21", "opponent": "SA", "stadium": "Mercedes-Benz Stadium (Atlanta)", "altitude_m": 320, "result": "Upcoming"},
                {"date": "2026-06-27", "opponent": "UY", "stadium": "Estadio Akron (Zapopan/Guadalajara)", "altitude_m": 1566, "result": "Upcoming"}
            ]
        }
    },
    "SA": {
        "names": ["saudi arabia", "saudi", "沙特", "沙特阿拉伯", "sa", "sau", "ksa"],
        "en": "Saudi Arabia",
        "cn": "沙特阿拉伯",
        "market_value_eur": 40000000,
        "wc2026": {
            "group": "Group H",
            "fixtures": [
                {"date": "2026-06-15", "opponent": "UY", "stadium": "Hard Rock Stadium (Miami)", "altitude_m": 2, "result": "1-1"},
                {"date": "2026-06-21", "opponent": "ES", "stadium": "Mercedes-Benz Stadium (Atlanta)", "altitude_m": 320, "result": "Upcoming"},
                {"date": "2026-06-27", "opponent": "CV", "stadium": "NRG Stadium (Houston)", "altitude_m": 24, "result": "Upcoming"}
            ]
        }
    },
    "HR": {
        "names": ["croatia", "克罗地亚", "hr", "cro"],
        "en": "Croatia",
        "cn": "克罗地亚",
        "market_value_eur": 320000000,
        "wc2026": {
            "group": "Group L",
            "fixtures": [
                {"date": "2026-06-17", "opponent": "EN", "stadium": "AT&T Stadium (Dallas/Arlington)", "altitude_m": 184, "result": "2-4"},
                {"date": "2026-06-23", "opponent": "PA", "stadium": "BMO Field (Toronto)", "altitude_m": 76, "result": "Upcoming"},
                {"date": "2026-06-27", "opponent": "GH", "stadium": "Lincoln Financial Field (Philadelphia)", "altitude_m": 12, "result": "Upcoming"}
            ]
        }
    },
    "EN": {
        "names": ["england", "英格兰", "en", "eng"],
        "en": "England",
        "cn": "英格兰",
        "market_value_eur": 1400000000,
        "wc2026": {
            "group": "Group L",
            "fixtures": [
                {"date": "2026-06-17", "opponent": "HR", "stadium": "AT&T Stadium (Dallas/Arlington)", "altitude_m": 184, "result": "4-2"},
                {"date": "2026-06-23", "opponent": "GH", "stadium": "Gillette Stadium (Foxborough)", "altitude_m": 90, "result": "Upcoming"},
                {"date": "2026-06-27", "opponent": "PA", "stadium": "MetLife Stadium (East Rutherford)", "altitude_m": 2, "result": "Upcoming"}
            ]
        }
    },
    "UY": {
        "names": ["uruguay", "乌拉圭", "uy", "uru"],
        "en": "Uruguay",
        "cn": "乌拉圭",
        "market_value_eur": 480000000,
        "wc2026": {
            "group": "Group H",
            "fixtures": [
                {"date": "2026-06-15", "opponent": "SA", "stadium": "Hard Rock Stadium (Miami)", "altitude_m": 2, "result": "1-1"},
                {"date": "2026-06-21", "opponent": "CV", "stadium": "Hard Rock Stadium (Miami)", "altitude_m": 2, "result": "Upcoming"},
                {"date": "2026-06-27", "opponent": "ES", "stadium": "Estadio Akron (Zapopan/Guadalajara)", "altitude_m": 1566, "result": "Upcoming"}
            ]
        }
    },
    "CV": {
        "names": ["cape verde", "cabo verde", "佛得角", "cv", "cpv"],
        "en": "Cape Verde",
        "cn": "佛得角",
        "market_value_eur": 25000000,
        "wc2026": {
            "group": "Group H",
            "fixtures": [
                {"date": "2026-06-15", "opponent": "ES", "stadium": "Mercedes-Benz Stadium (Atlanta)", "altitude_m": 320, "result": "0-0"},
                {"date": "2026-06-21", "opponent": "UY", "stadium": "Hard Rock Stadium (Miami)", "altitude_m": 2, "result": "Upcoming"},
                {"date": "2026-06-27", "opponent": "SA", "stadium": "NRG Stadium (Houston)", "altitude_m": 24, "result": "Upcoming"}
            ]
        }
    },
    "AR": {
        "names": ["argentina", "阿根廷", "ar", "arg"],
        "en": "Argentina",
        "cn": "阿根廷",
        "market_value_eur": 850000000,
        "wc2026": {"group": "Group A", "fixtures": []}
    },
    "FR": {
        "names": ["france", "法国", "fr", "fra"],
        "en": "France",
        "cn": "法国",
        "market_value_eur": 1200000000,
        "wc2026": {"group": "Group B", "fixtures": []}
    },
    "BR": {
        "names": ["brazil", "巴西", "br", "bra"],
        "en": "Brazil",
        "cn": "巴西",
        "market_value_eur": 1050000000,
        "wc2026": {"group": "Group C", "fixtures": []}
    },
    "PT": {
        "names": ["portugal", "葡萄牙", "pt", "por"],
        "en": "Portugal",
        "cn": "葡萄牙",
        "market_value_eur": 880000000,
        "wc2026": {
            "group": "Group K",
            "fixtures": [
                {"date": "2026-06-17", "opponent": "CD", "stadium": "Houston Stadium (Houston)", "altitude_m": 15, "result": "1-1"},
                {"date": "2026-06-23", "opponent": "UZ", "stadium": "Gillette Stadium (Foxborough)", "altitude_m": 90, "result": "Upcoming"},
                {"date": "2026-06-27", "opponent": "CO", "stadium": "Hard Rock Stadium (Miami)", "altitude_m": 2, "result": "Upcoming"}
            ]
        }
    },
    "CD": {
        "names": ["democratic republic of the congo", "dr congo", "congo dr", "congo-kinshasa", "刚果金", "刚果民主共和国", "cd", "cod"],
        "en": "DR Congo",
        "cn": "刚果民主共和国",
        "market_value_eur": 110000000,
        "wc2026": {
            "group": "Group K",
            "fixtures": [
                {"date": "2026-06-17", "opponent": "PT", "stadium": "Houston Stadium (Houston)", "altitude_m": 15, "result": "1-1"},
                {"date": "2026-06-23", "opponent": "CO", "stadium": "Hard Rock Stadium (Miami)", "altitude_m": 2, "result": "Upcoming"},
                {"date": "2026-06-27", "opponent": "UZ", "stadium": "Gillette Stadium (Foxborough)", "altitude_m": 90, "result": "Upcoming"}
            ]
        }
    },
    "NL": {
        "names": ["netherlands", "holland", "荷兰", "nl", "ned"],
        "en": "Netherlands",
        "cn": "荷兰",
        "market_value_eur": 750000000,
        "wc2026": {"group": "Group E", "fixtures": []}
    },
    "DE": {
        "names": ["germany", "德国", "de", "ger"],
        "en": "Germany",
        "cn": "德国",
        "market_value_eur": 800000000,
        "wc2026": {"group": "Group F", "fixtures": []}
    },
    "IT": {
        "names": ["italy", "意大利", "it", "ita"],
        "en": "Italy",
        "cn": "意大利",
        "market_value_eur": 650000000,
        "wc2026": {"group": "Group G", "fixtures": []}
    },
    "JP": {
        "names": ["japan", "日本", "jp", "jpn"],
        "en": "Japan",
        "cn": "日本",
        "market_value_eur": 280000000,
        "wc2026": {"group": "Group I", "fixtures": []}
    },
    "US": {
        "names": ["united states", "usa", "us", "美国", "美利坚"],
        "en": "United States",
        "cn": "美国",
        "market_value_eur": 350000000,
        "wc2026": {"group": "Group J", "fixtures": []}
    },
    "MX": {
        "names": ["mexico", "墨西哥", "mx", "mex"],
        "en": "Mexico",
        "cn": "墨西哥",
        "market_value_eur": 220000000,
        "wc2026": {"group": "Group K", "fixtures": []}
    },
    "CA": {
        "names": ["canada", "加拿大", "ca", "can"],
        "en": "Canada",
        "cn": "加拿大",
        "market_value_eur": 180000000,
        "wc2026": {"group": "Group M", "fixtures": []}
    },
    "SE": {
        "names": ["sweden", "瑞典", "se", "swe"],
        "en": "Sweden",
        "cn": "瑞典",
        "market_value_eur": 300000000,
        "wc2026": {"group": "Group F", "fixtures": []}
    },
    "CI": {
        "names": ["ivory coast", "côte d'ivoire", "cote d'ivoire", "科特迪瓦", "ci", "civ"],
        "en": "Ivory Coast",
        "cn": "科特迪瓦",
        "market_value_eur": 250000000,
        "wc2026": {"group": "Group F", "fixtures": []}
    },
    "EC": {
        "names": ["ecuador", "厄瓜多尔", "ec", "ecu"],
        "en": "Ecuador",
        "cn": "厄瓜多尔",
        "market_value_eur": 200000000,
        "wc2026": {"group": "Group G", "fixtures": []}
    },
    "CW": {
        "names": ["curacao", "curaçao", "库拉索", "cw", "cuw"],
        "en": "Curaçao",
        "cn": "库拉索",
        "market_value_eur": 15000000,
        "wc2026": {"group": "Group G", "fixtures": []}
    },
    "TN": {
        "names": ["tunisia", "突尼斯", "tn", "tun"],
        "en": "Tunisia",
        "cn": "突尼斯",
        "market_value_eur": 45000000,
        "wc2026": {"group": "Group I", "fixtures": []}
    },
    "BE": {
        "names": ["belgium", "比利时", "be", "bel"],
        "en": "Belgium",
        "cn": "比利时",
        "market_value_eur": 550000000,
        "wc2026": {"group": "Group J", "fixtures": []}
    },
    "IR": {
        "names": ["iran", "伊朗", "ir", "irn"],
        "en": "Iran",
        "cn": "伊朗",
        "market_value_eur": 50000000,
        "wc2026": {"group": "Group J", "fixtures": []}
    },
    "NZ": {
        "names": ["new zealand", "新西兰", "nz", "nzl"],
        "en": "New Zealand",
        "cn": "新西兰",
        "market_value_eur": 25000000,
        "wc2026": {"group": "Group K", "fixtures": []}
    },
    "EG": {
        "names": ["egypt", "埃及", "eg", "egy"],
        "en": "Egypt",
        "cn": "埃及",
        "market_value_eur": 120000000,
        "wc2026": {"group": "Group K", "fixtures": []}
    },
    "AT": {
        "names": ["austria", "奥地利", "at", "aut"],
        "en": "Austria",
        "cn": "奥地利",
        "market_value_eur": 280000000,
        "wc2026": {"group": "Group L", "fixtures": []}
    },
    "IQ": {
        "names": ["iraq", "伊拉克", "iq", "irq"],
        "en": "Iraq",
        "cn": "伊拉克",
        "market_value_eur": 15000000,
        "wc2026": {"group": "Group L", "fixtures": []}
    },
    "NO": {
        "names": ["norway", "挪威", "no", "nor"],
        "en": "Norway",
        "cn": "挪威",
        "market_value_eur": 450000000,
        "wc2026": {"group": "Group M", "fixtures": []}
    },
    "SN": {
        "names": ["senegal", "塞内加尔", "sn", "sen"],
        "en": "Senegal",
        "cn": "塞内加尔",
        "market_value_eur": 200000000,
        "wc2026": {"group": "Group M", "fixtures": []}
    },
    "JO": {
        "names": ["jordan", "约旦", "jo", "jor"],
        "en": "Jordan",
        "cn": "约旦",
        "market_value_eur": 15000000,
        "wc2026": {"group": "Group N", "fixtures": []}
    },
    "DZ": {
        "names": ["algeria", "阿尔及利亚", "dz", "alg"],
        "en": "Algeria",
        "cn": "阿尔及利亚",
        "market_value_eur": 180000000,
        "wc2026": {"group": "Group N", "fixtures": []}
    }
}

def find_country_code(name_input):
    """
    Fuzzy match country code by English, Chinese name, or aliases.
    """
    name_clean = name_input.strip().lower()
    for code, data in COUNTRY_METADATA.items():
        if name_clean in data["names"]:
            return code
        if name_clean == data["en"].lower() or name_clean == data["cn"].lower():
            return code
        if data["cn"].lower() in name_clean or name_clean in data["cn"].lower():
            return code
    return None

def fetch_elo_ratings():
    """
    Fetch the live world Elo ratings table from eloratings.net.
    Returns a dict {code: {elo: int, rank: int, total_matches: int, won: int, drawn: int, lost: int}}
    """
    url = "https://www.eloratings.net/World.tsv"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read().decode('utf-8')
            
        ratings = {}
        for line in content.splitlines():
            parts = line.split("\t")
            if len(parts) > 10:
                code = parts[2].strip()
                try:
                    rank = int(parts[0])
                    elo = int(parts[3])
                    # col 23 matches total, col 24 won, col 25 drawn, col 26 lost
                    total_matches = int(parts[22]) if len(parts) > 22 else 0
                    won = int(parts[23]) if len(parts) > 23 else 0
                    drawn = int(parts[24]) if len(parts) > 24 else 0
                    lost = int(parts[25]) if len(parts) > 25 else 0
                    
                    ratings[code] = {
                        "rank": rank,
                        "elo": elo,
                        "total_matches": total_matches,
                        "won": won,
                        "drawn": drawn,
                        "lost": lost
                    }
                except ValueError:
                    continue
        return ratings
    except Exception as e:
        sys.stderr.write(f"Error fetching Elo ratings: {e}\n")
        return {}

def calculate_probabilities(elo1, elo2):
    """
    Calculate Win, Draw, Loss probabilities using Elo rating difference.
    """
    dr = elo1 - elo2
    we = 1.0 / (10**(-dr / 400.0) + 1.0)
    
    # Empirical football draw probability formula:
    p_draw = 0.26 * math.exp(-0.5 * (dr / 220.0)**2)
    
    p_win = we - 0.5 * p_draw
    p_loss = 1.0 - p_win - p_draw
    
    p_win = max(0.01, min(0.98, p_win))
    p_draw = max(0.01, min(0.50, p_draw))
    p_loss = max(0.01, min(0.98, p_loss))
    
    total = p_win + p_draw + p_loss
    return p_win / total, p_draw / total, p_loss / total

def main():
    if len(sys.argv) < 3:
        print(json.dumps({
            "status": "error",
            "message": "Usage: python3 fetch_match_data.py <team1> <team2>"
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
        
    t1_input = sys.argv[1]
    t2_input = sys.argv[2]
    
    code1 = find_country_code(t1_input)
    code2 = find_country_code(t2_input)
    
    if not code1 or not code2:
        # Fallback to simple matching if not found in metadata
        error_msg = f"Could not identify one or both countries: {t1_input} ({code1}), {t2_input} ({code2})"
        print(json.dumps({
            "status": "error",
            "message": error_msg
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
        
    ratings = fetch_elo_ratings()
    
    if code1 not in ratings or code2 not in ratings:
        error_msg = f"Elo ratings not found in the live TSV table for {code1} or {code2}"
        print(json.dumps({
            "status": "error",
            "message": error_msg
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
        
    r1 = ratings[code1]
    r2 = ratings[code2]
    
    p_win, p_draw, p_loss = calculate_probabilities(r1["elo"], r2["elo"])
    
    # Aggregate results including 2026 World Cup Stage details and Transfermarkt身价
    meta1 = COUNTRY_METADATA[code1]
    meta2 = COUNTRY_METADATA[code2]
    
    result = {
        "status": "success",
        "match": {
            "team1": {
                "name_cn": meta1["cn"],
                "name_en": meta1["en"],
                "code": code1,
                "elo": r1["elo"],
                "rank": r1["rank"],
                "market_value_eur": meta1["market_value_eur"],
                "wc2026_info": meta1["wc2026"],
                "all_time_stats": {
                    "matches": r1["total_matches"],
                    "won": r1["won"],
                    "drawn": r1["drawn"],
                    "lost": r1["lost"]
                }
            },
            "team2": {
                "name_cn": meta2["cn"],
                "name_en": meta2["en"],
                "code": code2,
                "elo": r2["elo"],
                "rank": r2["rank"],
                "market_value_eur": meta2["market_value_eur"],
                "wc2026_info": meta2["wc2026"],
                "all_time_stats": {
                    "matches": r2["total_matches"],
                    "won": r2["won"],
                    "drawn": r2["drawn"],
                    "lost": r2["lost"]
                }
            },
            "elo_difference": r1["elo"] - r2["elo"],
            "mathematical_probabilities": {
                "team1_win": f"{p_win:.2%}",
                "draw": f"{p_draw:.2%}",
                "team2_win": f"{p_loss:.2%}"
            }
        }
    }
    
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

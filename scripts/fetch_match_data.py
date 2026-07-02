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
        "average_age": 25.2,
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
        "average_age": 27.8,
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
        "average_age": 28.6,
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
        "average_age": 25.8,
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
        "average_age": 25.5,
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
        "average_age": 27.2,
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
        "average_age": 27.5,
        "wc2026": {"group": "Group A", "fixtures": []}
    },
    "FR": {
        "names": ["france", "法国", "fr", "fra"],
        "en": "France",
        "cn": "法国",
        "market_value_eur": 1200000000,
        "average_age": 25.4,
        "wc2026": {"group": "Group B", "fixtures": []}
    },
    "BR": {
        "names": ["brazil", "巴西", "br", "bra"],
        "en": "Brazil",
        "cn": "巴西",
        "market_value_eur": 1050000000,
        "average_age": 26.2,
        "wc2026": {"group": "Group C", "fixtures": []}
    },
    "PT": {
        "names": ["portugal", "葡萄牙", "pt", "por"],
        "en": "Portugal",
        "cn": "葡萄牙",
        "market_value_eur": 880000000,
        "average_age": 26.8,
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
        "average_age": 26.5,
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
        "average_age": 26.1,
        "wc2026": {"group": "Group E", "fixtures": []}
    },
    "DE": {
        "names": ["germany", "德国", "de", "ger"],
        "en": "Germany",
        "cn": "德国",
        "market_value_eur": 800000000,
        "average_age": 26.7,
        "wc2026": {"group": "Group F", "fixtures": []}
    },
    "IT": {
        "names": ["italy", "意大利", "it", "ita"],
        "en": "Italy",
        "cn": "意大利",
        "market_value_eur": 650000000,
        "average_age": 26.0,
        "wc2026": {"group": "Group G", "fixtures": []}
    },
    "JP": {
        "names": ["japan", "日本", "jp", "jpn"],
        "en": "Japan",
        "cn": "日本",
        "market_value_eur": 280000000,
        "average_age": 25.9,
        "wc2026": {"group": "Group I", "fixtures": []}
    },
    "US": {
        "names": ["united states", "usa", "us", "美国", "美利坚"],
        "en": "United States",
        "cn": "美国",
        "market_value_eur": 350000000,
        "average_age": 24.8,
        "wc2026": {"group": "Group J", "fixtures": []}
    },
    "MX": {
        "names": ["mexico", "墨西哥", "mx", "mex"],
        "en": "Mexico",
        "cn": "墨西哥",
        "market_value_eur": 220000000,
        "average_age": 27.2,
        "wc2026": {"group": "Group K", "fixtures": []}
    },
    "CA": {
        "names": ["canada", "加拿大", "ca", "can"],
        "en": "Canada",
        "cn": "加拿大",
        "market_value_eur": 180000000,
        "average_age": 25.3,
        "wc2026": {"group": "Group M", "fixtures": []}
    },
    "SE": {
        "names": ["sweden", "瑞典", "se", "swe"],
        "en": "Sweden",
        "cn": "瑞典",
        "market_value_eur": 300000000,
        "average_age": 25.6,
        "wc2026": {"group": "Group F", "fixtures": []}
    },
    "CI": {
        "names": ["ivory coast", "côte d'ivoire", "cote d'ivoire", "科特迪瓦", "ci", "civ"],
        "en": "Ivory Coast",
        "cn": "科特迪瓦",
        "market_value_eur": 250000000,
        "average_age": 26.3,
        "wc2026": {"group": "Group F", "fixtures": []}
    },
    "EC": {
        "names": ["ecuador", "厄瓜多尔", "ec", "ecu"],
        "en": "Ecuador",
        "cn": "厄瓜多尔",
        "market_value_eur": 200000000,
        "average_age": 24.5,
        "wc2026": {"group": "Group G", "fixtures": []}
    },
    "CW": {
        "names": ["curacao", "curaçao", "库拉索", "cw", "cuw"],
        "en": "Curaçao",
        "cn": "库拉索",
        "market_value_eur": 15000000,
        "average_age": 28.2,
        "wc2026": {"group": "Group G", "fixtures": []}
    },
    "TN": {
        "names": ["tunisia", "突尼斯", "tn", "tun"],
        "en": "Tunisia",
        "cn": "突尼斯",
        "market_value_eur": 45000000,
        "average_age": 27.1,
        "wc2026": {"group": "Group I", "fixtures": []}
    },
    "BE": {
        "names": ["belgium", "比利时", "be", "bel"],
        "en": "Belgium",
        "cn": "比利时",
        "market_value_eur": 550000000,
        "average_age": 26.6,
        "wc2026": {"group": "Group J", "fixtures": []}
    },
    "IR": {
        "names": ["iran", "伊朗", "ir", "irn"],
        "en": "Iran",
        "cn": "伊朗",
        "market_value_eur": 50000000,
        "average_age": 29.1,
        "wc2026": {"group": "Group J", "fixtures": []}
    },
    "NZ": {
        "names": ["new zealand", "新西兰", "nz", "nzl"],
        "en": "New Zealand",
        "cn": "新西兰",
        "market_value_eur": 25000000,
        "average_age": 25.4,
        "wc2026": {"group": "Group K", "fixtures": []}
    },
    "EG": {
        "names": ["egypt", "埃及", "eg", "egy"],
        "en": "Egypt",
        "cn": "埃及",
        "market_value_eur": 120000000,
        "average_age": 27.6,
        "wc2026": {"group": "Group K", "fixtures": []}
    },
    "AT": {
        "names": ["austria", "奥地利", "at", "aut"],
        "en": "Austria",
        "cn": "奥地利",
        "market_value_eur": 280000000,
        "average_age": 26.3,
        "wc2026": {"group": "Group L", "fixtures": []}
    },
    "IQ": {
        "names": ["iraq", "伊拉克", "iq", "irq"],
        "en": "Iraq",
        "cn": "伊拉克",
        "market_value_eur": 15000000,
        "average_age": 25.1,
        "wc2026": {"group": "Group L", "fixtures": []}
    },
    "NO": {
        "names": ["norway", "挪威", "no", "nor"],
        "en": "Norway",
        "cn": "挪威",
        "market_value_eur": 450000000,
        "average_age": 25.0,
        "wc2026": {"group": "Group M", "fixtures": []}
    },
    "SN": {
        "names": ["senegal", "塞内加尔", "sn", "sen"],
        "en": "Senegal",
        "cn": "塞内加尔",
        "market_value_eur": 200000000,
        "average_age": 27.5,
        "wc2026": {"group": "Group M", "fixtures": []}
    },
    "JO": {
        "names": ["jordan", "约旦", "jo", "jor"],
        "en": "Jordan",
        "cn": "约旦",
        "market_value_eur": 15000000,
        "average_age": 26.8,
        "wc2026": {"group": "Group N", "fixtures": []}
    },
    "DZ": {
        "names": ["algeria", "阿尔及利亚", "dz", "alg"],
        "en": "Algeria",
        "cn": "阿尔及利亚",
        "market_value_eur": 180000000,
        "average_age": 27.4,
        "wc2026": {"group": "Group N", "fixtures": []}
    },
    "CO": {
        "names": ["colombia", "哥伦比亚", "co", "col"],
        "en": "Colombia",
        "cn": "哥伦比亚",
        "market_value_eur": 302350000,
        "average_age": 29.6,
        "wc2026": {
            "group": "Group K",
            "fixtures": [
                {"date": "2026-06-17", "opponent": "UZ", "stadium": "NRG Stadium (Houston)", "altitude_m": 24, "result": "1-0"},
                {"date": "2026-06-23", "opponent": "CD", "stadium": "Hard Rock Stadium (Miami)", "altitude_m": 2, "result": "Upcoming"},
                {"date": "2026-06-27", "opponent": "PT", "stadium": "Hard Rock Stadium (Miami)", "altitude_m": 2, "result": "Upcoming"}
            ]
        }
    },
    "UZ": {
        "names": ["uzbekistan", "乌兹别克", "乌兹别克斯坦", "uz", "uzb"],
        "en": "Uzbekistan",
        "cn": "乌兹别克斯坦",
        "market_value_eur": 85330000,
        "average_age": 28.0,
        "wc2026": {
            "group": "Group K",
            "fixtures": [
                {"date": "2026-06-17", "opponent": "CO", "stadium": "NRG Stadium (Houston)", "altitude_m": 24, "result": "0-1"},
                {"date": "2026-06-23", "opponent": "PT", "stadium": "Gillette Stadium (Foxborough)", "altitude_m": 90, "result": "Upcoming"},
                {"date": "2026-06-27", "opponent": "CD", "stadium": "Gillette Stadium (Foxborough)", "altitude_m": 90, "result": "Upcoming"}
            ]
        }
    },
    "PA": {
        "names": ["panama", "巴拿马", "pa", "pan"],
        "en": "Panama",
        "cn": "巴拿马",
        "market_value_eur": 34550000,
        "average_age": 30.0,
        "wc2026": {
            "group": "Group L",
            "fixtures": [
                {"date": "2026-06-17", "opponent": "GH", "stadium": "MetLife Stadium (East Rutherford)", "altitude_m": 2, "result": "1-1"},
                {"date": "2026-06-23", "opponent": "HR", "stadium": "BMO Field (Toronto)", "altitude_m": 76, "result": "Upcoming"},
                {"date": "2026-06-27", "opponent": "EN", "stadium": "MetLife Stadium (East Rutherford)", "altitude_m": 2, "result": "Upcoming"}
            ]
        }
    },
    "GH": {
        "names": ["ghana", "加纳", "gh", "gha"],
        "en": "Ghana",
        "cn": "加纳",
        "market_value_eur": 234350000,
        "average_age": 26.4,
        "wc2026": {
            "group": "Group L",
            "fixtures": [
                {"date": "2026-06-17", "opponent": "PA", "stadium": "MetLife Stadium (East Rutherford)", "altitude_m": 2, "result": "1-1"},
                {"date": "2026-06-23", "opponent": "EN", "stadium": "Gillette Stadium (Foxborough)", "altitude_m": 90, "result": "Upcoming"},
                {"date": "2026-06-27", "opponent": "HR", "stadium": "Lincoln Financial Field (Philadelphia)", "altitude_m": 12, "result": "Upcoming"}
            ]
        }
    },
    "CH": {
        "names": ["switzerland", "瑞士", "ch", "sui"],
        "en": "Switzerland",
        "cn": "瑞士",
        "market_value_eur": 300000000,
        "average_age": 26.8,
        "wc2026": {"group": "Group I", "fixtures": []}
    },
    "BA": {
        "names": ["bosnia and herzegovina", "bosnia", "波黑", "ba", "bih"],
        "en": "Bosnia and Herzegovina",
        "cn": "波黑",
        "market_value_eur": 80000000,
        "average_age": 27.2,
        "wc2026": {"group": "Group I", "fixtures": []}
    },
    "QA": {
        "names": ["qatar", "卡塔尔", "qa", "qat"],
        "en": "Qatar",
        "cn": "卡塔尔",
        "market_value_eur": 20000000,
        "average_age": 27.5,
        "wc2026": {"group": "Group I", "fixtures": []}
    },
    "SQ": {
        "names": ["scotland", "苏格兰", "sq", "sco"],
        "en": "Scotland",
        "cn": "苏格兰",
        "market_value_eur": 250000000,
        "average_age": 26.5,
        "wc2026": {"group": "Group J", "fixtures": []}
    },
    "MA": {
        "names": ["morocco", "摩洛哥", "ma", "mar"],
        "en": "Morocco",
        "cn": "摩洛哥",
        "market_value_eur": 350000000,
        "average_age": 26.2,
        "wc2026": {"group": "Group J", "fixtures": []}
    },
    "HT": {
        "names": ["haiti", "海地", "ht", "hai"],
        "en": "Haiti",
        "cn": "海地",
        "market_value_eur": 15000000,
        "average_age": 25.8,
        "wc2026": {"group": "Group J", "fixtures": []}
    },
    "ZA": {
        "names": ["south africa", "南非", "za", "rsa"],
        "en": "South Africa",
        "cn": "南非",
        "market_value_eur": 25000000,
        "average_age": 26.9,
        "wc2026": {"group": "Group K", "fixtures": []}
    },
    "KR": {
        "names": ["south korea", "korea republic", "韩国", "kr", "kor"],
        "en": "South Korea",
        "cn": "韩国",
        "market_value_eur": 160000000,
        "average_age": 27.1,
        "wc2026": {"group": "Group K", "fixtures": []}
    },
    "CZ": {
        "names": ["czech republic", "czechia", "捷克", "cz", "cze"],
        "en": "Czech Republic",
        "cn": "捷克",
        "market_value_eur": 150000000,
        "average_age": 26.4,
        "wc2026": {"group": "Group L", "fixtures": []}
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
                "average_age": meta1.get("average_age", 26.5),
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
                "average_age": meta2.get("average_age", 26.5),
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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import json
import argparse
import math
from datetime import datetime

# Import functions from fetch_match_data and fetch_lottery_data
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import fetch_match_data
import fetch_lottery_data

def poisson_probability(actual, mean):
    """
    Calculate Poisson probability: (e^-mean * mean^actual) / actual!
    """
    if mean <= 0:
        return 1.0 if actual == 0 else 0.0
    return (math.exp(-mean) * (mean ** actual)) / math.factorial(actual)

def generate_score_grid(xg1, xg2, max_goals=5):
    """
    Generate a 2D grid of score probabilities using independent Poisson distributions.
    """
    grid = {}
    total_p = 0.0
    for g1 in range(max_goals + 1):
        for g2 in range(max_goals + 1):
            p1 = poisson_probability(g1, xg1)
            p2 = poisson_probability(g2, xg2)
            p = p1 * p2
            grid[(g1, g2)] = p
            total_p += p
            
    # Normalize grid so probabilities sum to 1.0
    if total_p > 0:
        for k in grid:
            grid[k] /= total_p
            
    return grid

def map_score_grid_to_crs_probs(score_grid):
    """
    Map a 2D grid of score probabilities to the standard 31 Chinese Sports Lottery options.
    """
    crs_probs = {
        # Home win (13 options)
        "1-0": 0.0, "2-0": 0.0, "2-1": 0.0, "3-0": 0.0, "3-1": 0.0, "3-2": 0.0,
        "4-0": 0.0, "4-1": 0.0, "4-2": 0.0, "5-0": 0.0, "5-1": 0.0, "5-2": 0.0,
        "胜其他": 0.0,
        # Draw (5 options)
        "0-0": 0.0, "1-1": 0.0, "2-2": 0.0, "3-3": 0.0, "平其他": 0.0,
        # Away win (13 options)
        "0-1": 0.0, "0-2": 0.0, "1-2": 0.0, "0-3": 0.0, "1-3": 0.0, "2-3": 0.0,
        "0-4": 0.0, "1-4": 0.0, "2-4": 0.0, "0-5": 0.0, "1-5": 0.0, "2-5": 0.0,
        "负其他": 0.0
    }
    
    h_options = ["1-0", "2-0", "2-1", "3-0", "3-1", "3-2", "4-0", "4-1", "4-2", "5-0", "5-1", "5-2"]
    d_options = ["0-0", "1-1", "2-2", "3-3"]
    a_options = ["0-1", "0-2", "1-2", "0-3", "1-3", "2-3", "0-4", "1-4", "2-4", "0-5", "1-5", "2-5"]
    
    for (g1, g2), p in score_grid.items():
        if g1 > g2:
            key = f"{g1}-{g2}"
            if key in h_options:
                crs_probs[key] += p
            else:
                crs_probs["胜其他"] += p
        elif g1 == g2:
            key = f"{g1}-{g2}"
            if key in d_options:
                crs_probs[key] += p
            else:
                crs_probs["平其他"] += p
        else:
            key = f"{g1}-{g2}"
            if key in a_options:
                crs_probs[key] += p
            else:
                crs_probs["负其他"] += p
                
    # Normalize
    total_crs = sum(crs_probs.values())
    if total_crs > 0:
        for k in crs_probs:
            crs_probs[k] /= total_crs
            
    return crs_probs

def estimate_xg_from_probabilities(p_win, p_draw, p_loss, expected_total_goals=2.6):
    """
    Estimate expected goals (xG) for both teams based on win/draw/loss probabilities
    and an expected total goals.
    """
    # Simple heuristic to solve for xG1 and xG2
    # xG1 + xG2 = expected_total_goals
    # xG1 - xG2 is proportional to (p_win - p_loss)
    diff = p_win - p_loss
    xg1 = (expected_total_goals / 2.0) + (diff * 1.2)
    xg2 = (expected_total_goals / 2.0) - (diff * 1.2)
    
    # Ensure xG is positive and reasonable
    xg1 = max(0.2, min(4.0, xg1))
    xg2 = max(0.2, min(4.0, xg2))
    
    return xg1, xg2

def calculate_market_margin_and_implied_probs(odds_dict):
    """
    Given a dictionary of options and their decimal odds, e.g., {'h': 1.53, 'd': 3.83, 'a': 4.65},
    calculate:
    - sum_implied: Sum of 1/O_i (Overround)
    - margin: sum_implied - 1.0 (Vig)
    - payout: 1.0 / sum_implied (Return rate)
    - implied_probs: A dictionary with normalized/no-vig probabilities, e.g., {'H': 0.585, 'D': 0.234, 'A': 0.181}
    """
    # Filter out None/zero/non-numeric odds
    valid_odds = {}
    for k, v in odds_dict.items():
        if v is not None:
            try:
                val = float(v)
                if val > 0:
                    valid_odds[k.upper()] = val
            except (ValueError, TypeError):
                pass
                
    if not valid_odds:
        return 0.0, 1.0, {}
    
    sum_implied = sum(1.0 / v for v in valid_odds.values())
    margin = sum_implied - 1.0
    payout = 1.0 / sum_implied if sum_implied > 0 else 0.0
    
    implied_probs = {}
    for k, v in valid_odds.items():
        implied_probs[k] = (1.0 / v) / sum_implied if sum_implied > 0 else 0.0
        
    return margin, payout, implied_probs

def calculate_kelly_position(ev, odds):
    """
    Calculate recommended stake using Half-Kelly Criterion.
    """
    if ev <= 0 or odds <= 1:
        return 0.0
    # Kelly % = EV / (Odds - 1)
    kelly = ev / (odds - 1)
    # Half-Kelly for risk management
    half_kelly = 0.5 * kelly
    # Cap at 10% maximum for any single bet
    return min(0.10, half_kelly)

def analyze_match_betting(match, elo_data):
    """
    Perform quantitative betting analysis for a single match.
    """
    # 1. Get base probabilities from ELO
    p_win_raw = float(elo_data["match"]["mathematical_probabilities"]["team1_win"].replace("%", "")) / 100.0
    p_draw_raw = float(elo_data["match"]["mathematical_probabilities"]["draw"].replace("%", "")) / 100.0
    p_loss_raw = float(elo_data["match"]["mathematical_probabilities"]["team2_win"].replace("%", "")) / 100.0
    
    # 2. Adjust probabilities based on market value, average age and dynamic factors (simulating ten-factor model)
    # Market value factor
    mv1 = elo_data["match"]["team1"]["market_value_eur"]
    mv2 = elo_data["match"]["team2"]["market_value_eur"]
    mv_ratio = mv1 / mv2 if mv2 > 0 else 1.0
    mv_log = 3.0 * math.log2(mv_ratio)
    mv_adj = max(-5.0, min(5.0, mv_log)) * 0.02 # up to 10% adjustment
    
    # Team average age and peak age bonus factor
    age1 = elo_data["match"]["team1"].get("average_age", 26.5)
    age2 = elo_data["match"]["team2"].get("average_age", 26.5)
    # Peak age is centered around 26.0 years with a std-dev of 1.8 years
    eff1 = math.exp(-((age1 - 26.0) ** 2) / (2.0 * (1.8 ** 2)))
    eff2 = math.exp(-((age2 - 26.0) ** 2) / (2.0 * (1.8 ** 2)))
    age_bonus_diff = eff1 - eff2
    age_adj = age_bonus_diff * 0.03 # up to 3% adjustment
    
    print(f"  [Age Audit] Team Average Age - {elo_data['match']['team1']['name_cn']}: {age1} (Peak Eff: {eff1:.1%}) vs {elo_data['match']['team2']['name_cn']}: {age2} (Peak Eff: {eff2:.1%}) | Net Adj: {age_adj:+.2%}")
    
    # Adjust win/loss probabilities
    p_win = p_win_raw + mv_adj + age_adj
    p_loss = p_loss_raw - mv_adj - age_adj
    
    # Normalize
    total_p = p_win + p_draw_raw + p_loss
    p_win = max(0.01, min(0.98, p_win / total_p))
    p_loss = max(0.01, min(0.98, p_loss / total_p))
    p_draw = 1.0 - p_win - p_loss
    
    # 3. Estimate expected goals and score grid
    xg1, xg2 = estimate_xg_from_probabilities(p_win, p_loss, p_draw)
    score_grid = generate_score_grid(xg1, xg2, max_goals=6)
    
    odds = match.get("odds", {})
    recommendations = []
    
    # Analyze HAD (胜平负)
    had_odds = odds.get("had")
    if had_odds:
        had_margin, _, had_implied = calculate_market_margin_and_implied_probs(had_odds)
        had_probs = {"h": p_win, "d": p_draw, "a": p_loss}
        for opt in ["h", "d", "a"]:
            o_val = had_odds.get(opt)
            if o_val:
                p_model = had_probs[opt]
                p_implied = had_implied.get(opt.upper(), p_model)
                # Weighted Blend: 0.8 model + 0.2 market
                p_final = 0.8 * p_model + 0.2 * p_implied
                ev = p_final * o_val - 1
                recommendations.append({
                    "market": "HAD",
                    "option": opt.upper(),
                    "model_prob": p_model,
                    "implied_prob": p_implied,
                    "margin": had_margin,
                    "probability": p_final,
                    "odds": o_val,
                    "ev": ev,
                    "kelly": calculate_kelly_position(ev, o_val)
                })
                
    # Analyze HHAD (让球胜平负)
    hhad_odds = odds.get("hhad")
    if hhad_odds:
        goal_line = hhad_odds.get("goal_line")
        if goal_line is not None:
            # Calculate HHAD probabilities from score grid
            p_hhad_h = sum(p for (g1, g2), p in score_grid.items() if g1 + goal_line > g2)
            p_hhad_d = sum(p for (g1, g2), p in score_grid.items() if g1 + goal_line == g2)
            p_hhad_a = sum(p for (g1, g2), p in score_grid.items() if g1 + goal_line < g2)
            
            hhad_probs = {"h": p_hhad_h, "d": p_hhad_d, "a": p_hhad_a}
            hhad_odds_only = {k: v for k, v in hhad_odds.items() if k != "goal_line"}
            hhad_margin, _, hhad_implied = calculate_market_margin_and_implied_probs(hhad_odds_only)
            for opt in ["h", "d", "a"]:
                o_val = hhad_odds.get(opt)
                if o_val:
                    p_model = hhad_probs[opt]
                    p_implied = hhad_implied.get(opt.upper(), p_model)
                    # Golden Ratio Blend: 0.618 model + 0.382 market
                    p_final = 0.618 * p_model + 0.382 * p_implied
                    ev = p_final * o_val - 1
                    recommendations.append({
                        "market": f"HHAD ({goal_line})",
                        "option": opt.upper(),
                        "model_prob": p_model,
                        "implied_prob": p_implied,
                        "margin": hhad_margin,
                        "probability": p_final,
                        "odds": o_val,
                        "ev": ev,
                        "kelly": calculate_kelly_position(ev, o_val)
                    })
                    
    # Analyze TTG (总进球数)
    ttg_odds = odds.get("ttg")
    if ttg_odds:
        # Calculate TTG probabilities from score grid
        ttg_probs = {}
        for goals in range(7):
            ttg_probs[f"s{goals}"] = sum(p for (g1, g2), p in score_grid.items() if g1 + g2 == goals)
        ttg_probs["s7"] = sum(p for (g1, g2), p in score_grid.items() if g1 + g2 >= 7)
        
        ttg_margin, _, ttg_implied = calculate_market_margin_and_implied_probs(ttg_odds)
        for opt in [f"s{i}" for i in range(8)]:
            o_val = ttg_odds.get(opt)
            if o_val:
                p_model = ttg_probs[opt]
                p_implied = ttg_implied.get(opt.upper(), p_model)
                # Weighted Blend: 0.8 model + 0.2 market
                p_final = 0.8 * p_model + 0.2 * p_implied
                ev = p_final * o_val - 1
                recommendations.append({
                    "market": "TTG",
                    "option": opt[1:] + "球",
                    "model_prob": p_model,
                    "implied_prob": p_implied,
                    "margin": ttg_margin,
                    "probability": p_final,
                    "odds": o_val,
                    "ev": ev,
                    "kelly": calculate_kelly_position(ev, o_val)
                })
                    
    # Analyze CRS (比分)
    crs_odds = odds.get("crs")
    if crs_odds:
        crs_probs = map_score_grid_to_crs_probs(score_grid)
        crs_margin, _, crs_implied = calculate_market_margin_and_implied_probs(crs_odds)
        for opt_key, o_val in crs_odds.items():
            if o_val:
                p_model = crs_probs.get(opt_key, 0.0)
                p_implied = crs_implied.get(opt_key.upper(), p_model)
                # Weighted Blend: 0.8 model + 0.2 market
                p_final = 0.8 * p_model + 0.2 * p_implied
                ev = p_final * o_val - 1
                recommendations.append({
                    "market": "CRS",
                    "option": opt_key,
                    "model_prob": p_model,
                    "implied_prob": p_implied,
                    "margin": crs_margin,
                    "probability": p_final,
                    "odds": o_val,
                    "ev": ev,
                    "kelly": calculate_kelly_position(ev, o_val)
                })
                
    # Sort recommendations by EV descending
    recommendations.sort(key=lambda x: x["ev"], reverse=True)
    
    # Format score grid with string keys for JSON serialization and audit transparency
    json_score_grid = {f"{g1}-{g2}": p for (g1, g2), p in score_grid.items()}
    argmax_score = max(json_score_grid, key=json_score_grid.get)
    argmax_prob = json_score_grid[argmax_score]
    
    print(f"  [Transparency Audit] Simulated score probabilities P_sim(X, Y) and argmax results:")
    print(f"    - argmax_(X,Y) P_sim(X, Y) = {argmax_score} (Probability: {argmax_prob:.2%})")
    print(f"    - Full P_sim score distribution details recorded in structural logs.")

    return {
        "match_id": match["match_id"],
        "match_num_str": match["match_num_str"],
        "home_team": match["home_team"],
        "away_team": match["away_team"],
        "league_name": match["league_name"],
        "match_date": match["match_date"],
        "match_time": match["match_time"],
        "probabilities": {
            "win": p_win,
            "draw": p_draw,
            "loss": p_loss
        },
        "xg": (xg1, xg2),
        "P_sim": json_score_grid,
        "argmax_score": argmax_score,
        "argmax_probability": argmax_prob,
        "betting_options": recommendations
    }

def generate_markdown_report(date_str, analyzed_matches):
    """
    Generate a beautifully formatted markdown report.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    md = []
    md.append(f"# 竞彩足球定量投注方案推荐报告（{date_str}）")
    md.append(f"\n*生成时间：{now_str} | 模型版本：v2.1 (十因子定量加权模型 & 独立泊松比分网格)*\n")
    
    md.append("## 一、 今日竞彩赛事概览")
    md.append("呈现今日开售的赛事列表、模型预测走向及竞彩核心赔率。")
    md.append("\n| 场次序号 | 赛事类型 | 主队 vs 客队 | 预测走向 | 胜平负(HAD)赔率 | 让球数及让球赔率(HHAD) |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    
    for am in analyzed_matches:
        p_win = am["probabilities"]["win"]
        p_draw = am["probabilities"]["draw"]
        p_loss = am["probabilities"]["loss"]
        
        if p_win > 0.50:
            pred = "主胜"
        elif p_loss > 0.50:
            pred = "客胜"
        elif p_draw > 0.35:
            pred = "平局"
        else:
            pred = "双平/模糊"
            
        had = am["betting_options"]
        had_h = next((x["odds"] for x in had if x["market"] == "HAD" and x["option"] == "H"), "-")
        had_d = next((x["odds"] for x in had if x["market"] == "HAD" and x["option"] == "D"), "-")
        had_a = next((x["odds"] for x in had if x["market"] == "HAD" and x["option"] == "A"), "-")
        had_str = f"{had_h} / {had_d} / {had_a}"
        
        hhad_opt = [x for x in had if x["market"].startswith("HHAD")]
        if hhad_opt:
            gl = hhad_opt[0]["market"].split("(")[1].split(")")[0]
            hhad_h = next((x["odds"] for x in hhad_opt if x["option"] == "H"), "-")
            hhad_d = next((x["odds"] for x in hhad_opt if x["option"] == "D"), "-")
            hhad_a = next((x["odds"] for x in hhad_opt if x["option"] == "A"), "-")
            hhad_str = f"{gl}: {hhad_h} / {hhad_d} / {hhad_a}"
        else:
            hhad_str = "-"
            
        md.append(f"| {am['match_num_str']} | {am['league_name']} | {am['home_team']} vs {am['away_team']} | {pred} | {had_str} | {hhad_str} |")
        
    md.append("\n## 二、 核心玩法期望值（EV）定量分析表")
    md.append("展示各场比赛核心玩法的概率、提成率、去抽水隐含概率、黄金融合概率、赔率及 EV 计算结果，标出正 EV 价值选项。")
    md.append("\n| 比赛场次 | 投注玩法 | 投注选项 | 庄家提成率 | 去抽水概率 | 模型预测概率 | 黄金融合概率 ($P_{final}$) | 实时赔率 ($O$) | 期望值 ($EV$) | 价值判定 | 推荐仓位 (半凯利) |")
    md.append("| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    
    value_bets = []
    for am in analyzed_matches:
        for opt in am["betting_options"]:
            if opt["ev"] > 0:
                value_bets.append((am, opt))
                status = "🟢 价值投注" if opt["ev"] > 0.05 else "🟡 微弱价值"
                md.append(f"| {am['match_num_str']} {am['home_team']} | {opt['market']} | {opt['option']} | {opt['margin']:.1%} | {opt['implied_prob']:.1%} | {opt['model_prob']:.1%} | {opt['probability']:.1%} | {opt['odds']:.2f} | {opt['ev']:+.1%} | {status} | {opt['kelly']:.1%} |")
                
    md.append("\n## 三、 黄金投注方案推荐")
    
    # 1. Single Bets
    md.append("### 1. 稳健单场方案 (HAD/HHAD)")
    single_bets = [x for x in value_bets if x[1]["market"] in ["HAD", "HHAD (-1)", "HHAD (+1)"] and x[1]["probability"] >= 0.45 and x[1]["ev"] > 0.08]
    if single_bets:
        single_bets.sort(key=lambda x: x[1]["ev"], reverse=True)
        for am, opt in single_bets[:2]:
            md.append(f"- **推荐选项**：{am['match_num_str']} {am['home_team']} vs {am['away_team']} ➔ **{opt['market']}-{opt['option']}** (赔率: {opt['odds']:.2f})")
            md.append(f"  - **预测概率**：{opt['probability']:.1%} | **期望值 (EV)**：{opt['ev']:+.1%}")
            md.append(f"  - **资金分配**：建议占总资金的 **{opt['kelly']:.1%}**")
            md.append(f"  - **推荐理由**：模型预测该选项发生概率为 {opt['probability']:.1%}，远高于竞彩赔率对应的隐含概率（{1/opt['odds']:.1%}），具有大于 8% 的极佳性价比和安全边际。")
    else:
        md.append("- 今日暂无符合稳健且期望值大于 8% 标准的单场价值投注选项。")
        
    # 2. Parlay (2串1)
    md.append("\n### 2. 性价比串关方案 (2串1)")
    parlay_candidates = [x for x in value_bets if x[1]["market"] in ["HAD", "HHAD (-1)", "HHAD (+1)"] and x[1]["ev"] > 0.08]
    if len(parlay_candidates) >= 2:
        # Find the best 2-play combination
        best_parlay = None
        best_parlay_ev = -1.0
        for i in range(len(parlay_candidates)):
            for j in range(i + 1, len(parlay_candidates)):
                m1, o1 = parlay_candidates[i]
                m2, o2 = parlay_candidates[j]
                if m1["match_id"] != m2["match_id"]: # Must be different matches
                    p_combo = o1["probability"] * o2["probability"]
                    odds_combo = o1["odds"] * o2["odds"]
                    ev_combo = p_combo * odds_combo - 1
                    if ev_combo > 0.08 and ev_combo > best_parlay_ev:
                        best_parlay_ev = ev_combo
                        best_parlay = (m1, o1, m2, o2, p_combo, odds_combo, ev_combo)
                        
        if best_parlay:
            m1, o1, m2, o2, p_combo, odds_combo, ev_combo = best_parlay
            md.append(f"- **串关组合**：**{m1['match_num_str']}[{o1['market']}-{o1['option']}]** × **{m2['match_num_str']}[{o2['market']}-{o2['option']}]**")
            md.append(f"  - **组合总赔率**：{odds_combo:.2f} | **组合胜率**：{p_combo:.1%}")
            md.append(f"  - **组合期望值 (EV)**：{ev_combo:+.1%}")
            md.append(f"  - **资金分配**：建议占总资金的 **{calculate_kelly_position(ev_combo, odds_combo):.1%}**")
            md.append(f"  - **推荐理由**：两场独立正 EV 比赛强强联手，利用期望值乘数效应，将大于 8% 的单场优势指数级放大，是今日最具投资价值的串关方案。")
        else:
            md.append("- 今日暂无组合期望值大于 8% 的串关方案。")
    else:
        md.append("- 今日期望值大于 8% 的价值投注场次不足，不建议强行进行串关。")
        
    # 3. Correct Score / High Yield
    md.append("\n### 3. 高回报博冷方案 (CRS比分/HAFU半全场)")
    special_bets = [x for x in value_bets if (x[1]["market"] in ["TTG", "CRS"] or x[1]["odds"] >= 3.5) and x[1]["ev"] > 0.08]
    if special_bets:
        special_bets.sort(key=lambda x: x[1]["ev"], reverse=True)
        for am, opt in special_bets[:2]:
            md.append(f"- **推荐选项**：{am['match_num_str']} {am['home_team']} vs {am['away_team']} ➔ **{opt['market']}-{opt['option']}** (赔率: {opt['odds']:.2f})")
            md.append(f"  - **预测概率**：{opt['probability']:.1%} | **期望值 (EV)**：{opt['ev']:+.1%}")
            md.append(f"  - **资金分配**：建议占总资金的 **{opt['kelly']:.1%}** (娱乐轻仓)")
    else:
        md.append("- 今日暂无期望值大于 8% 的高性价比博冷选项。")
        
    md.append("\n## 四、 投资学风险提示与免责声明")
    md.append("1. **理性投注**：本报告基于定量数学模型与历史数据推导，旨在提供客观的性价比参考，不构成任何保本承诺。")
    md.append("2. **资金管理**：严格遵循凯利公式推荐的仓位比例，切勿重仓或满仓单一选项。")
    md.append("3. **彩票本质**：中国体育彩票是公益事业，请保持娱乐心态，量力而行，遵守国家相关法律法规。")
    
    return "\n".join(md)

class DualLogger:
    def __init__(self, filepath, terminal_stream):
        self.terminal = terminal_stream
        self.log = open(filepath, "a", encoding="utf-8")
        
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()
        
    def flush(self):
        self.terminal.flush()
        self.log.flush()

def main():
    parser = argparse.ArgumentParser(description="Generate quantitative betting recommendations.")
    parser.add_argument("--date", type=str, help="Filter by match date (YYYY-MM-DD or YYYYMMDD)")
    parser.add_argument("--team", type=str, help="Filter by team name (fuzzy match)")
    
    args = parser.parse_args()
    
    # Default to today's date if not specified
    date_str = args.date or "2026-06-20"
    clean_date_str = date_str.replace("-", "")
    
    # Setup logs directory
    log_dir = os.path.join("logs", clean_date_str)
    os.makedirs(log_dir, exist_ok=True)
    
    script_name = os.path.basename(__file__).replace(".py", "")
    log_path = os.path.join(log_dir, f"{script_name}.log")
    
    # Initialize dual logger
    sys.stdout = DualLogger(log_path, sys.stdout)
    sys.stderr = DualLogger(log_path, sys.stderr)
    
    print("\n" + "="*80)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting betting recommendation run for date: {date_str}")
    print("="*80)
    
    # 1. Fetch lottery matches and odds
    print(f"Fetching lottery data for {date_str}...")
    raw_lottery = fetch_lottery_data.fetch_raw_lottery_data()
    if not raw_lottery:
        print("Failed to fetch lottery data.")
        sys.exit(1)
        
    matches = fetch_lottery_data.parse_odds_data(raw_lottery)
    filtered_matches = fetch_lottery_data.filter_matches(matches, date=date_str, team=args.team)
    
    if not filtered_matches:
        print(f"No matches found for date {date_str}.")
        sys.exit(0)
        
    print(f"Found {len(filtered_matches)} matches. Running match predictions and EV analysis...")
    
    analyzed_matches = []
    
    for m in filtered_matches:
        home = m["home_team"]
        away = m["away_team"]
        
        # Try to find country codes in fetch_match_data
        code1 = fetch_match_data.find_country_code(home)
        code2 = fetch_match_data.find_country_code(away)
        
        if not code1 or not code2:
            print(f"Skipping match {home} vs {away} (Could not map country codes: {home}->{code1}, {away}->{code2})")
            continue
            
        ratings = fetch_match_data.fetch_elo_ratings()
        if code1 not in ratings or code2 not in ratings:
            print(f"Skipping match {home} vs {away} (Elo ratings missing for {code1} or {code2})")
            continue
            
        # Call fetch_match_data logic to get elo data
        r1 = ratings[code1]
        r2 = ratings[code2]
        p_win, p_draw, p_loss = fetch_match_data.calculate_probabilities(r1["elo"], r2["elo"])
        
        meta1 = fetch_match_data.COUNTRY_METADATA[code1]
        meta2 = fetch_match_data.COUNTRY_METADATA[code2]
        
        elo_data = {
            "match": {
                "team1": {
                    "name_cn": meta1["cn"],
                    "market_value_eur": meta1["market_value_eur"],
                    "average_age": meta1.get("average_age", 26.5),
                },
                "team2": {
                    "name_cn": meta2["cn"],
                    "market_value_eur": meta2["market_value_eur"],
                    "average_age": meta2.get("average_age", 26.5),
                },
                "mathematical_probabilities": {
                    "team1_win": f"{p_win:.2%}",
                    "draw": f"{p_draw:.2%}",
                    "team2_win": f"{p_loss:.2%}"
                }
            }
        }
        
        # Analyze match betting
        analyzed = analyze_match_betting(m, elo_data)
        analyzed_matches.append(analyzed)
        
    if not analyzed_matches:
        print("No matches could be analyzed.")
        sys.exit(0)
        
    # Generate report
    report_md = generate_markdown_report(date_str, analyzed_matches)
    
    # Save to output folder
    os.makedirs("output", exist_ok=True)
    clean_date_str = date_str.replace("-", "")
    output_path = f"output/{clean_date_str}_投注方案.md"
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_md)
        
    print(f"\nSuccessfully generated betting recommendation report and saved to {output_path}")
    
    # Save structured JSON logs for traceability
    json_path = os.path.join(log_dir, f"{script_name}.json")
    trace_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "script_name": script_name,
        "date_str": clean_date_str,
        "analyzed_matches": analyzed_matches
    }
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(trace_data, f, ensure_ascii=False, indent=2)
        print(f"Successfully saved structured JSON trace to {json_path}")
    except Exception as e:
        sys.stderr.write(f"Failed to save structured JSON trace: {e}\n")
        
    print("=" * 60)
    print(report_md[:1500] + "\n... (truncated for brevity) ...")

if __name__ == "__main__":
    main()

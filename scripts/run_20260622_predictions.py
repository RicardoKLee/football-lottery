#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import random
import json

def sample_poisson(lam):
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= random.random()
    return k - 1

def sample_normal(mu, sigma):
    u1 = random.random()
    u2 = random.random()
    while u1 == 0:
        u1 = random.random()
    z0 = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    return mu + z0 * sigma

def run_monte_carlo_simulation(
    home_name, away_name,
    base_lambda, base_mu,
    referee_strictness=4.2,
    ref_penalty_rate=0.25,
    home_fouls=12.0,
    away_fouls=12.0,
    home_dangerous_attacks=45.0,
    away_dangerous_attacks=45.0,
    num_samples=10000,
    volatility=0.15
):
    p_red_home = min(0.15, (referee_strictness / 4.5) * (home_fouls / 12.0) * 0.06)
    p_red_away = min(0.15, (referee_strictness / 4.5) * (away_fouls / 12.0) * 0.06)
    
    total_dangerous = home_dangerous_attacks + away_dangerous_attacks
    home_box_share = home_dangerous_attacks / total_dangerous if total_dangerous > 0 else 0.5
    
    p_penalty = min(0.40, ref_penalty_rate * (total_dangerous / 75.0) * 0.8)
    
    expected_pen_home = p_penalty * home_box_share * 0.76
    expected_pen_away = p_penalty * (1.0 - home_box_share) * 0.76
    
    open_lambda = max(0.1, base_lambda - expected_pen_home)
    open_mu = max(0.1, base_mu - expected_pen_away)
    
    home_wins = 0
    draws = 0
    away_wins = 0
    
    home_goals_sum = 0
    away_goals_sum = 0
    
    score_frequencies = {}
    
    red_card_events = {home_name: 0, away_name: 0}
    penalty_events = {home_name: 0, away_name: 0}
    
    for _ in range(num_samples):
        epsilon_h = sample_normal(0, volatility)
        epsilon_a = sample_normal(0, volatility)
        
        lam_j = open_lambda * math.exp(epsilon_h)
        mu_j = open_mu * math.exp(epsilon_a)
        
        rc_home = random.random() < p_red_home
        rc_away = random.random() < p_red_away
        
        if rc_home:
            red_card_events[home_name] += 1
            mu_j *= 1.30
            lam_j *= 0.90
            
        if rc_away:
            red_card_events[away_name] += 1
            lam_j *= 1.30
            mu_j *= 0.90
            
        g_home = sample_poisson(lam_j)
        g_away = sample_poisson(mu_j)
        
        has_penalty = random.random() < p_penalty
        if has_penalty:
            is_home_pen = random.random() < home_box_share
            is_converted = random.random() < 0.76
            
            if is_converted:
                if is_home_pen:
                    g_home += 1
                    penalty_events[home_name] += 1
                else:
                    g_away += 1
                    penalty_events[away_name] += 1
                    
        score_tuple = (g_home, g_away)
        score_frequencies[score_tuple] = score_frequencies.get(score_tuple, 0) + 1
        
        home_goals_sum += g_home
        away_goals_sum += g_away
        
        if g_home > g_away:
            home_wins += 1
        elif g_home < g_away:
            away_wins += 1
        else:
            draws += 1
            
    p_home_win = home_wins / num_samples
    p_draw = draws / num_samples
    p_away_win = away_wins / num_samples
    
    sim_xg_home = home_goals_sum / num_samples
    sim_xg_away = away_goals_sum / num_samples
    
    sorted_scores = sorted(score_frequencies.items(), key=lambda x: x[1], reverse=True)
    top_scores = [(score, freq / num_samples) for score, freq in sorted_scores[:4]]
    
    return {
        "home": home_name,
        "away": away_name,
        "probabilities": {
            "win": p_home_win,
            "draw": p_draw,
            "loss": p_away_win
        },
        "sim_xg": (sim_xg_home, sim_xg_away),
        "top_scores": top_scores,
        "event_stats": {
            "red_cards": {
                home_name: red_card_events[home_name] / num_samples,
                away_name: red_card_events[away_name] / num_samples
            },
            "penalties_scored": {
                home_name: penalty_events[home_name] / num_samples,
                away_name: penalty_events[away_name] / num_samples
            }
        }
    }

def print_report(res):
    print(f"Match: {res['home']} vs {res['away']}")
    print(f"  Simulated xG: {res['sim_xg'][0]:.3f} - {res['sim_xg'][1]:.3f}")
    print(f"  HAD Probabilities: H={res['probabilities']['win']:.2%} D={res['probabilities']['draw']:.2%} A={res['probabilities']['loss']:.2%}")
    print(f"  Top Scores:")
    for i, (score, prob) in enumerate(res["top_scores"]):
        print(f"    {i+1}: {score[0]}-{score[1]} ({prob:.2%})")
    print("-" * 50)

if __name__ == "__main__":
    random.seed(42)
    
    # 1. Argentina vs Austria
    # S = +3.04. txG = 2.4. base_lambda = 1.656, base_mu = 0.744
    print_report(run_monte_carlo_simulation(
        home_name="阿根廷", away_name="奥地利",
        base_lambda=1.656, base_mu=0.744,
        referee_strictness=4.2, ref_penalty_rate=0.25,
        home_fouls=11.0, away_fouls=13.5,
        home_dangerous_attacks=55.0, away_dangerous_attacks=35.0
    ))
    
    # 2. France vs Iraq
    # S = +5.145. txG = 2.8. base_lambda = 2.172, base_mu = 0.628
    print_report(run_monte_carlo_simulation(
        home_name="法国", away_name="伊拉克",
        base_lambda=2.172, base_mu=0.628,
        referee_strictness=4.0, ref_penalty_rate=0.22,
        home_fouls=10.0, away_fouls=14.5,
        home_dangerous_attacks=68.0, away_dangerous_attacks=22.0
    ))
    
    # 3. Norway vs Senegal
    # S = +0.75. txG = 2.4. base_lambda = 1.3125, base_mu = 1.0875
    print_report(run_monte_carlo_simulation(
        home_name="挪威", away_name="塞内加尔",
        base_lambda=1.3125, base_mu=1.0875,
        referee_strictness=4.3, ref_penalty_rate=0.26,
        home_fouls=12.0, away_fouls=14.0,
        home_dangerous_attacks=52.0, away_dangerous_attacks=40.0
    ))
    
    # 4. Jordan vs Algeria
    # S = -2.265. txG = 2.2. base_lambda = 0.760, base_mu = 1.440
    print_report(run_monte_carlo_simulation(
        home_name="约旦", away_name="阿尔及利亚",
        base_lambda=0.760, base_mu=1.440,
        referee_strictness=4.1, ref_penalty_rate=0.24,
        home_fouls=13.5, away_fouls=11.0,
        home_dangerous_attacks=32.0, away_dangerous_attacks=50.0
    ))

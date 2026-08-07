#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import random
import sys

def sample_poisson(lam):
    """
    Generate a random sample from a Poisson distribution with parameter lam using Knuth's algorithm.
    """
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
    """
    Generate a random sample from a Normal distribution using Box-Muller transform.
    """
    u1 = random.random()
    u2 = random.random()
    # Avoid log(0)
    while u1 == 0:
        u1 = random.random()
    z0 = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    return mu + z0 * sigma

def run_monte_carlo_simulation(
    home_name, away_name,
    base_lambda, base_mu,
    referee_strictness=4.5,  # Average yellow cards per match
    ref_penalty_rate=0.25,   # Penalties awarded per match
    home_fouls=12.0,         # Home team average fouls
    away_fouls=15.0,         # Away team average fouls
    home_dangerous_attacks=45.0,
    away_dangerous_attacks=30.0,
    num_samples=10000,
    volatility=0.15          # Physical luck white noise volatility (sigma)
):
    """
    Run a stochastic Monte Carlo simulation with referee discipline, penalty, and red card perturbations.
    """
    # 1. Map probabilities for red cards and penalties
    # Base probability of a red card is influenced by referee strictness and team foul density
    # World Cup baseline red card rate is ~0.12 per match.
    p_red_home = min(0.15, (referee_strictness / 4.5) * (home_fouls / 12.0) * 0.06)
    p_red_away = min(0.15, (referee_strictness / 4.5) * (away_fouls / 12.0) * 0.06)
    
    # Base probability of a penalty awarded in the match
    total_dangerous = home_dangerous_attacks + away_dangerous_attacks
    home_box_share = home_dangerous_attacks / total_dangerous if total_dangerous > 0 else 0.5
    
    p_penalty = min(0.40, ref_penalty_rate * (total_dangerous / 75.0) * 0.8)
    
    # Mathematical correction: Subtract expected penalty goals from base lambda/mu to avoid double-counting
    # since base_lambda and base_mu represent the overall goal expectations (inclusive of historical penalties).
    expected_pen_home = p_penalty * home_box_share * 0.76
    expected_pen_away = p_penalty * (1.0 - home_box_share) * 0.76
    
    open_lambda = max(0.1, base_lambda - expected_pen_home)
    open_mu = max(0.1, base_mu - expected_pen_away)
    
    # Simulation counters
    home_wins = 0
    draws = 0
    away_wins = 0
    
    home_goals_sum = 0
    away_goals_sum = 0
    
    score_frequencies = {}
    
    # Track event occurrences in simulation for statistics
    red_card_events = {home_name: 0, away_name: 0}
    penalty_events = {home_name: 0, away_name: 0}
    
    for _ in range(num_samples):
        # a. Sample physical white noise (luck/volatility) affecting expected goals log-normally
        epsilon_h = sample_normal(0, volatility)
        epsilon_a = sample_normal(0, volatility)
        
        lam_j = open_lambda * math.exp(epsilon_h)
        mu_j = open_mu * math.exp(epsilon_a)
        
        # b. Sample Red Cards (Bernoulli trial)
        rc_home = random.random() < p_red_home
        rc_away = random.random() < p_red_away
        
        if rc_home:
            red_card_events[home_name] += 1
            # Team 1 down to 10 men -> Team 2 expected goals spikes (e.g. defense collapses by 30%)
            mu_j *= 1.30
            # Team 1 offense also degrades slightly (e.g. by 10%)
            lam_j *= 0.90
            
        if rc_away:
            red_card_events[away_name] += 1
            # Team 2 down to 10 men -> Team 1 expected goals spikes by 30%
            lam_j *= 1.30
            # Team 2 offense degrades slightly by 10%
            mu_j *= 0.90
            
        # c. Sample Open Play Goals from Poisson
        g_home = sample_poisson(lam_j)
        g_away = sample_poisson(mu_j)
        
        # d. Sample Penalty Kick occurrences (Bernoulli trial)
        has_penalty = random.random() < p_penalty
        if has_penalty:
            # Allocate penalty based on box dominance
            is_home_pen = random.random() < home_box_share
            # Standard conversion rate for penalties is ~76%
            is_converted = random.random() < 0.76
            
            if is_converted:
                if is_home_pen:
                    g_home += 1
                    penalty_events[home_name] += 1
                else:
                    g_away += 1
                    penalty_events[away_name] += 1
                    
        # e. Record score
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
            
    # Calculate statistics
    p_home_win = home_wins / num_samples
    p_draw = draws / num_samples
    p_away_win = away_wins / num_samples
    
    sim_xg_home = home_goals_sum / num_samples
    sim_xg_away = away_goals_sum / num_samples
    
    # Sort scores by frequency
    sorted_scores = sorted(score_frequencies.items(), key=lambda x: x[1], reverse=True)
    top_scores = [(score, freq / num_samples) for score, freq in sorted_scores[:4]]
    
    # Return comprehensive analysis
    return {
        "home": home_name,
        "away": away_name,
        "parameters": {
            "base_lambda": base_lambda,
            "base_mu": base_mu,
            "p_red_home": p_red_home,
            "p_red_away": p_red_away,
            "p_penalty": p_penalty,
            "volatility": volatility
        },
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
    print("=" * 70)
    print(f" 随机噪声扰动蒙特卡洛预测报告: {res['home']} vs {res['away']}")
    print("=" * 70)
    print(f" 模拟采样次数: 10,000 次 | 物理底噪 Volatility (σ): {res['parameters']['volatility']:.1%}")
    print("-" * 70)
    print(f"【输入基准参数】")
    print(f" - 主队基准期望进球 (Base λ): {res['parameters']['base_lambda']:.3f}")
    print(f" - 客队基准期望进球 (Base μ): {res['parameters']['base_mu']:.3f}")
    print(f" - 模拟红牌概率: 主队 {res['parameters']['p_red_home']:.2%} | 客队 {res['parameters']['p_red_away']:.2%}")
    print(f" - 模拟点球概率 (单场至少判罚一球): {res['parameters']['p_penalty']:.2%}")
    print("-" * 70)
    print(f"【扰动后模拟输出结果】")
    print(f" - 模拟期望进球 (Simulated xG): {res['home']} {res['sim_xg'][0]:.3f} vs {res['sim_xg'][1]:.3f} {res['away']}")
    print(f" - 模拟胜平负概率:")
    print(f"   * {res['home']} 独赢 (HAD-H): {res['probabilities']['win']:.2%}")
    print(f"   * 双方战平   (HAD-D): {res['probabilities']['draw']:.2%}")
    print(f"   * {res['away']} 独赢 (HAD-A): {res['probabilities']['loss']:.2%}")
    print("-" * 70)
    print(f"【高频精确比分推荐 (Top 4)】")
    for i, (score, prob) in enumerate(res["top_scores"]):
        print(f"   第 {i+1} 推荐: {score[0]}-{score[1]} | 模拟发生概率: {prob:.2%}")
    print("-" * 70)
    print(f"【模拟关键事件触发率】")
    print(f" - 实际触发红牌率: 主队 {res['event_stats']['red_cards'][res['home']]:.2%} | 客队 {res['event_stats']['red_cards'][res['away']]:.2%}")
    print(f" - 实际点球罚入率: 主队 {res['event_stats']['penalties_scored'][res['home']]:.2%} | 客队 {res['event_stats']['penalties_scored'][res['away']]:.2%}")
    print("=" * 70)
    print()

if __name__ == "__main__":
    random.seed(42)  # Set seed for reproducible results
    
    # Match 1: Portugal vs Spain (葡萄牙 vs 西班牙)
    # Total加权得分 S = -0.60. Expected total goals = 2.2
    # Base lambda = (2.2 + 0.3 * -0.60) / 2 = 1.01
    # Base mu = (2.2 - 0.3 * -0.60) / 2 = 1.19
    # Referee: Anthony Taylor (strictness=4.5 cards, penalty_rate=0.25)
    # Team discipline: Portugal fouls=11.0, Spain fouls=9.0
    portugal_vs_spain = run_monte_carlo_simulation(
        home_name="葡萄牙", away_name="西班牙",
        base_lambda=1.01, base_mu=1.19,
        referee_strictness=4.5, ref_penalty_rate=0.25,
        home_fouls=11.0, away_fouls=9.0,
        home_dangerous_attacks=45.0, away_dangerous_attacks=50.0,
        volatility=0.15
    )
    print_report(portugal_vs_spain)
    
    # Match 2: USA vs Belgium (美国 vs 比利时)
    # Total加权得分 S = -0.54. Expected total goals = 2.4
    # Base lambda = (2.4 + 0.3 * -0.54) / 2 = 1.12
    # Base mu = (2.4 - 0.3 * -0.54) / 2 = 1.28
    # Referee: Adham Makhadmeh (strictness=4.8 cards, penalty_rate=0.28)
    # Team discipline: USA fouls=13.0, Belgium fouls=11.0
    usa_vs_belgium = run_monte_carlo_simulation(
        home_name="美国", away_name="比利时",
        base_lambda=1.12, base_mu=1.28,
        referee_strictness=4.8, ref_penalty_rate=0.28,
        home_fouls=13.0, away_fouls=11.0,
        home_dangerous_attacks=48.0, away_dangerous_attacks=42.0,
        volatility=0.15
    )
    print_report(usa_vs_belgium)

#!/usr/bin/env python3

import argparse
import json
import math
import random
import sys
from collections import Counter


def sample_poisson(expected_goals, rng=None):
    if expected_goals <= 0:
        return 0
    rng = rng or random
    threshold = math.exp(-expected_goals)
    product = 1.0
    count = 0
    while product > threshold:
        count += 1
        product *= rng.random()
    return count - 1


def sample_normal(mean, standard_deviation, rng=None):
    rng = rng or random
    return float(rng.gauss(mean, standard_deviation))


def run_monte_carlo_simulation(
    home_name,
    away_name,
    base_lambda,
    base_mu,
    num_samples=10000,
    volatility=0.10,
    seed=None,
):
    if base_lambda <= 0 or base_mu <= 0:
        raise ValueError("Expected goals must be positive")
    if num_samples <= 0:
        raise ValueError("num_samples must be positive")
    if volatility < 0:
        raise ValueError("volatility cannot be negative")
    rng = random.Random(seed)
    score_counts = Counter()
    home_wins = draws = away_wins = 0
    lognormal_mean = -(volatility**2) / 2.0
    for _ in range(num_samples):
        home_rate = base_lambda * math.exp(rng.gauss(lognormal_mean, volatility))
        away_rate = base_mu * math.exp(rng.gauss(lognormal_mean, volatility))
        home_goals = sample_poisson(home_rate, rng)
        away_goals = sample_poisson(away_rate, rng)
        score_counts[f"{home_goals}-{away_goals}"] += 1
        if home_goals > away_goals:
            home_wins += 1
        elif home_goals == away_goals:
            draws += 1
        else:
            away_wins += 1
    score_distribution = {
        score: count / num_samples for score, count in sorted(score_counts.items())
    }
    return {
        "home": home_name,
        "away": away_name,
        "expected_goals": {"home": base_lambda, "away": base_mu},
        "probabilities": {
            "win": home_wins / num_samples,
            "draw": draws / num_samples,
            "loss": away_wins / num_samples,
        },
        "score_distribution": score_distribution,
        "parameters": {
            "samples": num_samples,
            "volatility": volatility,
            "seed": seed,
            "event_adjustments": "none_without_observed_inputs",
        },
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Propagate club expected-goal uncertainty with a reproducible Monte Carlo run."
    )
    parser.add_argument("--home", required=True)
    parser.add_argument("--away", required=True)
    parser.add_argument("--home-xg", required=True, type=float)
    parser.add_argument("--away-xg", required=True, type=float)
    parser.add_argument("--samples", type=int, default=10000)
    parser.add_argument("--volatility", type=float, default=0.10)
    parser.add_argument("--seed", type=int)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        result = run_monte_carlo_simulation(
            args.home,
            args.away,
            args.home_xg,
            args.away_xg,
            num_samples=args.samples,
            volatility=args.volatility,
            seed=args.seed,
        )
    except ValueError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

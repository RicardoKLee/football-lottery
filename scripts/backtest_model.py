#!/usr/bin/env python3

import argparse
import json
import math
import sys
from dataclasses import asdict
from datetime import timedelta

from contracts import parse_datetime, utc_iso, write_json
from fetch_match_data import load_history_file
from model_core import (
    COMPETITION_NAMES,
    ModelParameters,
    build_elo_ratings,
    create_prediction,
    expected_home_result,
    finished_matches_before,
)

OUTCOMES = ("H", "D", "A")


def _actual_outcome(match):
    if match["home_score"] > match["away_score"]:
        return "H"
    if match["home_score"] == match["away_score"]:
        return "D"
    return "A"


def _simple_elo_probabilities(training_matches, target, parameters):
    target_context = target.get("context") if isinstance(target.get("context"), dict) else {}
    advantage = 0.0 if target_context.get("venue") == "neutral" else parameters.home_advantage_elo
    ratings, _ = build_elo_ratings(
        training_matches,
        home_advantage_elo=parameters.home_advantage_elo,
        k_factor=parameters.elo_k_factor,
        initial_elo=parameters.initial_elo,
    )
    home_id = target["home_team"]["team_id"]
    away_id = target["away_team"]["team_id"]
    home_expectation = expected_home_result(
        ratings.get(home_id, parameters.initial_elo),
        ratings.get(away_id, parameters.initial_elo),
        advantage,
    )
    draws = sum(match["home_score"] == match["away_score"] for match in training_matches)
    draw_probability = (draws + 2.5) / (len(training_matches) + 10.0)
    decisive_probability = 1.0 - draw_probability
    return {
        "H": decisive_probability * home_expectation,
        "D": draw_probability,
        "A": decisive_probability * (1.0 - home_expectation),
    }


def _metric_summary(predictions, outcomes, calibration_bins=10):
    if not predictions:
        raise ValueError("At least one prediction is required")
    log_loss = 0.0
    brier = 0.0
    ranked = 0.0
    calibration = [[] for _ in range(calibration_bins)]
    for probabilities, outcome in zip(predictions, outcomes):
        actual = {key: 1.0 if key == outcome else 0.0 for key in OUTCOMES}
        log_loss -= math.log(max(1e-15, probabilities[outcome]))
        brier += sum((probabilities[key] - actual[key]) ** 2 for key in OUTCOMES)
        predicted_cumulative = 0.0
        actual_cumulative = 0.0
        for key in OUTCOMES[:-1]:
            predicted_cumulative += probabilities[key]
            actual_cumulative += actual[key]
            ranked += (predicted_cumulative - actual_cumulative) ** 2
        predicted_outcome = max(OUTCOMES, key=lambda key: probabilities[key])
        confidence = probabilities[predicted_outcome]
        bin_index = min(calibration_bins - 1, int(confidence * calibration_bins))
        calibration[bin_index].append((confidence, predicted_outcome == outcome))
    sample_count = len(predictions)
    expected_calibration_error = 0.0
    for values in calibration:
        if not values:
            continue
        mean_confidence = sum(item[0] for item in values) / len(values)
        accuracy = sum(1.0 if item[1] else 0.0 for item in values) / len(values)
        expected_calibration_error += (len(values) / sample_count) * abs(
            mean_confidence - accuracy
        )
    return {
        "sample_count": sample_count,
        "log_loss": log_loss / sample_count,
        "brier_score": brier / sample_count,
        "ranked_probability_score": ranked / sample_count,
        "expected_calibration_error": expected_calibration_error,
    }


def run_walk_forward(
    history_matches,
    competition_code,
    min_training_matches=50,
    parameters=None,
    sample_pool=None,
):
    competition_code = str(competition_code).strip()
    if not competition_code:
        raise ValueError("competition_code is required")
    if min_training_matches < 1:
        raise ValueError("min_training_matches must be positive")
    parameters = parameters or ModelParameters()
    ordered = finished_matches_before(history_matches)
    if sample_pool is None:
        target_team_type = (
            ordered[0].get("context", {}).get("team_type", "club")
            if (ordered and isinstance(ordered[0].get("context"), dict))
            else "club"
        )
        sample_pool = {
            "pool_id": f"history:{competition_code}",
            "team_type": target_team_type,
            "competition_codes": [competition_code],
        }
    model_predictions = []
    elo_predictions = []
    outcomes = []
    audit = []
    skipped = []
    for target in ordered:
        target_kickoff = parse_datetime(target["kickoff_utc"])
        training = [
            match
            for match in ordered
            if parse_datetime(match["kickoff_utc"]) < target_kickoff
        ]
        if len(training) < min_training_matches:
            continue
        target_context = target.get("context") if isinstance(target.get("context"), dict) else {
            "team_type": "club",
            "competition_type": "league",
            "venue": "home",
            "score_basis": "regulation",
        }
        prediction = create_prediction(
            history_matches=training,
            match={
                "match_id": target["match_id"],
                "competition_code": competition_code,
                "competition_name": target.get("competition_name") or COMPETITION_NAMES.get(competition_code, competition_code),
                "season": str(target_kickoff.year),
                "kickoff_utc": target["kickoff_utc"],
                "context": target_context,
                "home_team": target["home_team"],
                "away_team": target["away_team"],
            },
            data_snapshot={
                "provider": "history-adapter",
                "source_url": "in-memory-history-before-target",
                "fetched_at": utc_iso(target_kickoff - timedelta(seconds=1)),
                "provenance_status": "verified",
                "sample_pool": sample_pool,
            },
            parameters=parameters,
        )
        if prediction["quality"]["status"] != "sufficient":
            skipped.append(
                {
                    "match_id": target["match_id"],
                    "reason": "insufficient_history",
                    "detail": prediction["quality"]["missing_data"],
                }
            )
            continue
        model_predictions.append(prediction["probabilities"]["had"])
        elo_predictions.append(_simple_elo_probabilities(training, target, parameters))
        outcomes.append(_actual_outcome(target))
        audit.append(
            {
                "match_id": target["match_id"],
                "training_match_count": len(training),
                "latest_training_kickoff_utc": training[-1]["kickoff_utc"],
                "target_kickoff_utc": target["kickoff_utc"],
                "target_context": target_context,
            }
        )
    if not outcomes:
        raise ValueError("No matches passed the walk-forward quality gate")
    model_metrics = _metric_summary(model_predictions, outcomes)
    elo_metrics = _metric_summary(elo_predictions, outcomes)
    return {
        "kind": "backtest_report",
        "method": "walk_forward",
        "competition_code": competition_code,
        "parameters": asdict(parameters),
        "input_matches": len(ordered),
        "minimum_training_matches": min_training_matches,
        "evaluated_matches": len(outcomes),
        "skipped_matches": skipped,
        "metrics": {
            "football_elo_poisson": model_metrics,
            "simple_home_elo": elo_metrics,
        },
        "metric_delta_model_minus_elo": {
            key: model_metrics[key] - elo_metrics[key]
            for key in (
                "log_loss",
                "brier_score",
                "ranked_probability_score",
                "expected_calibration_error",
            )
        },
        "audit": audit,
        "limitations": [
            "No historical odds were supplied; ROI and CLV are not calculated.",
            "Default parameters remain uncalibrated until evaluated on full seasons.",
        ],
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Walk-forward backtest for the football model.")
    parser.add_argument("--history-file", required=True)
    parser.add_argument("--competition", required=True, help="Competition code (e.g. PL, PD, J1)")
    parser.add_argument("--min-training-matches", type=int, default=50)
    parser.add_argument("--min-team-matches", type=int, default=5)
    parser.add_argument("--home-advantage-elo", type=float, default=60.0)
    parser.add_argument("--form-window", type=int, default=10)
    parser.add_argument("--form-decay", type=float, default=0.85)
    parser.add_argument("--output")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        history, _ = load_history_file(args.history_file)
        report = run_walk_forward(
            history,
            competition_code=args.competition,
            min_training_matches=args.min_training_matches,
            parameters=ModelParameters(
                min_team_matches=args.min_team_matches,
                home_advantage_elo=args.home_advantage_elo,
                form_window=args.form_window,
                form_decay=args.form_decay,
            ),
        )
        if args.output:
            write_json(args.output, report)
            print(json.dumps({"status": "success", "output": args.output}, ensure_ascii=False))
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
    except ValueError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

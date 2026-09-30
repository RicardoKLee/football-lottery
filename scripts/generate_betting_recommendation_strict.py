#!/usr/bin/env python3

import argparse
import glob
import json
import os
import sys
import tempfile

import fetch_lottery_data
from contracts import (
    BUSINESS_TIMEZONE,
    ContractError,
    load_json,
    parse_datetime,
    utc_now,
    validate_model_prediction,
    validate_odds_snapshot,
    write_json,
)
from generate_betting_recommendation import analyze_daily, render_markdown


def _prediction_files(paths):
    files = []
    for path in paths:
        if os.path.isdir(path):
            files.extend(glob.glob(os.path.join(path, "**", "*.json"), recursive=True))
        else:
            files.append(path)
    return sorted(set(files))


def load_predictions(paths):
    predictions = []
    errors = []
    for path in _prediction_files(paths):
        try:
            payload = load_json(path)
            if payload.get("kind") != "model_prediction":
                continue
            predictions.append(validate_model_prediction(payload))
        except ContractError as exc:
            errors.append({"path": path, "reason": str(exc)})
    if not predictions:
        detail = f"; invalid files: {errors}" if errors else ""
        raise ContractError(f"No valid model_prediction JSON files found{detail}")
    return predictions, errors


def load_odds_snapshot(path, requested_date, now):
    if not path:
        raw, fetched_at = fetch_lottery_data.fetch_raw_lottery_data()
        snapshot = fetch_lottery_data.parse_odds_data(
            raw,
            fetched_at=fetched_at,
            source_mode="live",
            now=now,
            requested_date=requested_date,
        )
    else:
        payload = load_json(path)
        if payload.get("kind") == "odds_snapshot":
            snapshot = validate_odds_snapshot(payload)
            snapshot = {**snapshot, "source_mode": "file"}
        else:
            fetched_at = payload.get("fetched_at")
            if not fetched_at:
                raise ContractError(
                    "Raw odds files must include fetched_at; capture time cannot be inferred for betting"
                )
            snapshot = fetch_lottery_data.parse_odds_data(
                payload,
                fetched_at=fetched_at,
                source_mode="file",
                now=now,
                requested_date=requested_date,
            )
    matches = fetch_lottery_data.filter_matches(snapshot["matches"], date=requested_date)
    return {**snapshot, "requested_date": requested_date, "matches": matches, "count": len(matches)}


def _write_text(path, content):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix=".tmp-", suffix=".md", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate fail-closed Sporttery football recommendations from JSON predictions."
    )
    parser.add_argument(
        "--predictions",
        nargs="+",
        default=["output/predictions"],
        help="Prediction JSON files or directories",
    )
    parser.add_argument("--lottery-file", help="Explicit normalized or raw odds JSON")
    parser.add_argument("--date", help="Business/match date; defaults to today in Asia/Shanghai")
    parser.add_argument("--bankroll", type=float, default=200.0)
    parser.add_argument("--unit", type=float, default=2.0)
    parser.add_argument("--max-odds-age", type=int, default=900, help="Maximum odds age in seconds")
    parser.add_argument(
        "--max-prediction-age", type=int, default=86400, help="Maximum model data snapshot age in seconds"
    )
    parser.add_argument("--probability-haircut", type=float, default=0.03)
    parser.add_argument("--min-ev-low", type=float, default=0.05)
    parser.add_argument(
        "--max-divergence-ratio",
        type=float,
        default=2.0,
        help="Maximum ratio of model probability to de-vigged market probability (default: 2.0)",
    )
    parser.add_argument(
        "--max-single-odds",
        type=float,
        default=70.0,
        help="Maximum decimal odds allowed for single bet recommendations (default: 70.0)",
    )
    parser.add_argument(
        "--all-eligible",
        action="store_true",
        help="Include all eligible selections with EV > threshold across markets (default: 1 per match)",
    )
    parser.add_argument(
        "--max-total-exposure",
        type=float,
        default=0.50,
        help="Maximum total exposure fraction (default: 0.50)",
    )
    parser.add_argument(
        "--include-parlays",
        dest="include_parlays",
        action="store_true",
        default=True,
        help="Include multi-leg mixed parlays (2-leg and 4-leg) in recommendations (default: True)",
    )
    parser.add_argument(
        "--no-parlays",
        dest="include_parlays",
        action="store_false",
        help="Disable parlay recommendations and generate single bets only",
    )
    parser.add_argument(
        "--parlay-legs",
        type=int,
        nargs="+",
        default=[2, 4],
        help="Leg counts for parlays when enabled (default: 2 4)",
    )
    parser.add_argument(
        "--max-match-repetition",
        type=int,
        default=None,
        help="Maximum appearances of any match across recommended parlays to prevent concentration risk (decentralized pairing)",
    )
    parser.add_argument(
        "--include-system-bets",
        action="store_true",
        help="Include fault-tolerant system bets (e.g. 3串4, 4串11)",
    )
    parser.add_argument(
        "--system-types",
        nargs="+",
        default=["3_in_4", "4_in_11"],
        help="System bet types (choices: 3_in_3, 3_in_4, 4_in_4, 4_in_5, 4_in_6, 4_in_11)",
    )
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    parser.add_argument(
        "--now",
        help="Simulate execution at this ISO 8601 timestamp (for replay/backtest)",
    )
    return parser.parse_args(argv)


def run(args, now=None):
    if getattr(args, "now", None):
        now = parse_datetime(args.now)
    else:
        now = now or utc_now()
    business_today = now.astimezone(BUSINESS_TIMEZONE).date().isoformat()
    requested_date = args.date or business_today
    predictions, prediction_load_errors = load_predictions(args.predictions)
    odds_snapshot = load_odds_snapshot(args.lottery_file, requested_date, now)
    include_parlays = args.parlay_legs if args.include_parlays else False
    report = analyze_daily(
        odds_snapshot,
        predictions,
        now=now,
        bankroll=args.bankroll,
        unit=args.unit,
        max_odds_age_seconds=args.max_odds_age,
        max_prediction_age_seconds=args.max_prediction_age,
        probability_haircut=args.probability_haircut,
        min_ev_low=args.min_ev_low,
        max_total_exposure=args.max_total_exposure,
        include_parlays=include_parlays,
        max_divergence_ratio=args.max_divergence_ratio,
        max_single_odds=args.max_single_odds,
        all_eligible=getattr(args, "all_eligible", False),
        max_match_repetition=args.max_match_repetition,
        include_system_bets=args.include_system_bets,
        system_types=args.system_types,
    )
    if prediction_load_errors:
        report["rejections"].extend(
            {
                "match_id": None,
                "reason": "prediction_file_invalid",
                "detail": item,
            }
            for item in prediction_load_errors
        )
    report["requested_date"] = requested_date
    return report


def main(argv=None):
    args = parse_args(argv)
    try:
        report = run(args)
        compact_date = report["requested_date"].replace("-", "")
        json_path = args.json_output or os.path.join(args.output_dir, f"{compact_date}_betting.json")
        markdown_path = args.markdown_output or os.path.join(
            args.output_dir, f"{compact_date}_betting.md"
        )
        write_json(json_path, report)
        _write_text(markdown_path, render_markdown(report, report["requested_date"]))
        print(
            json.dumps(
                {
                    "status": "success",
                    "recommendation_count": len(report["recommendations"]),
                    "json_output": json_path,
                    "markdown_output": markdown_path,
                },
                ensure_ascii=False,
            )
        )
    except (ContractError, fetch_lottery_data.LotteryProviderError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

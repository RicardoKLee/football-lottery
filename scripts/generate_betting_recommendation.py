#!/usr/bin/env python3

import itertools
import math
from datetime import timedelta

from contracts import (
    ContractError,
    normalize_name,
    parse_datetime,
    utc_iso,
    utc_now,
    validate_model_prediction,
    validate_odds_snapshot,
)

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
    "listed_by_official_api",
}
CRS_HOME_OPTIONS = {
    "1-0", "2-0", "2-1", "3-0", "3-1", "3-2", "4-0", "4-1", "4-2", "5-0", "5-1", "5-2"
}
CRS_DRAW_OPTIONS = {"0-0", "1-1", "2-2", "3-3"}
CRS_AWAY_OPTIONS = {
    "0-1", "0-2", "1-2", "0-3", "1-3", "2-3", "0-4", "1-4", "2-4", "0-5", "1-5", "2-5"
}
EXPECTED_MARKET_OPTIONS = {
    "had": {"h", "d", "a"},
    "hhad": {"h", "d", "a"},
    "ttg": {f"s{index}" for index in range(8)},
    "crs": CRS_HOME_OPTIONS
    | CRS_DRAW_OPTIONS
    | CRS_AWAY_OPTIONS
    | {"胜其他", "平其他", "负其他"},
}


def market_reasons(match: dict, market: str) -> list:
    if not isinstance(match, dict):
        return ["market_sale_unknown"]
    market_status = match.get("market_status")
    if not isinstance(market_status, dict) or market not in market_status:
        return ["market_sale_unknown"]
    status = market_status.get(market)
    if status == "open":
        return []
    if status == "closed":
        return ["market_closed"]
    return ["market_sale_unknown"]


def recommendation_reasons(prediction: dict) -> list:
    if not isinstance(prediction, dict):
        return ["prediction_invalid"]
    reasons = []
    quality = prediction.get("quality")
    if not isinstance(quality, dict):
        reasons.append("quality_missing")
    else:
        if quality.get("status") != "sufficient":
            reasons.append("prediction_quality_insufficient")
        for m in quality.get("missing_data", []):
            reasons.append(m)

    match = prediction.get("match") if isinstance(prediction, dict) else {}
    context = match.get("context") if isinstance(match, dict) else None
    if not isinstance(context, dict):
        reasons.append("context_missing")
    else:
        from match_context import context_reasons
        try:
            reasons.extend(context_reasons(context))
        except ValueError:
            reasons.append("context_invalid")

    snapshot = prediction.get("data_snapshot") if isinstance(prediction, dict) else {}
    if not isinstance(snapshot, dict):
        reasons.append("data_snapshot_missing")
    else:
        if snapshot.get("provenance_status") != "verified":
            reasons.append("provenance_unverified")
        sample_pool = snapshot.get("sample_pool")
        if not isinstance(sample_pool, dict) or not sample_pool:
            reasons.append("sample_pool_invalid")
    return list(dict.fromkeys(reasons))


def calculate_market_margin_and_implied_probs(odds_dict):
    valid = {}
    for key, value in (odds_dict or {}).items():
        if key == "goal_line" or value is None or isinstance(value, bool):
            continue
        try:
            odds = float(value)
        except (TypeError, ValueError):
            continue
        if odds > 1.0 and math.isfinite(odds):
            valid[str(key)] = odds
    if not valid:
        return 0.0, 0.0, {}
    overround = sum(1.0 / odds for odds in valid.values())
    if overround <= 0:
        return 0.0, 0.0, {}
    implied = {key: (1.0 / odds) / overround for key, odds in valid.items()}
    return overround - 1.0, 1.0 / overround, implied


def calculate_kelly_position(probability, odds, fraction=0.5, max_position=0.05):
    if not 0.0 < probability < 1.0 or odds <= 1.0:
        return 0.0
    full_kelly = (probability * odds - 1.0) / (odds - 1.0)
    if full_kelly <= 0:
        return 0.0
    return min(float(max_position), float(fraction) * full_kelly)


def _score_items(prediction):
    for score, probability in prediction["probabilities"]["score"].items():
        try:
            home_goals, away_goals = (int(value) for value in score.split("-", 1))
        except (ValueError, AttributeError):
            continue
        yield home_goals, away_goals, float(probability)


def _hhad_probabilities(prediction, goal_line):
    probabilities = {"h": 0.0, "d": 0.0, "a": 0.0}
    for home_goals, away_goals, probability in _score_items(prediction):
        adjusted_home = home_goals + goal_line
        if adjusted_home > away_goals:
            probabilities["h"] += probability
        elif adjusted_home == away_goals:
            probabilities["d"] += probability
        else:
            probabilities["a"] += probability
    return probabilities


def _crs_probabilities(prediction):
    probabilities = {
        key: 0.0 for key in CRS_HOME_OPTIONS | CRS_DRAW_OPTIONS | CRS_AWAY_OPTIONS
    }
    probabilities.update({"胜其他": 0.0, "平其他": 0.0, "负其他": 0.0})
    for home_goals, away_goals, probability in _score_items(prediction):
        key = f"{home_goals}-{away_goals}"
        if home_goals > away_goals:
            target = key if key in CRS_HOME_OPTIONS else "胜其他"
        elif home_goals == away_goals:
            target = key if key in CRS_DRAW_OPTIONS else "平其他"
        else:
            target = key if key in CRS_AWAY_OPTIONS else "负其他"
        probabilities[target] += probability
    return probabilities


def _model_probabilities(prediction, market_name, odds):
    if market_name == "had":
        had = prediction["probabilities"]["had"]
        return {"h": had["H"], "d": had["D"], "a": had["A"]}
    if market_name == "hhad":
        goal_line = odds.get("goal_line")
        return _hhad_probabilities(prediction, goal_line) if goal_line is not None else {}
    if market_name == "ttg":
        return prediction["probabilities"]["ttg"]
    if market_name == "crs":
        return _crs_probabilities(prediction)
    return {}


def evaluate_match(match, prediction, probability_haircut=0.03, min_ev_low=0.05):
    evaluations = []
    for market_name in ("had", "hhad", "ttg", "crs"):
        if market_reasons(match, market_name):
            continue
        odds = match.get("odds", {}).get(market_name)
        if not isinstance(odds, dict):
            continue
        market_odds = {key: value for key, value in odds.items() if key != "goal_line"}
        if set(market_odds) != EXPECTED_MARKET_OPTIONS[market_name]:
            continue
        margin, payout, implied = calculate_market_margin_and_implied_probs(market_odds)
        model_probabilities = _model_probabilities(prediction, market_name, odds)
        for option, decimal_odds in market_odds.items():
            if option not in model_probabilities or decimal_odds is None:
                continue
            try:
                decimal_odds = float(decimal_odds)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(decimal_odds) or decimal_odds <= 1.0:
                continue
            probability = float(model_probabilities[option])
            conservative_probability = max(0.0, probability - probability_haircut)
            ev = probability * decimal_odds - 1.0
            ev_low = conservative_probability * decimal_odds - 1.0
            kelly = calculate_kelly_position(conservative_probability, decimal_odds)
            evaluation = {
                "bet_id": f"{match['match_id']}:{market_name}:{option}",
                "match_id": match["match_id"],
                "match_num": match.get("match_num"),
                "competition": match.get("competition"),
                "home_team": match["home_team"]["name"],
                "away_team": match["away_team"]["name"],
                "market": market_name,
                "option": str(option),
                "goal_line": odds.get("goal_line"),
                "odds": float(decimal_odds),
                "probability": probability,
                "conservative_probability": conservative_probability,
                "market_probability": implied.get(option),
                "market_margin": margin,
                "market_payout": payout,
                "ev": ev,
                "ev_low": ev_low,
                "kelly_fraction": kelly,
                "eligible": ev_low >= min_ev_low and kelly > 0.0,
            }
            evaluations.append(evaluation)
    return evaluations


def _prediction_name_keys(prediction):
    match = prediction["match"]
    home = match["home_team"]
    away = match["away_team"]
    home_names = {normalize_name(home["name"])} | {
        normalize_name(alias) for alias in home.get("aliases", [])
    }
    away_names = {normalize_name(away["name"])} | {
        normalize_name(alias) for alias in away.get("aliases", [])
    }
    return {(home_name, away_name) for home_name in home_names for away_name in away_names if home_name and away_name}


def _prediction_indexes(predictions):
    by_id = {}
    by_names = {}
    invalid = []
    for index, prediction in enumerate(predictions):
        try:
            validate_model_prediction(prediction)
        except ContractError as exc:
            invalid.append({"match_id": None, "reason": "prediction_contract_invalid", "detail": f"index {index}: {exc}"})
            continue
        match = prediction["match"]
        for value in (match.get("match_id"), match.get("lottery_match_id")):
            if value:
                text = str(value)
                by_id.setdefault(text, []).append(prediction)
                if text.startswith("sporttery:"):
                    by_id.setdefault(text.split(":", 1)[1], []).append(prediction)
        for key in _prediction_name_keys(prediction):
            by_names.setdefault(key, []).append(prediction)
    return by_id, by_names, invalid


def _find_prediction(match, by_id, by_names):
    id_candidates = []
    for value in (match.get("match_id"), match.get("provider_match_id")):
        id_candidates.extend(by_id.get(str(value), []))
    unique = {id(candidate): candidate for candidate in id_candidates}
    if len(unique) == 1:
        return next(iter(unique.values())), None
    if len(unique) > 1:
        return None, "prediction_mapping_ambiguous"
    key = (
        normalize_name(match.get("home_team", {}).get("name")),
        normalize_name(match.get("away_team", {}).get("name")),
    )
    name_candidates = {id(candidate): candidate for candidate in by_names.get(key, [])}
    if len(name_candidates) == 1:
        return next(iter(name_candidates.values())), None
    if len(name_candidates) > 1:
        return None, "prediction_mapping_ambiguous"
    return None, "prediction_not_found"


def allocate_bankroll(bets, bankroll=200.0, unit=2.0, max_total_exposure=0.20):
    if bankroll < 0 or unit <= 0 or not 0 <= max_total_exposure <= 1:
        raise ValueError("Invalid bankroll policy")
    desired = [max(0.0, bankroll * float(bet.get("kelly_fraction", 0.0))) for bet in bets]
    exposure_limit = bankroll * max_total_exposure
    desired_total = sum(desired)
    scale = min(1.0, exposure_limit / desired_total) if desired_total > 0 else 0.0
    allocated = []
    for bet, raw_stake in zip(bets, desired):
        scaled = raw_stake * scale
        stake = math.floor((scaled + 1e-12) / unit) * unit
        allocated.append({**bet, "raw_stake": raw_stake, "stake": stake})
    staked = round(sum(item["stake"] for item in allocated), 10)
    return allocated, {
        "total": float(bankroll),
        "staked": staked,
        "cash_reserved": round(float(bankroll) - staked, 10),
        "max_total_exposure": max_total_exposure,
        "actual_exposure": staked / bankroll if bankroll else 0.0,
        "unit": float(unit),
    }


def build_two_leg_parlays(bets, min_ev_low=0.05, max_position=0.02):
    parlays = []
    for first, second in itertools.combinations(bets, 2):
        if first["match_id"] == second["match_id"]:
            continue
        probability = first["probability"] * second["probability"]
        conservative_probability = (
            first["conservative_probability"] * second["conservative_probability"]
        )
        odds = first["odds"] * second["odds"]
        ev = probability * odds - 1.0
        ev_low = conservative_probability * odds - 1.0
        if ev_low < min_ev_low:
            continue
        kelly = calculate_kelly_position(
            conservative_probability, odds, fraction=0.25, max_position=max_position
        )
        parlays.append(
            {
                "bet_id": f"parlay:{first['bet_id']}+{second['bet_id']}",
                "type": "two_leg_parlay",
                "match_id": "+".join(sorted((first["match_id"], second["match_id"]))),
                "match_ids": [first["match_id"], second["match_id"]],
                "legs": [first["bet_id"], second["bet_id"]],
                "odds": odds,
                "probability": probability,
                "conservative_probability": conservative_probability,
                "ev": ev,
                "ev_low": ev_low,
                "kelly_fraction": kelly,
                "eligible": kelly > 0,
                "assumption": "different matches treated as independent; residual correlation is not estimated",
            }
        )
    return sorted(parlays, key=lambda item: item["ev_low"], reverse=True)


def _empty_report(now, bankroll, policy, rejections):
    return {
        "kind": "betting_report",
        "generated_at": utc_iso(now),
        "policy": policy,
        "evaluations": [],
        "recommendations": [],
        "rejections": rejections,
        "bankroll": {
            "total": float(bankroll),
            "staked": 0.0,
            "cash_reserved": float(bankroll),
            "max_total_exposure": policy["max_total_exposure"],
            "actual_exposure": 0.0,
            "unit": policy["unit"],
        },
    }


def analyze_daily(
    odds_snapshot,
    predictions,
    now=None,
    bankroll=200.0,
    unit=2.0,
    max_odds_age_seconds=900,
    max_prediction_age_seconds=86400,
    probability_haircut=0.03,
    min_ev_low=0.05,
    max_total_exposure=0.20,
    include_parlays=False,
):
    now = parse_datetime(now or utc_now())
    if bankroll < 0 or unit <= 0:
        raise ValueError("bankroll must be non-negative and unit must be positive")
    if max_odds_age_seconds <= 0 or max_prediction_age_seconds <= 0:
        raise ValueError("freshness limits must be positive")
    if not 0.0 <= probability_haircut < 1.0:
        raise ValueError("probability_haircut must be in [0, 1)")
    if min_ev_low < 0.0:
        raise ValueError("min_ev_low cannot be negative")
    if not 0.0 <= max_total_exposure <= 1.0:
        raise ValueError("max_total_exposure must be in [0, 1]")
    policy = {
        "probability_source": "model_only",
        "market_probability_usage": "comparison_only",
        "probability_haircut": probability_haircut,
        "min_ev_low": min_ev_low,
        "kelly_fraction": 0.5,
        "max_single_position": 0.05,
        "max_total_exposure": max_total_exposure,
        "unit": float(unit),
        "parlays_enabled": bool(include_parlays),
    }
    try:
        validate_odds_snapshot(odds_snapshot)
    except ContractError as exc:
        return _empty_report(
            now, bankroll, policy, [{"match_id": None, "reason": "odds_contract_invalid", "detail": str(exc)}]
        )
    fetched_at = parse_datetime(odds_snapshot["fetched_at"])
    age = (now - fetched_at).total_seconds()
    if age < -60:
        return _empty_report(
            now, bankroll, policy, [{"match_id": None, "reason": "odds_snapshot_from_future", "detail": age}]
        )
    if age > max_odds_age_seconds:
        return _empty_report(
            now, bankroll, policy, [{"match_id": None, "reason": "odds_snapshot_stale", "detail": age}]
        )

    by_id, by_names, rejections = _prediction_indexes(predictions)
    evaluations = []
    eligible_by_match = []
    for match in odds_snapshot["matches"]:
        match_id = match["match_id"]
        listing = match.get("official_listing")
        if not isinstance(listing, dict) or listing.get("status") != "confirmed":
            rejections.append(
                {
                    "match_id": match_id,
                    "reason": "match_not_officially_listed",
                    "detail": listing.get("status") if isinstance(listing, dict) else "missing",
                }
            )
            continue
        sale_status = str(match.get("sale_status", "")).casefold()
        if not match.get("is_available") or sale_status not in OPEN_SALE_STATUSES:
            rejections.append(
                {
                    "match_id": match_id,
                    "reason": "match_not_available",
                    "detail": {
                        "sale_status": match.get("sale_status"),
                        "availability_reasons": match.get("availability_reasons", []),
                    },
                }
            )
            continue
        if parse_datetime(match["cutoff_utc"]) <= now:
            rejections.append({"match_id": match_id, "reason": "cutoff_passed"})
            continue
        observed_age = (now - parse_datetime(match["odds_observed_at"])).total_seconds()
        if observed_age > max_odds_age_seconds or observed_age < -60:
            rejections.append({"match_id": match_id, "reason": "match_odds_stale", "detail": observed_age})
            continue
        prediction, mapping_error = _find_prediction(match, by_id, by_names)
        if mapping_error:
            rejections.append({"match_id": match_id, "reason": mapping_error})
            continue
        if prediction is None:
            rejections.append({"match_id": match_id, "reason": "prediction_not_found"})
            continue
        pred_reasons = recommendation_reasons(prediction)
        if pred_reasons:
            reason = "prediction_quality_insufficient" if "prediction_quality_insufficient" in pred_reasons else "prediction_rejected"
            rejections.append(
                {"match_id": match_id, "reason": reason, "detail": pred_reasons}
            )
            continue
        prediction_age = (now - parse_datetime(prediction["data_snapshot"]["fetched_at"])).total_seconds()
        if prediction_age > max_prediction_age_seconds or prediction_age < -60:
            rejections.append({"match_id": match_id, "reason": "prediction_snapshot_stale", "detail": prediction_age})
            continue
        kickoff_delta = abs(
            (parse_datetime(match["kickoff_utc"]) - parse_datetime(prediction["match"]["kickoff_utc"])).total_seconds()
        )
        if kickoff_delta > timedelta(minutes=15).total_seconds():
            rejections.append({"match_id": match_id, "reason": "kickoff_mismatch", "detail": kickoff_delta})
            continue
        match_evaluations = evaluate_match(
            match,
            prediction,
            probability_haircut=probability_haircut,
            min_ev_low=min_ev_low,
        )
        evaluations.extend(match_evaluations)
        eligible = [item for item in match_evaluations if item["eligible"]]
        if eligible:
            eligible_by_match.append(max(eligible, key=lambda item: item["ev_low"]))
        else:
            rejections.append({"match_id": match_id, "reason": "no_selection_above_ev_threshold"})

    candidates = sorted(eligible_by_match, key=lambda item: item["ev_low"], reverse=True)
    if include_parlays:
        candidates.extend(build_two_leg_parlays(candidates, min_ev_low=min_ev_low)[:3])
    allocated, bankroll_summary = allocate_bankroll(
        candidates,
        bankroll=bankroll,
        unit=unit,
        max_total_exposure=max_total_exposure,
    )
    recommendations = [item for item in allocated if item["stake"] >= unit]
    for item in allocated:
        if item["stake"] < unit:
            rejections.append(
                {"match_id": item.get("match_id"), "reason": "kelly_stake_below_minimum_unit", "detail": item["raw_stake"]}
            )
    return {
        "kind": "betting_report",
        "generated_at": utc_iso(now),
        "odds_snapshot": {
            "provider": odds_snapshot["provider"],
            "source_url": odds_snapshot["source_url"],
            "fetched_at": odds_snapshot["fetched_at"],
        },
        "policy": policy,
        "evaluations": evaluations,
        "recommendations": recommendations,
        "rejections": rejections,
        "bankroll": bankroll_summary,
    }


def _selection_label(recommendation):
    if recommendation.get("type") == "two_leg_parlay":
        return "2串1：" + " × ".join(recommendation["legs"])
    market = recommendation["market"].upper()
    option = recommendation["option"]
    if recommendation.get("goal_line") is not None:
        market = f"{market}({recommendation['goal_line']:+d})"
    return f"{recommendation['match_num']} {recommendation['home_team']} vs {recommendation['away_team']} {market}-{option}"


def render_markdown(report, title_date=None):
    title_date = title_date or report["generated_at"][:10]
    lines = [
        f"# 竞彩足球投注分析（{title_date}）",
        "",
        f"- 赔率快照：{report.get('odds_snapshot', {}).get('fetched_at', '不可用')}",
        f"- 概率折减：{report['policy']['probability_haircut']:.1%}",
        f"- 保守 EV 门槛：{report['policy']['min_ev_low']:.1%}",
        "",
        "## 投注建议",
        "",
    ]
    if not report["recommendations"]:
        lines.append("当前没有满足数据完整性、赔率时效和保守 EV 门槛的投注建议。")
    else:
        lines.extend(
            [
                "| 选项 | 实时赔率 | 模型概率 | 保守概率 | 保守 EV | 凯利比例 | 金额 |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for item in report["recommendations"]:
            lines.append(
                f"| {_selection_label(item)} | {item['odds']:.2f} | {item['probability']:.1%} | "
                f"{item['conservative_probability']:.1%} | {item['ev_low']:+.1%} | "
                f"{item['kelly_fraction']:.1%} | {item['stake']:.0f} 元 |"
            )
    bankroll = report["bankroll"]
    lines.extend(
        [
            "",
            "## 资金",
            "",
            f"本金 {bankroll['total']:.0f} 元，建议投注 {bankroll['staked']:.0f} 元，保留现金 {bankroll['cash_reserved']:.0f} 元。",
            "",
            "## 拒绝记录",
            "",
        ]
    )
    if not report["rejections"]:
        lines.append("无。")
    else:
        for rejection in report["rejections"]:
            lines.append(
                f"- {rejection.get('match_id') or '全局'}：{rejection['reason']}"
                + (f"；{rejection['detail']}" if "detail" in rejection else "")
            )
    lines.extend(
        [
            "",
            "## 风险提示",
            "",
            "概率折减是风险缓冲，不是统计置信区间。模型和赔率都可能出错；彩票投注不保证收益。",
            "",
        ]
    )
    return "\n".join(lines)

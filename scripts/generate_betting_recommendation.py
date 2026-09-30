import collections
import functools
import itertools
import math
import operator
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


def market_category(market: str) -> str:
    if market in ("had", "hhad"):
        return "had_hhad"
    return str(market) if market else "unknown"


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


def get_disciplinary_haircut(prediction, market_name, option):
    if not isinstance(prediction, dict):
        return 0.0
    disciplinary = (
        prediction.get("inputs", {}).get("disciplinary")
        if isinstance(prediction.get("inputs"), dict)
        else None
    )
    if not disciplinary and isinstance(prediction.get("disciplinary"), dict):
        disciplinary = prediction["disciplinary"]
    if not isinstance(disciplinary, dict) or disciplinary.get("status") != "observed":
        return 0.0

    home_haircut = float(disciplinary.get("home", {}).get("disciplinary_haircut", 0.0) or 0.0)
    away_haircut = float(disciplinary.get("away", {}).get("disciplinary_haircut", 0.0) or 0.0)

    if market_name in ("had", "hhad"):
        if option == "h":
            return home_haircut
        elif option == "a":
            return away_haircut
        else:
            return 0.0
    elif market_name == "crs":
        if option in CRS_HOME_OPTIONS:
            return home_haircut
        elif option in CRS_AWAY_OPTIONS:
            return away_haircut
        else:
            return 0.0
    elif market_name == "ttg":
        return 0.0
    return 0.0


def evaluate_match(
    match,
    prediction,
    probability_haircut=0.03,
    min_ev_low=0.05,
    max_divergence_ratio=2.0,
    max_single_odds=70.0,
):
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
            disc_haircut = get_disciplinary_haircut(prediction, market_name, option)
            total_haircut = probability_haircut + disc_haircut
            conservative_probability = max(0.0, probability - total_haircut)
            ev = probability * decimal_odds - 1.0
            ev_low = conservative_probability * decimal_odds - 1.0
            base_ev_low = max(0.0, probability - probability_haircut) * decimal_odds - 1.0
            kelly = calculate_kelly_position(conservative_probability, decimal_odds)
            market_prob = implied.get(option)
            divergence_ratio = (
                probability / market_prob
                if (market_prob and market_prob > 0)
                else None
            )

            rejection_reasons = []
            if ev_low < min_ev_low:
                rejection_reasons.append("ev_below_threshold")
                if disc_haircut > 0 and base_ev_low >= min_ev_low:
                    rejection_reasons.append("disciplinary_risk_rejected")
            if kelly <= 0:
                rejection_reasons.append("kelly_zero")
            if max_single_odds is not None and decimal_odds > max_single_odds:
                rejection_reasons.append("odds_above_ceiling")
            if (
                max_divergence_ratio is not None
                and divergence_ratio is not None
                and divergence_ratio > max_divergence_ratio
            ):
                rejection_reasons.append("market_divergence_too_high")

            eligible = len(rejection_reasons) == 0

            variance = (
                conservative_probability
                * (1.0 - conservative_probability)
                * (decimal_odds**2)
            )
            std = math.sqrt(variance) if variance > 0 else 1.0
            sharpe_ratio = ev_low / std if std > 0 else 0.0
            single_status = match.get("single_status")
            if isinstance(single_status, dict):
                single_allowed = bool(single_status.get(market_name, market_name == "crs"))
            else:
                single_allowed = True

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
                "probability_haircut": probability_haircut,
                "disciplinary_haircut": disc_haircut,
                "total_haircut": round(total_haircut, 4),
                "conservative_probability": conservative_probability,
                "market_probability": market_prob,
                "divergence_ratio": (
                    round(divergence_ratio, 3)
                    if divergence_ratio is not None
                    else None
                ),
                "market_margin": margin,
                "market_payout": payout,
                "ev": ev,
                "ev_low": ev_low,
                "sharpe_ratio": round(sharpe_ratio, 4),
                "kelly_fraction": kelly,
                "eligible": eligible,
                "single_allowed": single_allowed,
                "rejection_reasons": rejection_reasons,
                "disciplinary": (
                    prediction.get("inputs", {}).get("disciplinary")
                    if isinstance(prediction.get("inputs"), dict)
                    else None
                ),
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


def allocate_bankroll(bets, bankroll=200.0, unit=2.0, max_total_exposure=0.50):
    if bankroll < 0 or unit <= 0 or not 0 <= max_total_exposure <= 1:
        raise ValueError("Invalid bankroll policy")
    desired = [max(0.0, bankroll * float(bet.get("kelly_fraction", 0.0))) for bet in bets]
    exposure_limit = bankroll * max_total_exposure
    desired_total = sum(desired)
    scale = min(1.0, exposure_limit / desired_total) if desired_total > 0 else 0.0
    allocated = []
    for bet, raw_stake in zip(bets, desired):
        scaled = raw_stake * scale
        # If scaled is at least half a unit (e.g. >= 1.0 for unit=2.0), round to nearest unit
        # so that high-odds positive-EV value bets (TTG/CRS) are not zeroed out on small bankrolls
        stake = round((scaled + 1e-12) / unit) * unit if scaled >= unit * 0.5 else 0.0
        allocated.append({**bet, "raw_stake": raw_stake, "stake": stake})

    # Enforce exposure limit strictly if rounding up caused sum(stake) > exposure_limit
    while sum(item["stake"] for item in allocated) > exposure_limit:
        candidates_to_reduce = [item for item in allocated if item["stake"] >= unit]
        if not candidates_to_reduce:
            break
        worst = min(candidates_to_reduce, key=lambda item: (item["raw_stake"], item.get("ev_low", 0.0)))
        worst["stake"] -= unit

    staked = round(sum(item["stake"] for item in allocated), 10)
    return allocated, {
        "total": float(bankroll),
        "staked": staked,
        "cash_reserved": round(float(bankroll) - staked, 10),
        "max_total_exposure": max_total_exposure,
        "actual_exposure": staked / bankroll if bankroll else 0.0,
        "unit": float(unit),
    }


def build_multi_leg_parlays(
    bets,
    leg_count=2,
    min_ev_low=0.05,
    max_position=0.02,
    max_match_repetition=None,
):
    parlays = []
    type_name = "two_leg_parlay" if leg_count == 2 else f"{leg_count}_leg_parlay"
    for combo in itertools.combinations(bets, leg_count):
        match_ids = [b["match_id"] for b in combo]
        if len(set(match_ids)) != leg_count:
            continue
        # Check official Sporttery mixed parlay limit (CRS/HAFU max 4 legs, TTG max 6 legs)
        max_allowed_legs = min(
            4 if b.get("market") in ("crs", "hafu") else (6 if b.get("market") == "ttg" else 8)
            for b in combo
        )
        if leg_count > max_allowed_legs:
            continue
        probability = functools.reduce(operator.mul, [b["probability"] for b in combo], 1.0)
        conservative_probability = functools.reduce(
            operator.mul, [b["conservative_probability"] for b in combo], 1.0
        )
        odds = round(functools.reduce(operator.mul, [b["odds"] for b in combo], 1.0), 2)
        ev = probability * odds - 1.0
        ev_low = conservative_probability * odds - 1.0
        if ev_low < min_ev_low:
            continue
        kelly = calculate_kelly_position(
            conservative_probability, odds, fraction=0.25, max_position=max_position
        )
        variance = (
            conservative_probability
            * (1.0 - conservative_probability)
            * (odds**2)
        )
        std = math.sqrt(variance) if variance > 0 else 1.0
        sharpe_ratio = ev_low / std if std > 0 else 0.0

        distinct_categories = len(set(market_category(b.get("market", "")) for b in combo))
        is_mixed = distinct_categories > 1
        market_tags = [b.get("market", "").upper() for b in combo]
        mix_label = "+".join(sorted(set(market_tags)))

        leg_labels = []
        for b in combo:
            if "match_num" in b and "home_team" in b and "market" in b and "option" in b:
                market_tag = b["market"].upper()
                if b.get("goal_line") is not None:
                    market_tag += f"({b['goal_line']:+d})"
                leg_labels.append(f"{b['match_num']} {b['home_team']}({market_tag}-{b['option']})")
            else:
                leg_labels.append(b.get("bet_id", str(b)))
        parlays.append(
            {
                "bet_id": f"parlay:{'+'.join(b['bet_id'] for b in combo)}",
                "type": type_name,
                "leg_count": leg_count,
                "match_id": "+".join(sorted(match_ids)),
                "match_ids": match_ids,
                "legs": [b["bet_id"] for b in combo],
                "leg_labels": leg_labels,
                "is_mixed": is_mixed,
                "distinct_categories": distinct_categories,
                "mix_label": mix_label,
                "market_mix": market_tags,
                "odds": odds,
                "probability": probability,
                "conservative_probability": conservative_probability,
                "ev": ev,
                "ev_low": ev_low,
                "sharpe_ratio": round(sharpe_ratio, 4),
                "kelly_fraction": kelly,
                "eligible": kelly > 0,
                "assumption": "different matches treated as independent; residual correlation is not estimated",
            }
        )
    sorted_parlays = sorted(
        parlays,
        key=lambda item: (
            1 if item.get("is_mixed") else 0,
            item.get("sharpe_ratio", item["ev_low"]),
            item["ev_low"],
        ),
        reverse=True,
    )
    if max_match_repetition is None or max_match_repetition <= 0:
        return sorted_parlays

    filtered = []
    match_usage = collections.defaultdict(int)
    for p in sorted_parlays:
        if all(match_usage[m_id] < max_match_repetition for m_id in p["match_ids"]):
            filtered.append(p)
            for m_id in p["match_ids"]:
                match_usage[m_id] += 1
    return filtered


def build_two_leg_parlays(
    bets,
    min_ev_low=0.05,
    max_position=0.02,
    max_match_repetition=None,
):
    return build_multi_leg_parlays(
        bets,
        leg_count=2,
        min_ev_low=min_ev_low,
        max_position=max_position,
        max_match_repetition=max_match_repetition,
    )


SYSTEM_BET_DEFINITIONS = {
    "3_in_3": {"name": "3串3", "matches_required": 3, "sub_lengths": [2], "tolerance_matches": 1},
    "3_in_4": {"name": "3串4", "matches_required": 3, "sub_lengths": [2, 3], "tolerance_matches": 1},
    "4_in_4": {"name": "4串4", "matches_required": 4, "sub_lengths": [3], "tolerance_matches": 1},
    "4_in_5": {"name": "4串5", "matches_required": 4, "sub_lengths": [3, 4], "tolerance_matches": 1},
    "4_in_6": {"name": "4串6", "matches_required": 4, "sub_lengths": [2], "tolerance_matches": 2},
    "4_in_11": {"name": "4串11", "matches_required": 4, "sub_lengths": [2, 3, 4], "tolerance_matches": 2},
}


def build_system_bets(
    bets,
    system_types=("3_in_4", "4_in_11"),
    unit=2.0,
    min_ev_low=0.03,
):
    system_bets = []
    seen_matches = set()
    unique_bets = []
    for b in bets:
        if b["match_id"] not in seen_matches:
            seen_matches.add(b["match_id"])
            unique_bets.append(b)

    for sys_type in system_types:
        defn = SYSTEM_BET_DEFINITIONS.get(sys_type)
        if not defn:
            continue
        req_matches = defn["matches_required"]
        if len(unique_bets) < req_matches:
            continue

        for combo in itertools.combinations(unique_bets, req_matches):
            match_ids = [b["match_id"] for b in combo]
            max_allowed_legs = min(
                4 if b.get("market") in ("crs", "hafu") else (6 if b.get("market") == "ttg" else 8)
                for b in combo
            )
            if max(defn["sub_lengths"]) > max_allowed_legs:
                continue

            sub_bets = []
            for sub_len in defn["sub_lengths"]:
                for sub_combo in itertools.combinations(combo, sub_len):
                    prob = functools.reduce(operator.mul, [b["probability"] for b in sub_combo], 1.0)
                    cons_prob = functools.reduce(operator.mul, [b["conservative_probability"] for b in sub_combo], 1.0)
                    odds = round(functools.reduce(operator.mul, [b["odds"] for b in sub_combo], 1.0), 2)
                    sub_bets.append({
                        "leg_count": sub_len,
                        "match_ids": [b["match_id"] for b in sub_combo],
                        "legs": [b["bet_id"] for b in sub_combo],
                        "probability": prob,
                        "conservative_probability": cons_prob,
                        "odds": odds,
                    })

            bet_count = len(sub_bets)
            cost = bet_count * unit
            expected_payout = sum(sb["probability"] * sb["odds"] * unit for sb in sub_bets)
            conservative_expected_payout = sum(sb["conservative_probability"] * sb["odds"] * unit for sb in sub_bets)
            ev = (expected_payout - cost) / cost if cost > 0 else 0.0
            ev_low = (conservative_expected_payout - cost) / cost if cost > 0 else 0.0

            if ev_low < min_ev_low:
                continue

            all_hit_payout = sum(sb["odds"] * unit for sb in sub_bets)

            miss_1_payouts = []
            for failed_match in match_ids:
                payout_if_miss = sum(
                    sb["odds"] * unit for sb in sub_bets if failed_match not in sb["match_ids"]
                )
                miss_1_payouts.append(payout_if_miss)

            miss_2_payouts = []
            if defn["tolerance_matches"] >= 2:
                for pair in itertools.combinations(match_ids, 2):
                    payout_if_miss = sum(
                        sb["odds"] * unit for sb in sub_bets if not any(m in sb["match_ids"] for m in pair)
                    )
                    miss_2_payouts.append(payout_if_miss)

            leg_labels = []
            for b in combo:
                if "match_num" in b and "home_team" in b and "market" in b and "option" in b:
                    market_tag = b["market"].upper()
                    if b.get("goal_line") is not None:
                        market_tag += f"({b['goal_line']:+d})"
                    disc_tag = f" [纪律折减:{b.get('disciplinary_haircut'):.1%}]" if b.get("disciplinary_haircut") else ""
                    leg_labels.append(f"{b['match_num']} {b['home_team']}({market_tag}-{b['option']}){disc_tag}")
                else:
                    leg_labels.append(b.get("bet_id", str(b)))

            system_bets.append({
                "bet_id": f"system:{sys_type}:{'+'.join(b['bet_id'] for b in combo)}",
                "type": "system_bet",
                "system_name": defn["name"],
                "system_type": sys_type,
                "matches_required": req_matches,
                "tolerance_matches": defn["tolerance_matches"],
                "match_id": "+".join(sorted(match_ids)),
                "match_ids": match_ids,
                "legs": [b["bet_id"] for b in combo],
                "leg_labels": leg_labels,
                "bet_count": bet_count,
                "unit": unit,
                "cost": cost,
                "ev": round(ev, 4),
                "ev_low": round(ev_low, 4),
                "scenarios": {
                    "all_hit": {
                        "payout": round(all_hit_payout, 2),
                        "net_profit": round(all_hit_payout - cost, 2),
                        "roi": round(all_hit_payout / cost, 2),
                    },
                    "miss_1": {
                        "min_payout": round(min(miss_1_payouts), 2) if miss_1_payouts else 0.0,
                        "max_payout": round(max(miss_1_payouts), 2) if miss_1_payouts else 0.0,
                        "avg_payout": round(sum(miss_1_payouts) / len(miss_1_payouts), 2) if miss_1_payouts else 0.0,
                        "min_net_profit": round(min(miss_1_payouts) - cost, 2) if miss_1_payouts else -cost,
                    },
                    "miss_2": {
                        "min_payout": round(min(miss_2_payouts), 2) if miss_2_payouts else 0.0,
                        "max_payout": round(max(miss_2_payouts), 2) if miss_2_payouts else 0.0,
                        "avg_payout": round(sum(miss_2_payouts) / len(miss_2_payouts), 2) if miss_2_payouts else 0.0,
                        "min_net_profit": round(min(miss_2_payouts) - cost, 2) if miss_2_payouts else -cost,
                    } if defn["tolerance_matches"] >= 2 else None,
                },
                "sub_bets_summary": {
                    f"{sub_len}_leg_count": len([sb for sb in sub_bets if sb["leg_count"] == sub_len])
                    for sub_len in defn["sub_lengths"]
                },
            })

    return sorted(system_bets, key=lambda item: item["ev_low"], reverse=True)


def _empty_report(now, bankroll, policy, rejections):
    return {
        "kind": "betting_report",
        "generated_at": utc_iso(now),
        "policy": policy,
        "evaluations": [],
        "recommendations": [],
        "system_bets": [],
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
    max_total_exposure=0.50,
    include_parlays=False,
    max_divergence_ratio=2.0,
    max_single_odds=70.0,
    all_eligible=False,
    max_match_repetition=None,
    include_system_bets=False,
    system_types=None,
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
        "max_divergence_ratio": max_divergence_ratio,
        "max_single_odds": max_single_odds,
        "all_eligible": bool(all_eligible),
        "kelly_fraction": 0.5,
        "max_single_position": 0.05,
        "max_total_exposure": max_total_exposure,
        "unit": float(unit),
        "parlays_enabled": bool(include_parlays),
        "max_match_repetition": max_match_repetition,
        "include_system_bets": bool(include_system_bets),
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
    single_candidates = []
    parlay_candidates_by_match = {}
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
            max_divergence_ratio=max_divergence_ratio,
            max_single_odds=max_single_odds,
        )
        evaluations.extend(match_evaluations)
        eligible = [item for item in match_evaluations if item["eligible"]]
        if eligible:
            eligible_by_match.extend(eligible)
            # Best eligible option per market category per match for parlay pool
            # (enables cross-market mixed parlays: HAD/HHAD, TTG, CRS across matches)
            match_parlay_picks = {}
            for item in eligible:
                cat = market_category(item.get("market", ""))
                current_best = match_parlay_picks.get(cat)
                item_score = (item.get("sharpe_ratio", item["ev_low"]), item["ev_low"])
                if current_best is None or item_score > (current_best.get("sharpe_ratio", current_best["ev_low"]), current_best["ev_low"]):
                    match_parlay_picks[cat] = item
            parlay_candidates_by_match[match_id] = list(match_parlay_picks.values())

            # Single bet availability check
            single_eligible = [item for item in eligible if item.get("single_allowed", True)]
            non_single_eligible = [item for item in eligible if not item.get("single_allowed", True)]

            for item in non_single_eligible:
                market_tag = item["market"].upper()
                if item.get("goal_line") is not None:
                    market_tag += f"({item['goal_line']:+d})"
                rejections.append(
                    {
                        "match_id": match_id,
                        "reason": "single_betting_not_allowed",
                        "detail": f"{item['match_num']} {item['home_team']} vs {item['away_team']} {market_tag}-{item['option']}（官方未开通单关固定奖，仅限串关投注，已转入串关池）",
                        "bet_id": item["bet_id"],
                        "ev_low": item["ev_low"],
                        "odds": item["odds"],
                    }
                )

            if single_eligible:
                if all_eligible:
                    single_candidates.extend(single_eligible)
                else:
                    # Retain best eligible single option per market category per match
                    # (allows HAD/HHAD, TTG, and CRS recommendations without mutual suppression)
                    match_single_picks = {}
                    for item in single_eligible:
                        cat = market_category(item.get("market", ""))
                        current_best = match_single_picks.get(cat)
                        item_score = (item.get("sharpe_ratio", item["ev_low"]), item["ev_low"])
                        if current_best is None or item_score > (current_best.get("sharpe_ratio", current_best["ev_low"]), current_best["ev_low"]):
                            match_single_picks[cat] = item
                    single_candidates.extend(match_single_picks.values())
        else:
            rejections.append({"match_id": match_id, "reason": "no_selection_above_ev_threshold"})

    candidates = sorted(
        single_candidates,
        key=lambda item: (
            item.get("sharpe_ratio", item["ev_low"]),
            item["ev_low"],
        ),
        reverse=True,
    )
    if all_eligible:
        parlay_pool = sorted(
            eligible_by_match,
            key=lambda item: (
                item.get("sharpe_ratio", item["ev_low"]),
                item["ev_low"],
            ),
            reverse=True,
        )
    else:
        pool_picks = [pick for picks in parlay_candidates_by_match.values() for pick in picks]
        parlay_pool = sorted(
            pool_picks,
            key=lambda item: (
                item.get("sharpe_ratio", item["ev_low"]),
                item["ev_low"],
            ),
            reverse=True,
        )

    if include_parlays:
        legs_to_generate = [2, 4] if include_parlays is True else (
            [include_parlays] if isinstance(include_parlays, int) else list(include_parlays)
        )
        unique_matches_count = len(set(item["match_id"] for item in parlay_pool))
        for leg_count in legs_to_generate:
            if leg_count <= unique_matches_count:
                candidates.extend(
                    build_multi_leg_parlays(
                        parlay_pool,
                        leg_count=leg_count,
                        min_ev_low=min_ev_low,
                        max_match_repetition=max_match_repetition,
                    )[:3]
                )

    system_bets = []
    if include_system_bets and len(parlay_pool) >= 3:
        types_to_use = system_types if system_types else ["3_in_4", "4_in_11"]
        system_bets = build_system_bets(
            parlay_pool,
            system_types=types_to_use,
            unit=unit,
            min_ev_low=min_ev_low,
        )

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
        "system_bets": system_bets,
        "rejections": rejections,
        "bankroll": bankroll_summary,
    }


def _selection_label(recommendation):
    rec_type = recommendation.get("type", "")
    if rec_type.endswith("_leg_parlay"):
        legs = recommendation.get("leg_labels") or recommendation.get("legs", [])
        if rec_type == "two_leg_parlay":
            prefix = "2串1"
        else:
            n = rec_type.split("_")[0]
            prefix = f"{n}串1"
        if recommendation.get("is_mixed") and recommendation.get("mix_label"):
            return f"{prefix}（混合过关·{recommendation['mix_label']}）：" + " × ".join(legs)
        return f"{prefix}：" + " × ".join(legs)
    market = recommendation["market"].upper()
    option = recommendation["option"]
    if recommendation.get("goal_line") is not None:
        market = f"{market}({recommendation['goal_line']:+d})"
    return f"【单关】{recommendation['match_num']} {recommendation['home_team']} vs {recommendation['away_team']} {market}-{option}"


def render_markdown(report, title_date=None):
    title_date = title_date or report["generated_at"][:10]
    lines = [
        f"# 竞彩足球投注分析（{title_date}）",
        "",
        f"- 赔率快照：{report.get('odds_snapshot', {}).get('fetched_at', '不可用')}",
        f"- 概率折减：{report['policy']['probability_haircut']:.1%}",
        f"- 保守 EV 门槛：{report['policy']['min_ev_low']:.1%}",
        f"- 市场分歧度上限：{report['policy'].get('max_divergence_ratio', 2.0):.1f}x",
        f"- 单关赔率上限：{report['policy'].get('max_single_odds', 70.0):.1f}",
        f"- 仓位总敞口上限：{report['policy'].get('max_total_exposure', 0.50):.0%}",
        "",
        "## 投注建议",
        "",
    ]
    if not report["recommendations"]:
        lines.append("当前没有满足数据完整性、赔率时效和保守 EV 门槛的投注建议。")
    else:
        singles = [
            r for r in report["recommendations"] if not str(r.get("type", "")).endswith("_leg_parlay")
        ]
        parlays_2 = [r for r in report["recommendations"] if r.get("type") == "two_leg_parlay"]
        parlays_4 = [r for r in report["recommendations"] if r.get("type") == "4_leg_parlay"]
        other_parlays = [
            r
            for r in report["recommendations"]
            if str(r.get("type", "")).endswith("_leg_parlay")
            and r.get("type") not in ("two_leg_parlay", "4_leg_parlay")
        ]

        def _render_table(items, col_name="选项"):
            res = [
                f"| {col_name} | 实时赔率 | 模型概率 | 保守概率 | 保守 EV | 凯利比例 | 金额 |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
            for item in items:
                res.append(
                    f"| {_selection_label(item)} | {item['odds']:.2f} | {item['probability']:.1%} | "
                    f"{item['conservative_probability']:.1%} | {item['ev_low']:+.1%} | "
                    f"{item['kelly_fraction']:.1%} | {item['stake']:.0f} 元 |"
                )
            return res

        single_filtered = [
            rej for rej in report.get("rejections", []) if rej.get("reason") == "single_betting_not_allowed"
        ]
        has_subsections = bool(
            parlays_2 or parlays_4 or other_parlays or single_filtered or singles
        )
        if has_subsections:
            lines.extend(["### 单关投注建议", ""])
            singles_had = [s for s in singles if s.get("market") in ("had", "hhad")]
            singles_ttg = [s for s in singles if s.get("market") == "ttg"]
            singles_crs = [s for s in singles if s.get("market") == "crs"]

            # Sub-category 1: HAD / HHAD
            lines.extend(["#### 胜平负 / 让球胜平负单关", ""])
            if singles_had:
                lines.extend(_render_table(singles_had, "胜平负/让球单场建议"))
                lines.append("")
            else:
                lines.append("当前暂无官方开放单关固定奖且满足保守 EV 门槛的胜平负/让球选项。")
                lines.append("")

            # Sub-category 2: TTG
            lines.extend(["#### 总进球数单关 (TTG)", ""])
            if singles_ttg:
                lines.extend(_render_table(singles_ttg, "总进球数单场建议"))
                lines.append("")
            else:
                lines.append("当前暂无官方开放单关固定奖且满足保守 EV 门槛的总进球数选项。")
                lines.append("")

            # Sub-category 3: CRS
            lines.extend(["#### 比分单关 (CRS)", ""])
            if singles_crs:
                lines.extend(_render_table(singles_crs, "比分单场建议"))
                lines.append("")
            else:
                lines.append("当前暂无官方开放单关固定奖且满足保守 EV 门槛的比分选项。")
                lines.append("")

            if single_filtered:
                lines.append("> [!NOTE]")
                lines.append("> **单关销售限制说明**：以下优质选项达到保守 EV 门槛，但由于体彩官方未开通单关固定奖销售（仅限串关投注），已按规则自动从单关建议中过滤，并已优先转入下方 **2 串 1** 与 **4 串 1** 混合过关方案中：")
                for rej in single_filtered:
                    lines.append(f"> - {rej['detail']}")
                lines.append("")

            if parlays_2:
                lines.extend(["### 2 串 1 混合过关建议", ""])
                lines.extend(_render_table(parlays_2, "2串1组合方案"))
                lines.append("")
            if parlays_4:
                lines.extend(["### 4 串 1 混合过关建议", ""])
                lines.extend(_render_table(parlays_4, "4串1组合方案"))
                lines.append("")
            if other_parlays:
                lines.extend(["### 其他串关建议", ""])
                lines.extend(_render_table(other_parlays, "组合方案"))
                lines.append("")
            if report.get("system_bets"):
                lines.extend([
                    "### 容错系统过关建议（System Bets / 多串过关）",
                    "",
                    "> [!TIP]",
                    "> **多串容错机制**：采用中国体育彩票官方“多串过关”组合体系（如 3串4、4串11），自动将注单拆解为子串关。当出现 1~2 场意外红牌或爆冷时，仍能命中部分子串关以保本或挽回损失，有效防止单场意外导致全单覆没。",
                    "",
                    "| 方案名称 | 容错场数 | 包含场次与玩法 | 注数 | 单倍投注 | 全中回报 (ROI) | 错 1 场最低返还 | 错 2 场最低返还 | 保守 EV |",
                    "|---|---:|---|---:|---:|---:|---:|---:|---:|",
                ])
                for sb in report["system_bets"]:
                    legs_str = " + ".join(sb["leg_labels"])
                    all_hit = sb["scenarios"]["all_hit"]
                    m1 = sb["scenarios"]["miss_1"]
                    m2 = sb["scenarios"].get("miss_2")
                    m2_str = f"{m2['min_payout']:.2f} 元" if m2 else "—"
                    lines.append(
                        f"| {sb['system_name']} | 容错 {sb['tolerance_matches']} 场 | {legs_str} | "
                        f"{sb['bet_count']} 注 | {sb['cost']:.0f} 元 | "
                        f"{all_hit['payout']:.2f} 元 ({all_hit['roi']:.1f}x) | "
                        f"{m1['min_payout']:.2f} 元 | {m2_str} | {sb['ev_low']:+.1%} |"
                    )
                lines.append("")
        else:
            lines.extend(_render_table(report["recommendations"]))
            if report.get("system_bets"):
                lines.extend([
                    "",
                    "### 容错系统过关建议（System Bets / 多串过关）",
                    "",
                    "> [!TIP]",
                    "> **多串容错机制**：采用中国体育彩票官方“多串过关”组合体系（如 3串4、4串11），自动将注单拆解为子串关。当出现 1~2 场意外红牌或爆冷时，仍能命中部分子串关以保本或挽回损失，有效防止单场意外导致全单覆没。",
                    "",
                    "| 方案名称 | 容错场数 | 包含场次与玩法 | 注数 | 单倍投注 | 全中回报 (ROI) | 错 1 场最低返还 | 错 2 场最低返还 | 保守 EV |",
                    "|---|---:|---|---:|---:|---:|---:|---:|---:|",
                ])
                for sb in report["system_bets"]:
                    legs_str = " + ".join(sb["leg_labels"])
                    all_hit = sb["scenarios"]["all_hit"]
                    m1 = sb["scenarios"]["miss_1"]
                    m2 = sb["scenarios"].get("miss_2")
                    m2_str = f"{m2['min_payout']:.2f} 元" if m2 else "—"
                    lines.append(
                        f"| {sb['system_name']} | 容错 {sb['tolerance_matches']} 场 | {legs_str} | "
                        f"{sb['bet_count']} 注 | {sb['cost']:.0f} 元 | "
                        f"{all_hit['payout']:.2f} 元 ({all_hit['roi']:.1f}x) | "
                        f"{m1['min_payout']:.2f} 元 | {m2_str} | {sb['ev_low']:+.1%} |"
                    )
                lines.append("")
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

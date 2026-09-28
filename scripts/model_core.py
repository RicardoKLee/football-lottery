#!/usr/bin/env python3

import math
from dataclasses import asdict, dataclass

from contracts import (
    normalize_name,
    parse_datetime,
    utc_iso,
    validate_model_prediction,
)

MODEL_NAME = "football-elo-poisson"
COMPETITION_NAMES = {
    "PL": "Premier League",
    "PD": "Primera Division",
    "BL1": "Bundesliga",
    "SA": "Serie A",
    "FL1": "Ligue 1",
}
SUPPORTED_COMPETITIONS = COMPETITION_NAMES


class ModelDataError(ValueError):
    pass


class TeamResolutionError(ModelDataError):
    pass


@dataclass(frozen=True)
class ModelParameters:
    profile: str = "club-baseline"
    initial_elo: float = 1500.0
    elo_k_factor: float = 20.0
    home_advantage_elo: float = 60.0
    form_window: int = 10
    form_decay: float = 0.85
    shrinkage_matches: float = 5.0
    min_team_matches: int = 5
    max_goals: int = 10
    elo_goal_divisor: float = 1600.0
    calibration_status: str = "baseline_pending_walk_forward"

    def __post_init__(self):
        if self.elo_k_factor <= 0 or self.form_window <= 0 or self.max_goals < 6:
            raise ValueError("Invalid model parameters")
        if not 0 < self.form_decay <= 1:
            raise ValueError("form_decay must be in (0, 1]")
        if self.shrinkage_matches < 0 or self.min_team_matches < 0:
            raise ValueError("Match counts cannot be negative")


def normalize_history_match(raw):
    from history_adapter import normalize_history_record

    try:
        return normalize_history_record(
            raw, "normalized-input", raw.get("context", {}) if isinstance(raw, dict) else {}
        )
    except ValueError as exc:
        raise ModelDataError(str(exc)) from exc


def finished_matches_before(history_matches, kickoff=None):
    cutoff = parse_datetime(kickoff) if kickoff else None
    normalized = []
    for raw in history_matches:
        if not isinstance(raw, dict):
            raise ModelDataError("Every history item must be an object")
        match = normalize_history_match(raw)
        if cutoff and parse_datetime(match["kickoff_utc"]) >= cutoff:
            continue
        normalized.append(match)
    if not normalized:
        raise ModelDataError("no_usable_history")
    return sorted(normalized, key=lambda item: parse_datetime(item["kickoff_utc"]))


def collect_teams(history_matches):
    teams = {}
    for match in finished_matches_before(history_matches):
        for side in ("home_team", "away_team"):
            team = match[side]
            existing = teams.setdefault(
                team["team_id"],
                {"team_id": team["team_id"], "name": team["name"], "aliases": []},
            )
            for alias in [team["name"], *team.get("aliases", [])]:
                if alias and alias not in existing["aliases"]:
                    existing["aliases"].append(alias)
    return teams


def resolve_team(query, teams, aliases=None):
    aliases = aliases or {}
    query_text = str(query).strip()
    if query_text in teams:
        return teams[query_text]
    alias_target = aliases.get(query_text) or aliases.get(normalize_name(query_text))
    if alias_target is not None and str(alias_target) in teams:
        return teams[str(alias_target)]
    normalized_query = normalize_name(query_text)
    candidates = []
    for team in teams.values():
        values = [team["name"], *team.get("aliases", [])]
        if any(normalize_name(value) == normalized_query for value in values):
            candidates.append(team)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        ids = ", ".join(sorted(team["team_id"] for team in candidates))
        raise TeamResolutionError(f"Ambiguous team {query!r}; candidate IDs: {ids}")
    raise TeamResolutionError(f"Unknown team: {query!r}; use a provider team ID or exact alias")


def expected_home_result(home_elo, away_elo, home_advantage_elo=60.0):
    difference = float(home_elo) + float(home_advantage_elo) - float(away_elo)
    return 1.0 / (1.0 + 10.0 ** (-difference / 400.0))


def build_elo_ratings(
    history_matches,
    home_advantage_elo=60.0,
    k_factor=20.0,
    initial_elo=1500.0,
    kickoff=None,
):
    ratings = {}
    counts = {}
    for match in finished_matches_before(history_matches, kickoff=kickoff):
        home_id = match["home_team"]["team_id"]
        away_id = match["away_team"]["team_id"]
        home_elo = ratings.setdefault(home_id, float(initial_elo))
        away_elo = ratings.setdefault(away_id, float(initial_elo))
        counts.setdefault(home_id, 0)
        counts.setdefault(away_id, 0)
        if match["home_score"] > match["away_score"]:
            actual_home = 1.0
        elif match["home_score"] == match["away_score"]:
            actual_home = 0.5
        else:
            actual_home = 0.0
        match_context = match.get("context") if isinstance(match.get("context"), dict) else {}
        advantage = 0.0 if match_context.get("venue") == "neutral" else home_advantage_elo
        expected_home = expected_home_result(home_elo, away_elo, advantage)
        change = float(k_factor) * (actual_home - expected_home)
        ratings[home_id] = home_elo + change
        ratings[away_id] = away_elo - change
        counts[home_id] += 1
        counts[away_id] += 1
    return ratings, counts


def poisson_probability(goals, expected_goals):
    if goals < 0 or expected_goals <= 0:
        return 0.0
    return math.exp(-expected_goals) * expected_goals**goals / math.factorial(goals)


def generate_score_grid(home_expected_goals, away_expected_goals, max_goals=10):
    if home_expected_goals <= 0 or away_expected_goals <= 0:
        raise ModelDataError("Expected goals must be positive")
    grid = {}
    for home_goals in range(max_goals + 1):
        for away_goals in range(max_goals + 1):
            grid[(home_goals, away_goals)] = poisson_probability(
                home_goals, home_expected_goals
            ) * poisson_probability(away_goals, away_expected_goals)
    total = sum(grid.values())
    if total <= 0:
        raise ModelDataError("Score grid has zero probability")
    return {score: probability / total for score, probability in grid.items()}


def _team_form(matches, team_id, window, decay):
    selected = []
    for match in reversed(matches):
        if team_id in {
            match["home_team"]["team_id"],
            match["away_team"]["team_id"],
        }:
            selected.append(match)
            if len(selected) >= window:
                break
    weighted_for = 0.0
    weighted_against = 0.0
    total_weight = 0.0
    for index, match in enumerate(selected):
        weight = decay**index
        if match["home_team"]["team_id"] == team_id:
            goals_for, goals_against = match["home_score"], match["away_score"]
        else:
            goals_for, goals_against = match["away_score"], match["home_score"]
        weighted_for += weight * goals_for
        weighted_against += weight * goals_against
        total_weight += weight
    return {
        "matches": len(selected),
        "weight": total_weight,
        "goals_for": weighted_for / total_weight if total_weight else None,
        "goals_against": weighted_against / total_weight if total_weight else None,
        "last_match_utc": selected[0]["kickoff_utc"] if selected else None,
    }


def _summarize_grid(grid):
    had = {"H": 0.0, "D": 0.0, "A": 0.0}
    ttg = {f"s{goals}": 0.0 for goals in range(8)}
    score = {}
    for (home_goals, away_goals), probability in grid.items():
        score[f"{home_goals}-{away_goals}"] = probability
        if home_goals > away_goals:
            had["H"] += probability
        elif home_goals == away_goals:
            had["D"] += probability
        else:
            had["A"] += probability
        total_goals = home_goals + away_goals
        key = f"s{total_goals}" if total_goals <= 6 else "s7"
        ttg[key] += probability
    return had, score, ttg


def _shrunk_ratio(value, weight, baseline, shrinkage_matches):
    if baseline <= 0:
        return 1.0
    observed_total = (value if value is not None else baseline) * weight
    numerator = observed_total + baseline * shrinkage_matches
    denominator = weight + shrinkage_matches
    return (numerator / denominator) / baseline if denominator else 1.0


def create_prediction(history_matches, match, data_snapshot, parameters=None):
    from dataclasses import replace
    from match_context import context_reasons, sample_pool_reasons

    target_context = match.get("context") if isinstance(match.get("context"), dict) else {}
    team_type = target_context.get("team_type")
    default_profile = "national-baseline" if team_type == "national" else "club-baseline"
    if parameters is None:
        parameters = ModelParameters(profile=default_profile)
    elif parameters.profile == "club-baseline" and default_profile == "national-baseline":
        parameters = replace(parameters, profile=default_profile)

    competition_code = str(match.get("competition_code", "")).strip()
    if not competition_code:
        raise ModelDataError("competition_code is required")
    competition_name = str(match.get("competition_name") or COMPETITION_NAMES.get(competition_code, competition_code))

    kickoff = parse_datetime(match.get("kickoff_utc"))
    finished = finished_matches_before(history_matches, kickoff=kickoff)
    if not finished:
        raise ModelDataError("No finished league matches are available before kickoff")

    home_team = match.get("home_team") or {}
    away_team = match.get("away_team") or {}
    home_id = str(home_team.get("team_id", ""))
    away_id = str(away_team.get("team_id", ""))
    if not home_id or not away_id or home_id == away_id:
        raise ModelDataError("Upcoming match requires two distinct stable team IDs")

    total_home_goals = sum(item["home_score"] for item in finished)
    total_away_goals = sum(item["away_score"] for item in finished)
    league_team_average = (total_home_goals + total_away_goals) / (2.0 * len(finished))
    if league_team_average <= 0:
        raise ModelDataError("Historical league goal average is zero")

    if target_context.get("venue") == "neutral":
        league_home_average = league_away_average = league_team_average
        target_advantage = 0.0
    else:
        league_home_average = total_home_goals / len(finished)
        league_away_average = total_away_goals / len(finished)
        target_advantage = parameters.home_advantage_elo

    ratings, counts = build_elo_ratings(
        finished,
        home_advantage_elo=parameters.home_advantage_elo,
        k_factor=parameters.elo_k_factor,
        initial_elo=parameters.initial_elo,
    )
    home_elo = ratings.get(home_id, parameters.initial_elo)
    away_elo = ratings.get(away_id, parameters.initial_elo)
    home_form = _team_form(finished, home_id, parameters.form_window, parameters.form_decay)
    away_form = _team_form(finished, away_id, parameters.form_window, parameters.form_decay)

    home_attack = _shrunk_ratio(
        home_form["goals_for"], home_form["weight"], league_team_average, parameters.shrinkage_matches
    )
    home_defence = _shrunk_ratio(
        home_form["goals_against"], home_form["weight"], league_team_average, parameters.shrinkage_matches
    )
    away_attack = _shrunk_ratio(
        away_form["goals_for"], away_form["weight"], league_team_average, parameters.shrinkage_matches
    )
    away_defence = _shrunk_ratio(
        away_form["goals_against"], away_form["weight"], league_team_average, parameters.shrinkage_matches
    )

    neutral_elo_factor = 10.0 ** ((home_elo - away_elo) / parameters.elo_goal_divisor)
    neutral_elo_factor = max(0.75, min(1.33, neutral_elo_factor))
    home_expected_goals = league_home_average * home_attack * away_defence * neutral_elo_factor
    away_expected_goals = league_away_average * away_attack * home_defence / neutral_elo_factor
    home_expected_goals = max(0.20, min(4.50, home_expected_goals))
    away_expected_goals = max(0.20, min(4.50, away_expected_goals))

    grid = generate_score_grid(home_expected_goals, away_expected_goals, parameters.max_goals)
    had, score, ttg = _summarize_grid(grid)

    missing_data = []
    if counts.get(home_id, 0) < parameters.min_team_matches:
        missing_data.append("insufficient_home_history")
    if counts.get(away_id, 0) < parameters.min_team_matches:
        missing_data.append("insufficient_away_history")

    if isinstance(target_context, dict) and target_context:
        try:
            missing_data.extend(context_reasons(target_context))
        except ValueError:
            missing_data.append("context_unknown")
    else:
        missing_data.append("context_unknown")

    provenance_status = data_snapshot.get("provenance_status")
    if provenance_status != "verified":
        missing_data.append("provenance_unverified")

    sample_pool = data_snapshot.get("sample_pool")
    if isinstance(sample_pool, dict) and sample_pool:
        missing_data.extend(sample_pool_reasons(finished, match, sample_pool))
    else:
        missing_data.append("sample_pool_invalid")

    missing_data = list(dict.fromkeys(missing_data))

    prediction = {
        "kind": "model_prediction",
        "model": {
            "name": MODEL_NAME,
            "parameters": asdict(parameters),
        },
        "match": {
            "match_id": str(match.get("match_id") or f"{competition_code}:{home_id}:{away_id}:{kickoff.date()}"),
            "lottery_match_id": match.get("lottery_match_id"),
            "competition_code": competition_code,
            "competition_name": competition_name,
            "season": str(match.get("season", "unknown")),
            "kickoff_utc": utc_iso(kickoff),
            "context": target_context,
            "home_team": {
                "team_id": home_id,
                "name": str(home_team.get("name") or home_id),
                "aliases": list(home_team.get("aliases") or []),
            },
            "away_team": {
                "team_id": away_id,
                "name": str(away_team.get("name") or away_id),
                "aliases": list(away_team.get("aliases") or []),
            },
        },
        "data_snapshot": {
            "provider": str(data_snapshot.get("provider", "unknown")),
            "source_url": str(data_snapshot.get("source_url", "unknown")),
            "fetched_at": utc_iso(data_snapshot.get("fetched_at")),
            "provenance_status": str(data_snapshot.get("provenance_status", "unverified")),
            "sample_pool": sample_pool if isinstance(sample_pool, dict) else {},
        },
        "inputs": {
            "history_match_count": len(finished),
            "league_home_goals_average": league_home_average,
            "league_away_goals_average": league_away_average,
            "home_elo": home_elo,
            "away_elo": away_elo,
            "elo_home_expectation": expected_home_result(
                home_elo, away_elo, target_advantage
            ),
            "home_form": home_form,
            "away_form": away_form,
            "home_attack_ratio": home_attack,
            "home_defence_ratio": home_defence,
            "away_attack_ratio": away_attack,
            "away_defence_ratio": away_defence,
            "sample_pool_composition": sample_pool.get("competition_codes", []) if isinstance(sample_pool, dict) else [],
            "baseline_limitation": "baseline_pending_walk_forward",
        },
        "expected_goals": {"home": home_expected_goals, "away": away_expected_goals},
        "probabilities": {"had": had, "score": score, "ttg": ttg},
        "quality": {
            "status": "insufficient" if missing_data else "sufficient",
            "missing_data": missing_data,
            "home_history_matches": counts.get(home_id, 0),
            "away_history_matches": counts.get(away_id, 0),
        },
    }
    return validate_model_prediction(prediction)

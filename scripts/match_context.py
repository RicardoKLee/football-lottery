"""Provider-qualified identities and explicit football context, without defaults."""
import re

CONTEXT_ENUMS = {
    "team_type": ("club", "national", "unknown"),
    "competition_type": ("league", "cup", "other", "unknown"),
    "venue": ("home", "neutral", "unknown"),
    "score_basis": ("regulation", "unknown"),
}
ID_PATTERN = r"^[^\s:]+:\S+$"


def validate_context(context: dict) -> dict:
    if not isinstance(context, dict):
        raise ValueError("context must be an object")
    for key, allowed in CONTEXT_ENUMS.items():
        if context.get(key) not in allowed:
            raise ValueError(f"context.{key} must be one of {', '.join(allowed)}")
    return context


def stable_id(provider: str, entity_id: str) -> str:
    # Never strip another provider's prefix or coerce numeric IDs implicitly.
    if not isinstance(provider, str) or not re.fullmatch(r"[^\s:]+", provider):
        raise ValueError("provider must be a non-empty namespace without whitespace or colons")
    if not isinstance(entity_id, str) or not re.fullmatch(r"\S+", entity_id):
        raise ValueError("entity_id must be a non-empty string without whitespace")
    return f"{provider}:{entity_id}"


def context_reasons(context: dict) -> list:
    validate_context(context)
    return [f"{key}_unknown" for key in CONTEXT_ENUMS if context[key] == "unknown"]


def sample_pool_reasons(matches: list, target: dict, sample_pool: dict) -> list:
    """Check declared scope and pre-kickoff connectivity, not calibration.

    Inspect every row for scope violations; do not silently filter a mixed pool.
    Provider-qualified IDs remain distinct graph vertices.
    """
    from contracts import parse_datetime, validate_sample_pool

    reasons = []
    try:
        validate_sample_pool(sample_pool, "sample_pool")
    except ValueError:
        return ["sample_pool_invalid"]
    team_type = sample_pool["team_type"]
    if team_type not in ("club", "national"):
        return ["sample_pool_invalid"]
    codes = sample_pool["competition_codes"]

    def check_scope(item, prefix):
        context = item.get("context")
        actual_type = context.get("team_type") if isinstance(context, dict) else None
        valid = True
        if actual_type not in ("club", "national"):
            reasons.append(f"{prefix}_team_type_unknown")
            valid = False
        elif actual_type != team_type:
            reasons.append(f"{prefix}_team_type_mismatch")
            valid = False
        if item.get("competition_code") not in codes:
            reasons.append(f"{prefix}_competition_undeclared")
            valid = False
        return valid

    if not isinstance(target, dict):
        return ["target_invalid"]
    check_scope(target, "target")
    try:
        cutoff = parse_datetime(target.get("kickoff_utc"))
        home = target["home_team"]["team_id"]
        away = target["away_team"]["team_id"]
        if any(not isinstance(v, str) or not re.fullmatch(ID_PATTERN, v) for v in (home, away)) or home == away:
            raise ValueError("invalid target identity")
    except (ValueError, KeyError, TypeError):
        return list(dict.fromkeys(reasons + ["target_invalid"]))
    graph = {}
    for match in matches:
        if not isinstance(match, dict):
            reasons.append("invalid_history_record")
            continue
        applicable = check_scope(match, "history")
        try:
            kickoff = parse_datetime(match.get("kickoff_utc"))
            first = match["home_team"]["team_id"]
            second = match["away_team"]["team_id"]
            if any(not isinstance(v, str) or not re.fullmatch(ID_PATTERN, v) for v in (first, second)) or first == second:
                raise ValueError("invalid history identity")
        except (ValueError, KeyError, TypeError):
            reasons.append("invalid_history_record")
            continue
        if match.get("status", "FINISHED") != "FINISHED":
            reasons.append("history_not_finished")
            continue
        if applicable and kickoff < cutoff:
            graph.setdefault(first, set()).add(second)
            graph.setdefault(second, set()).add(first)
    visited, pending = set(), [home]
    while pending:
        vertex = pending.pop()
        if vertex not in visited:
            visited.add(vertex)
            pending.extend(graph.get(vertex, set()) - visited)
    if away not in visited:
        reasons.append("history_pools_disconnected")
    return list(dict.fromkeys(reasons))

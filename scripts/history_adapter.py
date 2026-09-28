"""Strict internal history contract; no unverified provider score-key mappings.

Task 1 confirms FINISHED semantics, but not regularTime key shape or added-time
coverage. Explicit normalized inputs are diagnostic only, never attestation.
"""
from copy import deepcopy
import math
import re

from contracts import parse_datetime, require_datetime, utc_iso
from match_context import ID_PATTERN, validate_context


class HistoryDataError(ValueError):
    def __init__(self, reason, rejected_records=None):
        super().__init__(reason)
        self.rejected_records = rejected_records or []


def regulation_score(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid_regulation_score")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("invalid_regulation_score")
    if value < 0 or int(value) != value:
        raise ValueError("invalid_regulation_score")
    return int(value)


def _identity(value):
    if not isinstance(value, str) or not re.fullmatch(ID_PATTERN, value):
        raise ValueError("invalid_history_identity")
    return value


def normalize_history_record(raw: dict, provider: str, context: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("invalid_history_record")
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("history_provider_missing")
    # The explicit argument may supply snapshot context, never override a row.
    row_context = raw.get("context", context)
    validate_context(row_context)
    if row_context["score_basis"] != "regulation":
        raise ValueError("regulation_score_unknown")
    if row_context["team_type"] == "unknown":
        raise ValueError("history_team_type_unknown")
    if context and row_context["team_type"] != context.get("team_type"):
        raise ValueError("history_team_type_mismatch")
    # A normalized result is finished by definition. Explicit non-final status
    # must still be rejected; provider payloads never use this default path.
    if raw.get("status", "FINISHED") != "FINISHED":
        raise ValueError("history_not_finished")
    if "home_score" not in raw or "away_score" not in raw:
        raise ValueError("regulation_score_unknown")
    home_score = regulation_score(raw["home_score"])
    away_score = regulation_score(raw["away_score"])
    competition = raw.get("competition_code")
    if not isinstance(competition, str) or not competition.strip():
        raise ValueError("history_competition_missing")
    teams = {}
    for side in ("home_team", "away_team"):
        team = raw.get(side)
        if not isinstance(team, dict):
            raise ValueError("invalid_history_team")
        _identity(team.get("team_id"))
        if not isinstance(team.get("name"), str) or not team["name"].strip():
            raise ValueError("invalid_history_team")
        teams[side] = deepcopy(team)
    if teams["home_team"]["team_id"] == teams["away_team"]["team_id"]:
        raise ValueError("history_self_match")
    require_datetime(raw, "kickoff_utc", "history")
    return {
        "match_id": _identity(raw.get("match_id")),
        "kickoff_utc": utc_iso(raw.get("kickoff_utc")),
        **teams, "home_score": home_score, "away_score": away_score,
        "competition_code": competition, "context": deepcopy(row_context),
        "provenance_status": "unverified",
        "quality_reasons": ["history_source_unverified"],
    }


def prepare_history(records: list, provider: str, context: dict) -> tuple:
    if not isinstance(records, list):
        raise HistoryDataError("invalid_history_records")
    normalized, rejected = [], []
    for raw in records:
        try:
            normalized.append(normalize_history_record(raw, provider, context))
        except ValueError as exc:
            rejected.append({"match_id": raw.get("match_id", raw.get("id"))
                             if isinstance(raw, dict) else None, "reason": str(exc)})
    if not normalized:
        raise HistoryDataError("no_usable_history", rejected)
    normalized.sort(key=lambda item: parse_datetime(item["kickoff_utc"]))
    return normalized, rejected

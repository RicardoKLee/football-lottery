#!/usr/bin/env python3

import json
import math
import os
import tempfile
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SCHEMA_VERSION = "2.0"
BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")


class ContractError(ValueError):
    pass


def parse_datetime(value, default_timezone=BUSINESS_TIMEZONE):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ContractError(f"Invalid datetime: {value}") from exc
    else:
        raise ContractError(f"Datetime is required, got: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_timezone)
    return parsed.astimezone(timezone.utc)


def utc_iso(value):
    return parse_datetime(value).isoformat().replace("+00:00", "Z")


def utc_now():
    return datetime.now(timezone.utc)


def normalize_name(value):
    if not isinstance(value, str):
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def require_mapping(value, path):
    if not isinstance(value, dict):
        raise ContractError(f"{path} must be an object")
    return value


def require_string(mapping, key, path):
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path}.{key} must be a non-empty string")
    return value


def validate_probability_distribution(distribution, path, tolerance=1e-6):
    require_mapping(distribution, path)
    if not distribution:
        raise ContractError(f"{path} cannot be empty")
    total = 0.0
    for key, value in distribution.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ContractError(f"{path}.{key} must be numeric")
        if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
            raise ContractError(f"{path}.{key} must be between 0 and 1")
        total += float(value)
    if abs(total - 1.0) > tolerance:
        raise ContractError(f"{path} must sum to 1, got {total}")
    return distribution


def validate_team(team, path):
    require_mapping(team, path)
    require_string(team, "team_id", path)
    require_string(team, "name", path)
    aliases = team.get("aliases")
    if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
        raise ContractError(f"{path}.aliases must be an array of strings")
    return team


def validate_model_prediction(prediction):
    require_mapping(prediction, "prediction")
    if prediction.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("prediction.schema_version must be 2.0")
    if prediction.get("kind") != "model_prediction":
        raise ContractError("prediction.kind must be model_prediction")

    model = require_mapping(prediction.get("model"), "prediction.model")
    require_string(model, "name", "prediction.model")
    require_string(model, "version", "prediction.model")
    require_mapping(model.get("parameters"), "prediction.model.parameters")

    match = require_mapping(prediction.get("match"), "prediction.match")
    require_string(match, "match_id", "prediction.match")
    competition_code = require_string(match, "competition_code", "prediction.match")
    if competition_code not in {"PL", "PD", "BL1", "SA", "FL1"}:
        raise ContractError(f"Unsupported competition_code: {competition_code}")
    parse_datetime(require_string(match, "kickoff_utc", "prediction.match"))
    validate_team(match.get("home_team"), "prediction.match.home_team")
    validate_team(match.get("away_team"), "prediction.match.away_team")

    snapshot = require_mapping(prediction.get("data_snapshot"), "prediction.data_snapshot")
    require_string(snapshot, "provider", "prediction.data_snapshot")
    require_string(snapshot, "source_url", "prediction.data_snapshot")
    parse_datetime(require_string(snapshot, "fetched_at", "prediction.data_snapshot"))

    probabilities = require_mapping(prediction.get("probabilities"), "prediction.probabilities")
    had = validate_probability_distribution(probabilities.get("had"), "prediction.probabilities.had")
    if set(had) != {"H", "D", "A"}:
        raise ContractError("prediction.probabilities.had must contain H, D and A")
    validate_probability_distribution(probabilities.get("score"), "prediction.probabilities.score")
    validate_probability_distribution(probabilities.get("ttg"), "prediction.probabilities.ttg")

    quality = require_mapping(prediction.get("quality"), "prediction.quality")
    if quality.get("status") not in {"sufficient", "insufficient"}:
        raise ContractError("prediction.quality.status must be sufficient or insufficient")
    if not isinstance(quality.get("missing_data"), list):
        raise ContractError("prediction.quality.missing_data must be an array")
    return prediction


def validate_odds_snapshot(snapshot):
    require_mapping(snapshot, "snapshot")
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("snapshot.schema_version must be 2.0")
    if snapshot.get("kind") != "odds_snapshot":
        raise ContractError("snapshot.kind must be odds_snapshot")
    require_string(snapshot, "provider", "snapshot")
    require_string(snapshot, "source_url", "snapshot")
    if snapshot.get("source_mode") not in {"live", "file"}:
        raise ContractError("snapshot.source_mode must be live or file")
    parse_datetime(require_string(snapshot, "fetched_at", "snapshot"))
    matches = snapshot.get("matches")
    if not isinstance(matches, list):
        raise ContractError("snapshot.matches must be an array")
    for index, match in enumerate(matches):
        path = f"snapshot.matches[{index}]"
        require_mapping(match, path)
        require_string(match, "match_id", path)
        parse_datetime(require_string(match, "kickoff_utc", path))
        parse_datetime(require_string(match, "cutoff_utc", path))
        parse_datetime(require_string(match, "odds_observed_at", path))
        require_string(match, "sale_status", path)
        if not isinstance(match.get("is_available"), bool):
            raise ContractError(f"{path}.is_available must be boolean")
        reasons = match.get("availability_reasons")
        if not isinstance(reasons, list) or any(not isinstance(reason, str) for reason in reasons):
            raise ContractError(f"{path}.availability_reasons must be an array of strings")
        home_team = require_mapping(match.get("home_team"), f"{path}.home_team")
        away_team = require_mapping(match.get("away_team"), f"{path}.away_team")
        require_string(home_team, "name", f"{path}.home_team")
        require_string(away_team, "name", f"{path}.away_team")
        require_mapping(match.get("odds"), f"{path}.odds")
    return snapshot


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Unable to load JSON from {path}: {exc}") from exc


def write_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise

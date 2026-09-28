#!/usr/bin/env python3

import json
import math
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from match_context import ID_PATTERN, validate_context

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


def require_datetime(mapping, key, path):
    """Validate JSON date-time without the boundary parser's timezone defaults."""
    value = require_string(mapping, key, path)
    # RFC 3339 syntax: explicit seconds and timezone, ASCII digits, no trimming.
    pattern = (r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt]"
               r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?"
               r"(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])")
    if not re.fullmatch(pattern, value):
        raise ContractError(f"{path}.{key} must be a date-time with explicit timezone")
    try:
        return datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{path}.{key} is an invalid date-time: {value}") from exc


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


def require_enum(mapping, key, allowed, path):
    value = mapping.get(key)
    if value not in allowed:
        raise ContractError(f"{path}.{key} must be one of {', '.join(allowed)}")
    return value


def require_stable_id(mapping, key, path):
    value = require_string(mapping, key, path)
    if not re.fullmatch(ID_PATTERN, value):
        raise ContractError(f"{path}.{key} must be a provider-qualified ID")
    return value


def validate_sample_pool(pool, path):
    require_mapping(pool, path)
    require_string(pool, "pool_id", path)
    require_enum(pool, "team_type", ("club", "national", "unknown"), path)
    codes = pool.get("competition_codes")
    if not isinstance(codes, list) or not codes or any(
        not isinstance(code, str) or not code.strip() for code in codes
    ):
        raise ContractError(f"{path}.competition_codes must be a non-empty array of non-empty strings")
    return pool


def validate_team(team, path):
    require_mapping(team, path)
    require_stable_id(team, "team_id", path)
    require_string(team, "name", path)
    aliases = team.get("aliases")
    if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
        raise ContractError(f"{path}.aliases must be an array of strings")
    return team


def validate_model_prediction(prediction):
    require_mapping(prediction, "prediction")
    if prediction.get("kind") != "model_prediction":
        raise ContractError("prediction.kind must be model_prediction")

    model = require_mapping(prediction.get("model"), "prediction.model")
    require_string(model, "name", "prediction.model")
    require_mapping(model.get("parameters"), "prediction.model.parameters")

    match = require_mapping(prediction.get("match"), "prediction.match")
    require_stable_id(match, "match_id", "prediction.match")
    require_string(match, "competition_code", "prediction.match")
    context = require_mapping(match.get("context"), "prediction.match.context")
    try:
        validate_context(context)
    except ValueError as exc:
        raise ContractError(f"prediction.match.{exc}") from exc
    require_datetime(match, "kickoff_utc", "prediction.match")
    validate_team(match.get("home_team"), "prediction.match.home_team")
    validate_team(match.get("away_team"), "prediction.match.away_team")

    snapshot = require_mapping(prediction.get("data_snapshot"), "prediction.data_snapshot")
    require_string(snapshot, "provider", "prediction.data_snapshot")
    require_string(snapshot, "source_url", "prediction.data_snapshot")
    require_datetime(snapshot, "fetched_at", "prediction.data_snapshot")
    # Structural validation only: source evidence must be checked by the adapter.
    require_enum(snapshot, "provenance_status", ("verified", "unverified"), "prediction.data_snapshot")
    validate_sample_pool(snapshot.get("sample_pool"), "prediction.data_snapshot.sample_pool")

    probabilities = require_mapping(prediction.get("probabilities"), "prediction.probabilities")
    had = validate_probability_distribution(probabilities.get("had"), "prediction.probabilities.had")
    if set(had) != {"H", "D", "A"}:
        raise ContractError("prediction.probabilities.had must contain H, D and A")
    validate_probability_distribution(probabilities.get("score"), "prediction.probabilities.score")
    validate_probability_distribution(probabilities.get("ttg"), "prediction.probabilities.ttg")

    quality = require_mapping(prediction.get("quality"), "prediction.quality")
    if quality.get("status") not in {"sufficient", "insufficient"}:
        raise ContractError("prediction.quality.status must be sufficient or insufficient")
    if not isinstance(quality.get("missing_data"), list) or any(
        not isinstance(reason, str) for reason in quality["missing_data"]
    ):
        raise ContractError("prediction.quality.missing_data must be an array")
    return prediction


def validate_odds_snapshot(snapshot):
    require_mapping(snapshot, "snapshot")
    if snapshot.get("kind") != "odds_snapshot":
        raise ContractError("snapshot.kind must be odds_snapshot")
    require_string(snapshot, "provider", "snapshot")
    require_string(snapshot, "source_url", "snapshot")
    if snapshot.get("source_mode") not in {"live", "file"}:
        raise ContractError("snapshot.source_mode must be live or file")
    require_datetime(snapshot, "fetched_at", "snapshot")
    matches = snapshot.get("matches")
    if not isinstance(matches, list):
        raise ContractError("snapshot.matches must be an array")
    for index, match in enumerate(matches):
        path = f"snapshot.matches[{index}]"
        require_mapping(match, path)
        require_stable_id(match, "match_id", path)
        listing_path = f"{path}.official_listing"
        listing = require_mapping(match.get("official_listing"), listing_path)
        require_enum(listing, "status", ("confirmed", "unknown"), listing_path)
        require_string(listing, "source_url", listing_path)
        require_string(listing, "provider_match_id", listing_path)
        require_datetime(listing, "observed_at", listing_path)
        markets = require_mapping(match.get("market_status"), f"{path}.market_status")
        for market in ("had", "hhad", "ttg", "crs"):
            require_enum(markets, market, ("open", "closed", "unknown"), f"{path}.market_status")
        require_datetime(match, "kickoff_utc", path)
        require_datetime(match, "cutoff_utc", path)
        require_datetime(match, "odds_observed_at", path)
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

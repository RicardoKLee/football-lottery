"""Synthetic internal-contract data; never evidence of provider semantics."""
from copy import deepcopy


def regular_history(team_type="club", venue="home") -> list:
    teams = [{"team_id": f"fixture:{name}", "name": name, "aliases": []}
             for name in ("Alpha", "Beta", "Gamma")]
    return [{
        "match_id": f"fixture:history-{day}",
        "kickoff_utc": f"2026-09-{day:02d}T12:00:00Z",
        "status": "FINISHED", "competition_code": "J1",
        "home_team": deepcopy(teams[(day - 1) % 3]),
        "away_team": deepcopy(teams[day % 3]),
        "home_score": 1 + day % 3, "away_score": 1,
        "context": {"team_type": team_type, "competition_type": "league",
                    "venue": venue, "score_basis": "regulation"},
        "synthetic": True,
    } for day in range(1, 13)]


def target_match(team_type="club", venue="home", competition_code="J1") -> dict:
    match = regular_history(team_type, venue)[0]
    match.update(match_id="fixture:target", kickoff_utc="2026-09-13T12:00:00Z",
                 competition_code=competition_code, status="SCHEDULED")
    del match["home_score"], match["away_score"]
    return match


def verified_snapshot() -> dict:
    """Test-only asserted verification, not a production source attestation."""
    return {"provider": "fixture", "source_url": "https://example.invalid/fixture",
            "fetched_at": "2026-09-13T10:00:00Z", "synthetic": True,
            "provenance_status": "verified",
            "sample_pool": {"pool_id": "fixture:J1", "team_type": "club",
                            "competition_codes": ["J1"]}}

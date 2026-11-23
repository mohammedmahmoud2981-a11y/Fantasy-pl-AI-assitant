from __future__ import annotations

import requests
import pandas as pd


BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"


def load_players() -> tuple[pd.DataFrame, dict[int, str], dict[int, str], list[dict]]:
    """Fetch current player, club, position, and gameweek metadata from FPL."""
    response = requests.get(
        BOOTSTRAP_URL,
        headers={"User-Agent": "FantasyIQ/0.1 (educational project)"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()

    positions = {row["id"]: row["singular_name"] for row in payload["element_types"]}
    teams = {row["id"]: row["name"] for row in payload["teams"]}
    players = pd.DataFrame(payload["elements"])
    if players.empty:
        raise ValueError("The FPL feed returned no players.")

    players["position"] = players["element_type"].map(positions).fillna("Unknown")
    players["team_name"] = players["team"].map(teams).fillna("Unknown")
    players["player"] = (players["first_name"].fillna("") + " " + players["second_name"].fillna("")).str.strip()
    players["cost_m"] = pd.to_numeric(players["now_cost"], errors="coerce").fillna(0) / 10

    numeric_columns = {
        "ep_next": "expected_points",
        "total_points": "total_points",
        "points_per_game": "points_per_game",
        "minutes": "minutes",
        "form": "form",
        "selected_by_percent": "selected_by_percent",
    }
    for source, target in numeric_columns.items():
        players[target] = pd.to_numeric(players[source], errors="coerce").fillna(0)

    return players, positions, teams, payload.get("events", [])

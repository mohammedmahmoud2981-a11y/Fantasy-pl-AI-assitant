from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://fantasy.premierleague.com/api"

def main() -> None:
    parser = argparse.ArgumentParser(description="Collect public FPL squad picks for collaborative filtering.")
    parser.add_argument("--team-ids", default=None, help="Optional comma-separated public FPL entry IDs.")
    parser.add_argument("--leaderboard-teams", type=int, default=30, help="Number of public teams to collect automatically from the overall league (10-50).")
    parser.add_argument("--league-id", type=int, default=314, help="FPL classic league ID used when --team-ids is omitted.")
    parser.add_argument("--event", type=int, default=None, help="Gameweek ID; defaults to latest finished round.")
    parser.add_argument("--rounds", type=int, default=1, help="Number of recent completed rounds to collect (1-8).")
    args = parser.parse_args()
    session = requests.Session()
    bootstrap = session.get(f"{BASE}/bootstrap-static/", timeout=20); bootstrap.raise_for_status()
    events = bootstrap.json()["events"]
    event = args.event or max((row["id"] for row in events if row.get("finished")), default=None)
    if event is None:
        raise RuntimeError("No completed gameweek is available.")
    if args.team_ids:
        team_ids = sorted(set(int(v.strip()) for v in args.team_ids.split(",") if v.strip()))
    else:
        if not 10 <= args.leaderboard_teams <= 50:
            raise ValueError("--leaderboard-teams must be between 10 and 50.")
        standings = session.get(f"{BASE}/leagues-classic/{args.league_id}/standings/?page_standings=1", timeout=20)
        standings.raise_for_status()
        team_ids = [int(row["entry"]) for row in standings.json().get("standings", {}).get("results", [])[:args.leaderboard_teams]]
        if len(team_ids) < 10:
            raise RuntimeError("Could not retrieve at least 10 teams from the public league. Try providing --team-ids.")
    if not 1 <= args.rounds <= 8:
        raise ValueError("--rounds must be between 1 and 8.")
    finished = sorted((int(row["id"]) for row in events if row.get("finished") and int(row["id"]) <= event), reverse=True)
    selected_events = finished[:args.rounds]
    records = []
    for gw in selected_events:
        for team_id in team_ids:
            response = session.get(f"{BASE}/entry/{team_id}/event/{gw}/picks/", timeout=20)
            if response.status_code == 404:
                continue
            response.raise_for_status()
            records.extend({"user_id": team_id, "player_id": pick["element"], "event": gw} for pick in response.json().get("picks", []))
    if len({row["user_id"] for row in records}) < 10:
        raise RuntimeError("Fewer than 10 teams have saved picks; provide more valid team IDs.")
    output = ROOT / "data" / "processed" / "user_player_interactions.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).drop_duplicates(["user_id", "player_id", "event"]).to_csv(output, index=False)
    print(f"Saved {len(records)} picks from {len(set(row['user_id'] for row in records))} teams across GWs {min(selected_events)}-{max(selected_events)}: {output}")

if __name__ == "__main__":
    main()

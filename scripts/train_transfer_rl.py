from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fantasyiq.features import create_grid
from fantasyiq.optimizer import optimize_squad

SOURCE = ROOT / "data/processed/player_gameweeks.csv.gz"
REPORT = ROOT / "reports/transfer_rl_metrics.json"
POSITION_MAP = {"GK": "Goalkeeper", "DEF": "Defender", "MID": "Midfielder", "FWD": "Forward"}
RNG = np.random.default_rng(42)


def trajectory(source: pd.DataFrame, season: str) -> list[dict]:
    frame = source[source.season.astype(str) == season].copy()
    if frame.empty:
        return []
    frame["season"] = frame.season.astype(str)
    frame["gameweek"] = pd.to_numeric(frame.gameweek, errors="coerce").astype(int)
    frame["player_id"] = pd.to_numeric(frame.player_id, errors="coerce").astype(int)
    frame = create_grid(frame)
    frame["position"] = frame.position.map(POSITION_MAP)
    frame["cost_m"] = pd.to_numeric(frame.value, errors="coerce") / 10
    frame["team"] = pd.to_numeric(frame.team_id, errors="coerce").fillna(-1).astype(int)
    frame["total_points"] = pd.to_numeric(frame.total_points, errors="coerce").fillna(0)
    result = []
    opening_squad = None
    opening_cost = None
    for gw in sorted(frame.gameweek.unique()):
        if gw <= 3:
            continue
        prior = frame[frame.gameweek < gw]
        latest = prior.sort_values("gameweek").groupby("player_id", as_index=False).tail(1).set_index("player_id")
        recent = prior[prior.gameweek >= gw - 3].groupby("player_id").total_points.mean().rename("expected_points")
        pool = latest.join(recent, how="inner").reset_index()
        pool = pool[pool.position.isin(POSITION_MAP.values())].dropna(subset=["cost_m", "expected_points"])
        pool = pd.concat([grp.sort_values("expected_points", ascending=False).head(60) for _, grp in pool.groupby("position")]).drop_duplicates("player_id")
        actual = frame[frame.gameweek == gw].set_index("player_id").total_points
        if opening_squad is None:
            try:
                selected = optimize_squad(pool[["player_id", "position", "team", "cost_m", "expected_points"]].rename(columns={"player_id": "id"}), 100.0)
            except ValueError:
                continue
            opening_squad = set(selected.id.astype(int))
            opening_cost = float(selected.cost_m.sum())
        result.append({"gw": int(gw), "pool": pool, "actual": actual, "initial": opening_squad,
                       "initial_cost": opening_cost})
    return result


def state_key(gw: int, gain: float, bank: float) -> tuple[int, int, int]:
    phase = min(2, max(0, (gw - 4) // 12))
    gain_bin = min(8, max(0, int(max(0, gain) / 0.5)))
    bank_bin = min(5, max(0, int(max(0, bank) / 2)))
    return phase, gain_bin, bank_bin


def swap_options(row: dict, squad: set[int], bank: float, limit: int = 3):
    pool = row["pool"].drop_duplicates("player_id").set_index("player_id")
    ids = pool.index.to_numpy(dtype=int)
    positions = pool.position.to_numpy()
    teams = pool.team.to_numpy(dtype=int)
    costs = pool.cost_m.to_numpy(dtype=float)
    projections = pool.expected_points.to_numpy(dtype=float)
    available = set(map(int, ids))
    options = []
    for out_id in squad:
        if out_id not in available: continue
        out_index = int(np.flatnonzero(ids == out_id)[0])
        rest = squad - {out_id}
        counts = {}
        for player_id in rest:
            if player_id in available:
                club = int(pool.loc[player_id, "team"])
                counts[club] = counts.get(club, 0) + 1
        mask = (positions == positions[out_index]) & ~np.isin(ids, list(squad))
        mask &= np.array([counts.get(int(team), 0) < 3 for team in teams])
        deltas = costs - costs[out_index]
        mask &= deltas <= bank + 1e-9
        gains = projections - projections[out_index]
        if not mask.any(): continue
        masked_gains = np.where(mask, gains, -np.inf)
        incoming_index = int(masked_gains.argmax())
        gain = float(gains[incoming_index])
        delta = float(deltas[incoming_index])
        options.append((gain, int(out_id), int(ids[incoming_index]), delta))
    options.sort(key=lambda item: item[0], reverse=True)
    return options[:limit]


def best_swap(row: dict, squad: set[int], bank: float):
    options = swap_options(row, squad, bank, limit=1)
    return options[0] if options else None


def run_policy(rows: list[dict], q_values=None, mode="rl") -> dict:
    squad = rows[0]["initial"].copy()
    bank = max(0.0, 100.0 - rows[0]["initial_cost"])
    score, moves, decisions = 0.0, 0, []
    for index, row in enumerate(rows):
        if index:
            options = swap_options(row, squad, bank)
            if options:
                key = state_key(row["gw"], options[0][0], bank)
                action = int(np.argmax(q_values.get(key, np.zeros(4))[:len(options) + 1])) if q_values is not None else (1 if mode == "heuristic" and options[0][0] > 0 else 0)
                decisions.append((key, action))
                if action > 0:
                    _, out_id, in_id, delta = options[action - 1]
                    squad.remove(out_id); squad.add(in_id); bank -= delta; moves += 1
        score += float(row["actual"].reindex(list(squad)).fillna(0).sum())
    return {"points": round(score, 2), "transfers": moves, "decisions": decisions}


def train_q(rows: list[dict], episodes: int = 30) -> dict:
    q = {}
    alpha, gamma = 0.12, 0.92
    for episode in range(episodes):
        squad = rows[0]["initial"].copy()
        bank = max(0.0, 100.0 - rows[0]["initial_cost"])
        epsilon = max(0.03, 0.45 * (1 - episode / episodes))
        for index, row in enumerate(rows[1:], start=1):
            options = swap_options(row, squad, bank)
            if not options: continue
            gain, out_id, in_id, delta = options[0]
            key = state_key(row["gw"], gain, bank)
            q.setdefault(key, np.zeros(4, dtype=float))
            action = int(RNG.integers(len(options) + 1)) if RNG.random() < epsilon else int(np.argmax(q[key][:len(options) + 1]))
            if action:
                _, out_id, in_id, delta = options[action - 1]
            old_points = float(row["actual"].get(out_id, 0)) if action else 0.0
            new_points = float(row["actual"].get(in_id, 0)) if action else 0.0
            reward = new_points - old_points
            if action:
                squad.remove(out_id); squad.add(in_id); bank -= delta
            next_row = rows[min(index + 1, len(rows) - 1)]
            next_options = swap_options(next_row, squad, bank)
            next_key = state_key(next_row["gw"], next_options[0][0] if next_options else 0, bank)
            q.setdefault(next_key, np.zeros(4, dtype=float))
            q[key][action] += alpha * (reward + gamma * float(np.max(q[next_key])) - q[key][action])
    return q


def main() -> None:
    data = pd.read_csv(SOURCE, low_memory=False)
    seasons = ["2022-23", "2023-24", "2024-25", "2025-26"]
    trajectories = {season: trajectory(data, season) for season in seasons}
    folds = []
    for test_season, train_seasons in (("2024-25", ["2022-23", "2023-24"]), ("2025-26", ["2022-23", "2023-24", "2024-25"])):
        test = trajectories[test_season]
        q_models = [train_q(trajectories[season]) for season in train_seasons if len(trajectories[season]) >= 10]
        if not q_models or len(test) < 10:
            raise RuntimeError(f"Insufficient data for RL fold ending in {test_season}.")
        all_states = set().union(*(model.keys() for model in q_models))
        q = {state: np.mean([model.get(state, np.zeros(4)) for model in q_models], axis=0) for state in all_states}
        rl = run_policy(test, q_values=q)
        heuristic = run_policy(test, mode="heuristic")
        hold_result = run_policy(test, mode="hold")
        folds.append({"training_seasons": train_seasons, "test_season": test_season,
            "rl": {"points": rl["points"], "transfers": rl["transfers"]},
            "projection_heuristic": {"points": heuristic["points"], "transfers": heuristic["transfers"]},
            "hold_initial_team": {"points": hold_result["points"], "transfers": 0}})
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "folds": folds,
        "agent": "tabular Q-learning: action 0 keep; actions 1-3 choose among the three highest projected-gain legal same-position swaps; reward is incoming minus outgoing actual GW points.",
        "state": ["season phase", "projected gain bucket", "bank bucket"], "episodes_per_training_season": 30,
        "caveats": ["The candidate set is limited to the three highest-projection same-position swaps; this remains a prototype, not a full transfer-action policy.",
                    "Historical price and club snapshots are approximate; chips, injuries, price-change sell value and official transfer rollover are not modeled.",
                    "The small public-team/past-season dataset limits generalization; compare multiple seasons before relying on policy results."]}
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(folds, indent=2))


if __name__ == "__main__":
    main()

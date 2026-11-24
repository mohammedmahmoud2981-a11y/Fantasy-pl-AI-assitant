from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fantasyiq.features import create_grid
from fantasyiq.optimizer import optimize_squad

SOURCE = ROOT / "data/processed/player_gameweeks.csv.gz"
OUT = ROOT / "reports/transfer_policy_backtest.json"
POSITION_MAP = {"GK": "Goalkeeper", "DEF": "Defender", "MID": "Midfielder", "FWD": "Forward"}


def main() -> None:
    season = "2025-26"
    raw = pd.read_csv(SOURCE, low_memory=False)
    raw = raw[raw.season.astype(str) == season].copy()
    raw["season"] = raw.season.astype(str)
    raw["gameweek"] = pd.to_numeric(raw.gameweek, errors="coerce").astype(int)
    raw["player_id"] = pd.to_numeric(raw.player_id, errors="coerce").astype(int)
    data = create_grid(raw)
    data["position"] = data.position.map(POSITION_MAP)
    data["cost_m"] = pd.to_numeric(data.value, errors="coerce") / 10
    data["team"] = pd.to_numeric(data.team_id, errors="coerce").fillna(-1).astype(int)
    data["total_points"] = pd.to_numeric(data.total_points, errors="coerce").fillna(0)
    rows = []
    for gw in sorted(data.gameweek.unique()):
        if gw <= 3:
            continue  # need three completed rounds before making any decision
        prior = data[data.gameweek < gw]
        latest = prior.sort_values("gameweek").groupby("player_id", as_index=False).tail(1).set_index("player_id")
        recent = prior[prior.gameweek >= gw - 3].groupby("player_id").total_points.mean().rename("expected_points")
        pool = latest.join(recent, how="inner").reset_index()
        pool = pool[pool.position.isin(POSITION_MAP.values())].dropna(subset=["cost_m", "expected_points"])
        pool = pd.concat([
            group.sort_values("expected_points", ascending=False).head(60)
            for _, group in pool.groupby("position", sort=False)
        ]).drop_duplicates("player_id")
        actual = data[data.gameweek == gw].set_index("player_id").total_points
        try:
            optimal = optimize_squad(pool[["player_id", "position", "team", "cost_m", "expected_points"]].rename(columns={"player_id": "id"}), 100.0)
        except ValueError:
            continue
        rows.append({"gw": int(gw), "pool": pool, "actual": actual, "optimal": set(optimal.id.astype(int)),
                     "projection": float(optimal.expected_points.sum()), "optimal_cost": float(optimal.cost_m.sum())})
    if len(rows) < 5:
        raise RuntimeError("Not enough valid gameweeks for this backtest.")

    initial = rows[0]["optimal"].copy()
    hold_scores = [float(row["actual"].reindex(list(initial)).fillna(0).sum()) for row in rows]
    reoptimized_scores = [float(row["actual"].reindex(list(row["optimal"])).fillna(0).sum()) for row in rows]
    policy_results = {}
    for threshold in (0.0, 0.5, 1.0, 1.5, 2.0):
        active = initial.copy()
        bankroll = max(0.0, 100.0 - rows[0]["optimal_cost"])
        scores, transfers = [], 0
        for index, row in enumerate(rows):
            if index:
                pool = row["pool"].set_index("player_id")
                best = None
                for outgoing_id in active:
                    if outgoing_id not in pool.index: continue
                    outgoing = pool.loc[outgoing_id]
                    candidates = pool[(pool.position == outgoing.position) & (~pool.index.isin(active))]
                    for incoming_id, incoming in candidates.iterrows():
                        remaining = active - {outgoing_id}
                        if sum(int(pool.loc[i, "team"] == incoming.team) for i in remaining if i in pool.index) >= 3: continue
                        delta = float(incoming.cost_m - outgoing.cost_m)
                        if delta > bankroll + 1e-9: continue
                        gain = float(incoming.expected_points - outgoing.expected_points)
                        if gain > threshold and (best is None or gain > best[0]): best = (gain, int(outgoing_id), int(incoming_id), delta)
                if best:
                    _, outgoing_id, incoming_id, delta = best
                    active.remove(outgoing_id); active.add(incoming_id); bankroll -= delta; transfers += 1
            scores.append(float(row["actual"].reindex(list(active)).fillna(0).sum()))
        policy_results[str(threshold)] = {"points": round(sum(scores), 2), "transfers": transfers,
                                          "net_gain_vs_hold": round(sum(scores) - sum(hold_scores), 2)}

    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "season": season,
        "gameweeks_evaluated": [r["gw"] for r in rows], "warmup_gameweeks": 3,
        "policy": "Compare one-free-transfer-per-GW policies at minimum projected-gain thresholds; prior-three-GW only, 100m initial budget, cash bank and max three per club.",
        "hold_initial_squad_points": round(sum(hold_scores), 2),
        "one_transfer_policy_thresholds": policy_results,
        "weekly_reoptimization_points_before_hits": round(sum(reoptimized_scores), 2),
        "weekly_reoptimization_transfers": sum(len(rows[i]["optimal"] ^ rows[i-1]["optimal"]) // 2 for i in range(1, len(rows))),
        "caveat": "Only completed prior-round player outcomes determine projections. The source has imperfect historical price/club snapshots; price changes, chips, injuries/news and transfer-value rules are not fully reconstructed. Treat this as a diagnostic baseline, not an official FPL score reproduction.",
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("gameweeks_evaluated", "hold_initial_squad_points", "one_transfer_policy_thresholds", "weekly_reoptimization_points_before_hits", "weekly_reoptimization_transfers")}, indent=2))


if __name__ == "__main__":
    main()

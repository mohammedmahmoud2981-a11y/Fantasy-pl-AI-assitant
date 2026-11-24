from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/processed/player_gameweeks.csv.gz"
REPORT = ROOT / "reports/hybrid_recommender_evaluation.json"
sys.path.insert(0, str(ROOT))
from fantasyiq.features import create_grid

FEATURES = ["total_points", "minutes", "goals_scored", "assists", "clean_sheets", "bonus", "bps", "expected_goals", "expected_assists", "expected_goals_conceded"]
POS = {"GK": "Goalkeeper", "DEF": "Defender", "MID": "Midfielder", "FWD": "Forward"}

def main() -> None:
    season = sys.argv[1] if len(sys.argv) > 1 else "2025-26"
    raw = pd.read_csv(SOURCE, low_memory=False)
    raw = raw[raw.season.astype(str) == season].copy()
    if raw.empty:
        raise RuntimeError(f"No historical player-gameweek data for {season}.")
    raw["season"] = raw.season.astype(str)
    raw["gameweek"] = pd.to_numeric(raw.gameweek, errors="coerce").astype(int)
    raw["player_id"] = pd.to_numeric(raw.player_id, errors="coerce").astype(int)
    data = create_grid(raw)
    for column in FEATURES + ["value"]:
        if column in data: data[column] = pd.to_numeric(data[column], errors="coerce")
    data["position"] = data.position.map(POS)
    groups = {"hybrid": [], "form_only": [], "candidate_pool": []}
    hit = {"hybrid": [], "form_only": []}
    rng = np.random.default_rng(42)
    for gw in sorted(data.gameweek.unique()):
        if gw <= 3: continue
        prior = data[data.gameweek < gw]
        latest = prior.sort_values("gameweek").groupby("player_id", as_index=False).tail(1).set_index("player_id")
        rolling = prior[prior.gameweek >= gw - 3].groupby("player_id")[FEATURES].mean()
        profiles = latest.join(rolling, how="inner", rsuffix="_rolling").reset_index()
        # Rolling features use pre-deadline rounds only; current gameweek points are labels only.
        for stat in FEATURES:
            roll_col = f"{stat}_rolling" if f"{stat}_rolling" in profiles else stat
            if roll_col in profiles: profiles[f"f_{stat}"] = profiles[roll_col]
        profiles["cost_m"] = profiles.value / 10
        target = data[data.gameweek == gw].set_index("player_id").total_points
        profiles = profiles.dropna(subset=["position", "cost_m"])
        for position, full_pool in profiles.groupby("position"):
            if len(full_pool) < 8: continue
            sample = full_pool.sample(min(8, len(full_pool)), random_state=int(rng.integers(0, 2**31 - 1)))
            feat_cols = [f"f_{x}" for x in FEATURES if f"f_{x}" in profiles]
            mat = profiles[feat_cols].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
            mat = mat.fillna(mat.median()).fillna(0)
            scaled = StandardScaler().fit_transform(mat)
            scaled_frame = pd.DataFrame(scaled, index=profiles.player_id.astype(int), columns=feat_cols)
            indexed = profiles.set_index("player_id")
            for row in sample.itertuples(index=False):
                player_id = int(row.player_id)
                if player_id not in scaled_frame.index: continue
                candidates = full_pool[full_pool.player_id != player_id].copy()
                if candidates.empty: continue
                cids = candidates.player_id.astype(int).to_numpy()
                sim = cosine_similarity(scaled_frame.loc[cids], scaled_frame.loc[[player_id]]).ravel()
                recent_col = "f_total_points"
                xp = pd.to_numeric(candidates[recent_col], errors="coerce").fillna(0).to_numpy()
                value = xp / candidates.cost_m.clip(lower=0.1).to_numpy()
                def norm(x):
                    span = float(np.max(x) - np.min(x))
                    return (x - np.min(x)) / span if span else np.full(len(x), 0.5)
                hybrid_score = 0.45 * norm(xp) + 0.35 * ((sim + 1) / 2) + 0.20 * norm(value)
                rankings = {"hybrid": np.argsort(hybrid_score)[::-1][:5], "form_only": np.argsort(xp)[::-1][:5]}
                for method, indices in rankings.items():
                    selected_ids = cids[indices]
                    actual_values = target.reindex(selected_ids).fillna(0).to_numpy(dtype=float)
                    groups[method].append(float(actual_values.mean()))
                    pos_values = target.reindex(candidates.player_id.astype(int)).fillna(0).to_numpy(dtype=float)
                    hit[method].append(float(np.mean(actual_values >= 4)))
                groups["candidate_pool"].append(float(target.reindex(cids).fillna(0).mean()))
    results = {method: {"mean_actual_points_at_5": round(float(np.mean(groups[method])), 4),
                        "share_of_top5_scoring_4plus": round(float(np.mean(hit[method])), 4), "queries": len(vals)}
               for method, vals in hit.items()}
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "test_season": season,
              "rounds": "GW4-GW38; pre-deadline rolling three-gameweek history", "sampled_queries": len(groups["candidate_pool"]),
              "candidate_pool_mean_actual_points": round(float(np.mean(groups["candidate_pool"])), 4), "methods": results,
              "caveat": "This tests same-position replacement ranking on sampled outgoing players. Historical prices/team labels are imperfect and the metric is descriptive; rankings are not a causal transfer backtest."}
    season_report = REPORT.with_name(f"hybrid_recommender_evaluation_{season}.json")
    season_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if season == "2025-26":
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["methods"], indent=2))

if __name__ == "__main__": main()

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/processed/player_gameweeks.csv.gz"
OUT = ROOT / "reports"
FEATURES = ["total_points", "minutes", "goals_scored", "assists", "clean_sheets", "bonus", "bps", "expected_goals", "expected_assists", "expected_goals_conceded", "value"]

def main() -> None:
    data = pd.read_csv(SOURCE, low_memory=False)
    data["season"] = data["season"].astype(str)
    # Use most recent fully observed season to create comparable end-of-season player profiles.
    season = sorted(data["season"].unique())[-2] if len(data["season"].unique()) > 1 else data["season"].iloc[0]
    current = data[data["season"] == season].copy()
    current[FEATURES] = current[FEATURES].apply(pd.to_numeric, errors="coerce")
    agg = current.groupby(["player_id", "player_name", "position"], dropna=False).agg(
        total_points=("total_points", "sum"), minutes=("minutes", "sum"),
        goals_scored=("goals_scored", "sum"), assists=("assists", "sum"),
        clean_sheets=("clean_sheets", "sum"), bonus=("bonus", "sum"), bps=("bps", "sum"),
        expected_goals=("expected_goals", "sum"), expected_assists=("expected_assists", "sum"),
        expected_goals_conceded=("expected_goals_conceded", "sum"), value=("value", "last"),
        gameweeks=("gameweek", "nunique"),
    ).reset_index()
    agg = agg[agg.minutes >= 180].reset_index(drop=True)
    features = FEATURES
    matrix = StandardScaler().fit_transform(SimpleImputer(strategy="median").fit_transform(agg[features]))
    candidates = {}
    for k in range(3, 7):
        km = KMeans(n_clusters=k, random_state=42, n_init=20).fit(matrix)
        candidates[k] = (silhouette_score(matrix, km.labels_, sample_size=min(5000, len(matrix)), random_state=42), km)
    best_k = max(candidates, key=lambda k: candidates[k][0])
    score, model = candidates[best_k]
    agg["cluster"] = model.labels_
    detector = IsolationForest(contamination=0.03, random_state=42, n_estimators=300)
    agg["anomaly_score"] = -detector.fit(matrix).score_samples(matrix)
    agg["is_anomaly"] = detector.predict(matrix) == -1
    OUT.mkdir(exist_ok=True)
    agg.sort_values("anomaly_score", ascending=False).to_csv(OUT / "player_profiles.csv", index=False)
    cluster_summary = agg.groupby("cluster")[FEATURES].mean().round(3).to_dict(orient="index")
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "source_season": season,
              "players": int(len(agg)), "features": features, "clusters": best_k,
              "silhouette_score": round(float(score), 4), "anomaly_count": int(agg.is_anomaly.sum()),
              "anomaly_contamination": 0.03, "cluster_profiles": cluster_summary,
              "caveat": "End-of-season descriptive player profiles; not a pre-deadline prediction or injury signal."}
    (OUT / "player_profile_metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("source_season", "players", "clusters", "silhouette_score", "anomaly_count")}, indent=2))

if __name__ == "__main__":
    main()

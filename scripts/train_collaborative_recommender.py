from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "processed" / "user_player_interactions.csv"
MODEL = ROOT / "models" / "collaborative_recommender.joblib"
REPORT = ROOT / "reports" / "collaborative_recommender_metrics.json"

def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Interaction data is missing: {SOURCE}. Collect public FPL team picks first; see data/README.md.")
    data = pd.read_csv(SOURCE)
    if not {"user_id", "player_id"}.issubset(data):
        raise ValueError("Input CSV must contain user_id and player_id columns.")
    data = data[["user_id", "player_id"] + (["event"] if "event" in data else [])].dropna().drop_duplicates()
    temporal = {"available": False}
    if "event" in data and data.event.nunique() >= 2:
        latest = int(data.event.max())
        train_data = data[data.event < latest].drop_duplicates(["user_id", "player_id"])
        test_data = data[data.event == latest]
        train_users = sorted(train_data.user_id.astype(str).unique())
        train_items = sorted(train_data.player_id.astype(int).unique())
        item_idx = {v: i for i, v in enumerate(train_items)}
        user_idx = {v: i for i, v in enumerate(train_users)}
        from scipy.sparse import csr_matrix
        train_rows = train_data.user_id.astype(str).map(user_idx)
        train_cols = train_data.player_id.astype(int).map(item_idx)
        fit = train_rows.notna() & train_cols.notna()
        train_matrix = csr_matrix((np.ones(int(fit.sum()), dtype=np.float32),
            (train_rows[fit].astype(int), train_cols[fit].astype(int))), shape=(len(train_users), len(train_items)))
        similarities = cosine_similarity(train_matrix.T, dense_output=True)
        precisions, recalls, popularity_precisions, popularity_recalls = [], [], [], []
        popular = np.asarray(train_matrix.sum(axis=0)).ravel()
        for user, group in test_data.groupby(test_data.user_id.astype(str)):
            if user not in user_idx: continue
            relevant = set(group.player_id.astype(int)) & set(item_idx)
            if not relevant: continue
            history = train_matrix.getrow(user_idx[user]).toarray().ravel()
            scores = history @ similarities
            scores[history > 0] = -1
            top = np.argsort(scores)[-10:]
            recommended = {train_items[i] for i in top if scores[i] >= 0}
            if recommended:
                precisions.append(len(recommended & relevant) / len(recommended))
                recalls.append(len(recommended & relevant) / len(relevant))
            popular_scores = popular.copy()
            popular_scores[history > 0] = -1
            popular_top = np.argsort(popular_scores)[-10:]
            popular_recommended = {train_items[i] for i in popular_top if popular_scores[i] >= 0}
            if popular_recommended:
                popularity_precisions.append(len(popular_recommended & relevant) / len(popular_recommended))
                popularity_recalls.append(len(popular_recommended & relevant) / len(relevant))
        temporal = {"available": bool(recalls), "holdout_event": latest, "users_evaluated": len(recalls),
                    "precision_at_10": round(float(np.mean(precisions)), 4) if precisions else None,
                    "recall_at_10": round(float(np.mean(recalls)), 4) if recalls else None,
                    "popularity_baseline_precision_at_10": round(float(np.mean(popularity_precisions)), 4) if popularity_precisions else None,
                    "popularity_baseline_recall_at_10": round(float(np.mean(popularity_recalls)), 4) if popularity_recalls else None}
    data = data[["user_id", "player_id"]].drop_duplicates()
    users = sorted(data.user_id.astype(str).unique())
    items = sorted(data.player_id.astype(int).unique())
    if len(users) < 10:
        raise ValueError("Collaborative filtering requires picks from at least 10 distinct FPL teams.")
    user_index = {v: i for i, v in enumerate(users)}
    item_index = {v: i for i, v in enumerate(items)}
    rows = data.user_id.astype(str).map(user_index).to_numpy()
    cols = data.player_id.astype(int).map(item_index).to_numpy()
    from scipy.sparse import csr_matrix
    matrix = csr_matrix((np.ones(len(rows), dtype=np.float32), (rows, cols)), shape=(len(users), len(items)))
    item_similarity = cosine_similarity(matrix.T, dense_output=True).astype(np.float32)
    np.fill_diagonal(item_similarity, 0)
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"user_ids": users, "player_ids": items, "item_similarity": item_similarity}, MODEL, compress=3)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"trained_at_utc": datetime.now(timezone.utc).isoformat(), "users": len(users),
        "players": len(items), "interactions": int(matrix.nnz), "density": round(matrix.nnz / (len(users) * len(items)), 6),
        "method": "implicit item-item cosine similarity from public FPL picks", "temporal_evaluation": temporal,
        "model": str(MODEL.relative_to(ROOT))}, indent=2), encoding="utf-8")
    print(f"Trained item-item collaborative model from {len(users)} teams and {matrix.nnz} unique picks.")

if __name__ == "__main__":
    main()

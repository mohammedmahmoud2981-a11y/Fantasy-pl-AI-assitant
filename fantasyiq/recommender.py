from __future__ import annotations

import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler


PROFILE_FEATURES = ["form", "points_per_game", "minutes", "total_points", "expected_points", "selected_by_percent", "cost_m"]
CF_MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "collaborative_recommender.joblib"


def hybrid_recommendations(pool: pd.DataFrame, target: pd.Series, limit: int = 5) -> pd.DataFrame:
    """Rank same-position alternatives by form similarity, projected points and value."""
    candidates = pool[pool["id"] != target["id"]].copy()
    if candidates.empty:
        return candidates
    columns = [column for column in PROFILE_FEATURES if column in candidates.columns and column in target.index]
    matrix = candidates[columns].apply(pd.to_numeric, errors="coerce")
    target_row = pd.DataFrame([{column: pd.to_numeric(pd.Series([target[column]]), errors="coerce").iloc[0] for column in columns}])
    matrix = matrix.replace([np.inf, -np.inf], np.nan)
    matrix = matrix.fillna(matrix.median()).fillna(0)
    target_row = target_row.replace([np.inf, -np.inf], np.nan).fillna(matrix.median()).fillna(0)
    scaled = StandardScaler().fit_transform(pd.concat([matrix, target_row], ignore_index=True))
    similarity = cosine_similarity(scaled[:-1], scaled[-1:]).ravel()
    candidates["similarity_score"] = (similarity + 1) / 2
    xp = pd.to_numeric(candidates["recommendation_points"], errors="coerce").fillna(0)
    xp_range = xp.max() - xp.min()
    candidates["projection_score"] = (xp - xp.min()) / xp_range if xp_range else 0.5
    value = xp / pd.to_numeric(candidates["cost_m"], errors="coerce").clip(lower=0.1)
    value_range = value.max() - value.min()
    candidates["value_score"] = (value - value.min()) / value_range if value_range else 0.5
    candidates["hybrid_score"] = 0.45 * candidates["projection_score"] + 0.35 * candidates["similarity_score"] + 0.20 * candidates["value_score"]
    candidates["collaborative_score"] = np.nan
    candidates["recommender_type"] = "content_hybrid"
    if CF_MODEL_PATH.exists():
        try:
            cf = joblib.load(CF_MODEL_PATH)
            ids = {int(player_id): index for index, player_id in enumerate(cf["player_ids"])}
            target_index = ids.get(int(target["id"]))
            if target_index is not None:
                scores = cf["item_similarity"][target_index]
                score_map = {int(player_id): float(scores[index]) for index, player_id in enumerate(cf["player_ids"])}
                raw = candidates["id"].map(score_map).fillna(0.0).to_numpy()
                maximum = float(raw.max())
                candidates["collaborative_score"] = raw / maximum if maximum > 0 else 0.0
                # CF currently ties the popularity baseline, so keep it as a small tie-break signal.
                candidates["hybrid_score"] = 0.42 * candidates["projection_score"] + 0.32 * candidates["similarity_score"] + 0.21 * candidates["value_score"] + 0.05 * candidates["collaborative_score"]
                candidates["recommender_type"] = "hybrid_with_collaborative"
        except (OSError, KeyError, ValueError):
            pass
    # Chronological offline checks show form/projection ranking is stronger than
    # similarity-heavy ranking; keep hybrid features as tie-breakers only.
    return candidates.sort_values(["recommendation_points", "hybrid_score"], ascending=False).head(limit)

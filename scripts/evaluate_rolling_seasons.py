from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from train_next_gw_model import DATA_PATH, MANIFEST_PATH, TARGET, make_estimator, metrics


def main() -> None:
    frame = pd.read_csv(DATA_PATH, low_memory=False)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    frame["season"] = frame["season"].astype(str)
    frame = frame.dropna(subset=[TARGET])
    categorical = manifest.get("categorical_feature_columns", [])
    features = manifest["feature_columns"]
    numeric = [column for column in features if column not in categorical]
    seasons = [season for season in ["2022-23", "2023-24", "2024-25", "2025-26"] if season in set(frame.season)]
    results = []
    for season in seasons:
        train = frame[frame.season < season]
        valid = frame[frame.season == season]
        model = make_estimator(numeric, categorical)
        model.fit(train[features], train[TARGET].astype(float))
        prediction = model.predict(valid[features])
        baseline = valid["total_points_mean_3gw"].fillna(float(train[TARGET].mean())).to_numpy(float)
        results.append({"evaluation_season": season, "training_seasons": sorted(train.season.unique().tolist()),
                        "model": metrics(valid[TARGET], prediction), "last_3_gameweeks_baseline": metrics(valid[TARGET], baseline),
                        "improved_mae": bool(metrics(valid[TARGET], prediction)["mae"] < metrics(valid[TARGET], baseline)["mae"])})
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "method": "expanding-window chronological evaluation",
              "target": TARGET, "folds": results,
              "mean_model_mae": round(float(np.mean([r["model"]["mae"] for r in results])), 4),
              "mean_baseline_mae": round(float(np.mean([r["last_3_gameweeks_baseline"]["mae"] for r in results])), 4),
              "folds_beating_baseline": sum(r["improved_mae"] for r in results)}
    path = DATA_PATH.parents[2] / "reports" / "rolling_season_evaluation.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("mean_model_mae", "mean_baseline_mae", "folds_beating_baseline")}, indent=2))
    for fold in results:
        print(f"{fold['evaluation_season']}: model MAE {fold['model']['mae']} vs baseline {fold['last_3_gameweeks_baseline']['mae']}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd

from fantasyiq.features import add_features, create_grid


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "processed" / "player_gameweeks.csv.gz"
FEATURE_MANIFEST = ROOT / "data" / "processed" / "next_gw_manifest.json"
MODEL_PATH = ROOT / "models" / "next_gw_hist_gradient_boosting.joblib"
CLASSIFIER_PATH = ROOT / "models" / "high_potential_classifier.joblib"


def infer_current_season(events: list[dict]) -> str:
    first_deadline = next((event.get("deadline_time") for event in events if event.get("deadline_time")), None)
    if not first_deadline:
        raise ValueError("The FPL feed has no gameweek deadline to identify its season.")
    year = datetime.fromisoformat(first_deadline.replace("Z", "+00:00")).year
    return f"{year}-{(year + 1) % 100:02d}"


def predict_next_gameweek(current_season: str) -> tuple[pd.DataFrame, int]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Trained model not found: {MODEL_PATH}")
    if not SOURCE.exists() or not FEATURE_MANIFEST.exists():
        missing = [str(path.relative_to(ROOT)) for path in (SOURCE, FEATURE_MANIFEST) if not path.exists()]
        raise FileNotFoundError(f"Required prediction assets are missing: {', '.join(missing)}. Rebuild the Docker image from the project root.")

    source = pd.read_csv(SOURCE, low_memory=False)
    source["season"] = source["season"].astype(str)
    current = source.loc[source["season"] == current_season].copy()
    if current.empty:
        raise ValueError(f"No collected player-gameweek data exists for {current_season}.")
    current["gameweek"] = pd.to_numeric(current["gameweek"], errors="raise").astype(int)
    current["player_id"] = pd.to_numeric(current["player_id"], errors="raise").astype(int)

    grid = create_grid(current)
    feature_rows = add_features(grid, keep_unlabeled=True)
    last_completed_gw = int(current["gameweek"].max())
    latest_rows = feature_rows.loc[feature_rows["gameweek"] == last_completed_gw].copy()
    if latest_rows.empty:
        raise ValueError("No feature rows were produced for the latest completed gameweek.")

    manifest = json.loads(FEATURE_MANIFEST.read_text(encoding="utf-8"))
    feature_columns = manifest["feature_columns"]
    missing = set(feature_columns) - set(latest_rows.columns)
    if missing:
        raise ValueError(f"Inference features do not match the trained model: {sorted(missing)}")
    model = joblib.load(MODEL_PATH)
    latest_rows["fantasyiq_points"] = model.predict(latest_rows[feature_columns])
    if CLASSIFIER_PATH.exists():
        classifier = joblib.load(CLASSIFIER_PATH)
        latest_rows["high_potential_probability"] = classifier.predict_proba(latest_rows[feature_columns])[:, 1]
    else:
        latest_rows["high_potential_probability"] = float("nan")
    latest_rows["prediction_gameweek"] = latest_rows["target_gameweek"].astype(int)
    return latest_rows[["player_id", "fantasyiq_points", "high_potential_probability", "prediction_gameweek"]], last_completed_gw

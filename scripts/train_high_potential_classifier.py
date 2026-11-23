from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "processed" / "next_gw_training.csv.gz"
MANIFEST_PATH = ROOT / "data" / "processed" / "next_gw_manifest.json"
MODEL_DIR = ROOT / "models"
REPORT_DIR = ROOT / "reports"
TARGET = "target_points_next_gw"
VALIDATION_SEASON = "2024-25"
TEST_SEASON = "2025-26"
LIVE_SEASON = "2026-27"


def make_classifier(numeric_features: list[str], categorical_features: list[str]) -> Pipeline:
    numeric = Pipeline([
        ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("one_hot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    prep = ColumnTransformer([
        ("numeric", numeric, numeric_features),
        ("categorical", categorical, categorical_features),
    ], sparse_threshold=0.0)
    model = LogisticRegression(C=0.15, max_iter=500, solver="lbfgs", random_state=42)
    return Pipeline([("preprocessing", prep), ("classifier", model)])


def thresholds_from(training: pd.DataFrame) -> dict[str, float]:
    return {
        str(position): float(group[TARGET].quantile(0.75))
        for position, group in training.groupby("position", sort=True)
    }


def labels(frame: pd.DataFrame, thresholds: dict[str, float]) -> np.ndarray:
    cutoffs = frame["position"].map(thresholds).fillna(frame[TARGET].quantile(0.75))
    return (frame[TARGET].to_numpy(dtype=float) >= cutoffs.to_numpy(dtype=float)).astype(np.int8)


def score(y_true: np.ndarray, probabilities: np.ndarray) -> dict:
    predicted = probabilities >= 0.5
    return {
        "precision_at_0_5": round(float(precision_score(y_true, predicted, zero_division=0)), 4),
        "recall_at_0_5": round(float(recall_score(y_true, predicted, zero_division=0)), 4),
        "f1_at_0_5": round(float(f1_score(y_true, predicted, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, probabilities)), 4),
        "average_precision": round(float(average_precision_score(y_true, probabilities)), 4),
        "positive_rate": round(float(np.mean(y_true)), 4),
        "rows": int(len(y_true)),
    }


def main() -> None:
    frame = pd.read_csv(DATA_PATH, low_memory=False)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    frame["season"] = frame["season"].astype(str)
    features = manifest["feature_columns"]
    categorical = manifest.get("categorical_feature_columns", [])
    numeric = [column for column in features if column not in categorical]

    train_mask = frame["season"] < VALIDATION_SEASON
    validation_mask = frame["season"] == VALIDATION_SEASON
    validation_train = frame.loc[train_mask]
    validation_cutoffs = thresholds_from(validation_train)
    y_train = labels(validation_train, validation_cutoffs)
    y_validation = labels(frame.loc[validation_mask], validation_cutoffs)
    validation_model = make_classifier(numeric, categorical)
    validation_model.fit(validation_train[features], y_train)
    validation_prob = validation_model.predict_proba(frame.loc[validation_mask, features])[:, 1]
    validation_metrics = score(y_validation, validation_prob)

    final_train_mask = frame["season"] < TEST_SEASON
    test_mask = frame["season"] == TEST_SEASON
    final_train = frame.loc[final_train_mask]
    final_cutoffs = thresholds_from(final_train)
    y_final_train = labels(final_train, final_cutoffs)
    y_test = labels(frame.loc[test_mask], final_cutoffs)
    test_model = make_classifier(numeric, categorical)
    test_model.fit(final_train[features], y_final_train)
    test_prob = test_model.predict_proba(frame.loc[test_mask, features])[:, 1]
    test_metrics = score(y_test, test_prob)

    current_mask = frame["season"] == LIVE_SEASON
    current_metrics = None
    prediction_parts = []
    test_output = frame.loc[test_mask, ["season", "player_id", "player_name", "position", "gameweek", "target_gameweek", TARGET]].copy()
    test_output["high_potential_probability"] = test_prob
    test_output["high_potential_label"] = y_test
    prediction_parts.append(test_output)
    if current_mask.any():
        current = frame.loc[current_mask]
        current_y = labels(current, final_cutoffs)
        current_prob = test_model.predict_proba(current[features])[:, 1]
        current_metrics = score(current_y, current_prob)
        current_output = current[["season", "player_id", "player_name", "position", "gameweek", "target_gameweek", TARGET]].copy()
        current_output["high_potential_probability"] = current_prob
        current_output["high_potential_label"] = current_y
        prediction_parts.append(current_output)

    deployment_mask = frame["season"] < LIVE_SEASON
    deployment_frame = frame.loc[deployment_mask]
    deployment_cutoffs = thresholds_from(deployment_frame)
    deployment_y = labels(deployment_frame, deployment_cutoffs)
    deployment_model = make_classifier(numeric, categorical)
    deployment_model.fit(deployment_frame[features], deployment_y)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / "high_potential_classifier.joblib"
    joblib.dump(deployment_model, model_path, compress=3)
    prediction_path = REPORT_DIR / "high_potential_predictions.csv.gz"
    pd.concat(prediction_parts, ignore_index=True).to_csv(prediction_path, index=False, compression="gzip")
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "definition": "High potential means target points at or above the training-set 75th percentile for the player's position.",
        "thresholds_by_position_points": {key: round(value, 3) for key, value in deployment_cutoffs.items()},
        "features": features,
        "validation": {
            "training_seasons": sorted(validation_train["season"].unique().tolist()),
            "evaluation_seasons": [VALIDATION_SEASON],
            "thresholds_by_position_points": validation_cutoffs,
            "metrics": validation_metrics,
        },
        "final_test": {
            "training_seasons": sorted(final_train["season"].unique().tolist()),
            "evaluation_seasons": [TEST_SEASON],
            "thresholds_by_position_points": final_cutoffs,
            "metrics": test_metrics,
        },
        "current_season_diagnostic": current_metrics,
        "deployment_training_seasons": sorted(deployment_frame["season"].unique().tolist()),
        "model": "LogisticRegression",
        "model_path": str(model_path.relative_to(ROOT)),
        "predictions_path": str(prediction_path.relative_to(ROOT)),
        "caveat": "The probability estimates the chance of reaching this historical, position-relative high-score threshold. It is not a calibrated probability of injury or guaranteed points.",
    }
    report_path = REPORT_DIR / "high_potential_metrics.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Validation:", json.dumps(validation_metrics))
    print("Final test:", json.dumps(test_metrics))
    if current_metrics:
        print("Current season diagnostic:", json.dumps(current_metrics))
    print(f"Saved classifier: {model_path}")
    print(f"Saved report: {report_path}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "processed" / "next_gw_training.csv.gz"
MANIFEST_PATH = ROOT / "data" / "processed" / "next_gw_manifest.json"
MODEL_DIR = ROOT / "models"
REPORT_DIR = ROOT / "reports"
TARGET = "target_points_next_gw"
VALIDATION_SEASON = "2024-25"
TEST_SEASON = "2025-26"
LIVE_SEASON = "2026-27"
RANDOM_STATE = 42


def make_estimator(numeric_features: list[str], categorical_features: list[str]) -> Pipeline:
    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
    ])
    categorical_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("one_hot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    preprocessing = ColumnTransformer([
        ("numeric", numeric_pipeline, numeric_features),
        ("categorical", categorical_pipeline, categorical_features),
    ], remainder="drop", sparse_threshold=0.0)
    predictor = HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=0.08,
        max_iter=120,
        max_leaf_nodes=31,
        min_samples_leaf=30,
        l2_regularization=1.0,
        early_stopping=False,
        random_state=RANDOM_STATE,
    )
    return Pipeline([("preprocessing", preprocessing), ("model", predictor)])


def metrics(y_true: pd.Series, prediction: np.ndarray) -> dict[str, float]:
    return {
        "mae": round(float(mean_absolute_error(y_true, prediction)), 4),
        "rmse": round(float(np.sqrt(mean_squared_error(y_true, prediction))), 4),
        "r2": round(float(r2_score(y_true, prediction)), 4),
        "rows": int(len(y_true)),
    }


def evaluate_split(
    frame: pd.DataFrame,
    train_mask: pd.Series,
    eval_mask: pd.Series,
    feature_columns: list[str],
    numeric_features: list[str],
    categorical_features: list[str],
) -> tuple[Pipeline, dict, pd.DataFrame]:
    train = frame.loc[train_mask]
    evaluation = frame.loc[eval_mask]
    if train.empty or evaluation.empty:
        raise ValueError("A chronological split is empty. Check available season coverage.")

    y_train = train[TARGET].astype(float)
    y_eval = evaluation[TARGET].astype(float)
    X_train = train[feature_columns]
    X_eval = evaluation[feature_columns]

    # Mean and recent-form baselines are intentionally simple comparison points.
    mean_baseline = DummyRegressor(strategy="mean").fit(np.zeros((len(y_train), 1)), y_train)
    mean_predictions = mean_baseline.predict(np.zeros((len(y_eval), 1)))
    recent_predictions = evaluation["total_points_mean_3gw"].fillna(float(y_train.mean())).to_numpy(dtype=float)

    estimator = make_estimator(numeric_features, categorical_features)
    estimator.fit(X_train, y_train)
    model_predictions = estimator.predict(X_eval)

    report = {
        "mean_baseline": metrics(y_eval, mean_predictions),
        "last_3_gameweeks_baseline": metrics(y_eval, recent_predictions),
        "hist_gradient_boosting": metrics(y_eval, model_predictions),
        "evaluation_seasons": sorted(evaluation["season"].unique().tolist()),
        "training_seasons": sorted(train["season"].unique().tolist()),
    }
    output = evaluation[["season", "player_id", "player_name", "position", "gameweek", "target_gameweek", TARGET]].copy()
    output["mean_baseline_prediction"] = mean_predictions
    output["last_3_gameweeks_prediction"] = recent_predictions
    output["model_prediction"] = model_predictions
    return estimator, report, output


def evaluate_by_position(predictions: pd.DataFrame) -> dict[str, dict[str, float]]:
    report = {}
    for position, group in predictions.groupby("position", sort=True):
        report[position] = {
            "mae": round(float(mean_absolute_error(group[TARGET], group["model_prediction"])), 4),
            "rmse": round(float(np.sqrt(mean_squared_error(group[TARGET], group["model_prediction"]))), 4),
            "rows": int(len(group)),
        }
    return report


def main() -> None:
    if not DATA_PATH.exists() or not MANIFEST_PATH.exists():
        raise FileNotFoundError("Training data is missing. Run scripts/build_next_gw_features.py first.")
    frame = pd.read_csv(DATA_PATH, low_memory=False)
    data_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    feature_columns = data_manifest["feature_columns"]
    categorical_features = data_manifest.get("categorical_feature_columns", [])
    numeric_features = [column for column in feature_columns if column not in categorical_features]

    required = set(feature_columns + ["season", "player_id", "player_name", "gameweek", "target_gameweek", TARGET])
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Training table is missing required columns: {sorted(missing)}")
    frame["season"] = frame["season"].astype(str)
    frame = frame.dropna(subset=[TARGET]).copy()

    # One untouched recent completed season for the final temporal test.
    final_train_mask = frame["season"] < TEST_SEASON
    test_mask = frame["season"] == TEST_SEASON
    # A prior season is kept as a chronological validation checkpoint.
    validation_train_mask = frame["season"] < VALIDATION_SEASON
    validation_mask = frame["season"] == VALIDATION_SEASON

    _, validation_report, validation_predictions = evaluate_split(
        frame, validation_train_mask, validation_mask,
        feature_columns, numeric_features, categorical_features,
    )
    model, test_report, test_predictions = evaluate_split(
        frame, final_train_mask, test_mask,
        feature_columns, numeric_features, categorical_features,
    )

    live_mask = frame["season"] == LIVE_SEASON
    live_report = None
    live_predictions = pd.DataFrame()
    if live_mask.any():
        live = frame.loc[live_mask]
        live_y = live[TARGET].astype(float)
        live_X = live[feature_columns]
        live_predictions = live[["season", "player_id", "player_name", "position", "gameweek", "target_gameweek", TARGET]].copy()
        live_predictions["mean_baseline_prediction"] = float(frame.loc[final_train_mask, TARGET].mean())
        live_predictions["last_3_gameweeks_prediction"] = live["total_points_mean_3gw"].fillna(float(frame.loc[final_train_mask, TARGET].mean())).to_numpy(dtype=float)
        live_predictions["model_prediction"] = model.predict(live_X)
        live_report = {
            "model": metrics(live_y, live_predictions["model_prediction"].to_numpy()),
            "last_3_gameweeks_baseline": metrics(live_y, live_predictions["last_3_gameweeks_prediction"].to_numpy()),
            "evaluation_seasons": [LIVE_SEASON],
            "note": "Current in-progress season diagnostic; it is excluded from model fitting and is not the main final test.",
        }

    # After reporting the untouched test result, refit the deployable artifact
    # on every completed season. The in-progress season remains excluded.
    production_mask = frame["season"] < LIVE_SEASON
    production_model = make_estimator(numeric_features, categorical_features)
    production_model.fit(frame.loc[production_mask, feature_columns], frame.loc[production_mask, TARGET].astype(float))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / "next_gw_hist_gradient_boosting.joblib"
    joblib.dump(production_model, model_path, compress=3)
    prediction_path = REPORT_DIR / "next_gw_predictions.csv.gz"
    pd.concat([test_predictions, live_predictions], ignore_index=True).to_csv(prediction_path, index=False, compression="gzip")

    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": TARGET,
        "features": feature_columns,
        "categorical_features": categorical_features,
        "identifier_columns_excluded_from_model": data_manifest.get("id_columns", []),
        "validation": {
            **validation_report,
            "by_position": evaluate_by_position(validation_predictions),
        },
        "final_test": {
            **test_report,
            "by_position": evaluate_by_position(test_predictions),
        },
        "current_season_diagnostic": live_report,
        "test_model_training_seasons": sorted(frame.loc[final_train_mask, "season"].unique().tolist()),
        "deployment_model_training_seasons": sorted(frame.loc[production_mask, "season"].unique().tolist()),
        "final_test_seasons": sorted(frame.loc[test_mask, "season"].unique().tolist()),
        "estimator": {
            "name": "HistGradientBoostingRegressor",
            "max_iter": 120,
            "learning_rate": 0.08,
            "max_leaf_nodes": 31,
            "min_samples_leaf": 30,
            "early_stopping": False,
            "random_state": RANDOM_STATE,
        },
        "model_path": str(model_path.relative_to(ROOT)),
        "predictions_path": str(prediction_path.relative_to(ROOT)),
        "interpretation": "Validation and final-test metrics come from models that never train on their evaluation season. After evaluation, the deployment artifact is refit on every completed season through 2025-26; 2026-27 remains excluded.",
    }
    report_path = REPORT_DIR / "next_gw_model_metrics.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Validation (trained through 2023-24; evaluated on 2024-25):")
    print(json.dumps(validation_report, indent=2))
    print("Final test (trained through 2024-25; evaluated on 2025-26):")
    print(json.dumps(test_report, indent=2))
    if live_report:
        print("Current-season diagnostic (2026-27):")
        print(json.dumps(live_report, indent=2))
    print(f"\nSaved deployment model trained through {max(frame.loc[production_mask, 'season'])}: {model_path}")
    print(f"Saved report: {report_path}")
    print(f"Saved test predictions: {prediction_path}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fantasyiq.features import GROUP, add_features, create_grid


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "processed" / "player_gameweeks.csv.gz"
OUTPUT_DIR = ROOT / "data" / "processed"
OUTPUT = OUTPUT_DIR / "next_gw_training.csv.gz"
def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Training source not found: {SOURCE}. Run scripts/collect_training_data.py first.")
    source = pd.read_csv(SOURCE, low_memory=False)
    source["season"] = source["season"].astype(str)
    source["gameweek"] = pd.to_numeric(source["gameweek"], errors="raise").astype(int)
    source["player_id"] = pd.to_numeric(source["player_id"], errors="raise").astype(int)
    if source.duplicated([*GROUP, "gameweek"]).any():
        raise ValueError("Input contains duplicate player-season-gameweek rows. Re-run the collection step.")

    grid = create_grid(source)
    training = add_features(grid)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    training.to_csv(OUTPUT, index=False, compression="gzip")

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(SOURCE.relative_to(ROOT)),
        "output": str(OUTPUT.relative_to(ROOT)),
        "rows": len(training),
        "id_columns": ["season", "player_id", "player_name"],
        "feature_columns": [
            column for column in training.columns
            if column not in {"season", "player_id", "player_name", "target_gameweek", "target_points_next_gw"}
        ],
        "categorical_feature_columns": ["position"],
        "label_column": "target_points_next_gw",
        "target": "player's total FPL points in the immediately following gameweek",
        "features_use_current_and_prior_completed_gameweeks": True,
        "excluded_fields": ["source_xp", "team name"],
        "caveats": [
            "Missing player-gameweek rows after a player's first observed round are treated as zero performance; this covers blanks and non-appearances.",
            "Features use outcomes through the observation gameweek; target is shifted one gameweek forward within the same season and player.",
            "Rows without a collected next gameweek are excluded, so the latest completed round has no label yet.",
            "Price and ownership use the last available prior-round snapshot; team name is excluded because historical team labels can reflect season-end metadata.",
            "Expected-stat features can be absent in older seasons and remain null; handle this with an explicit model imputation strategy.",
        ],
    }
    (OUTPUT_DIR / "next_gw_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved {len(training):,} player-round samples from {training['season'].nunique()} seasons.")
    print(f"Features: {len(manifest['feature_columns'])}")
    print(f"Dataset: {OUTPUT}")


if __name__ == "__main__":
    main()

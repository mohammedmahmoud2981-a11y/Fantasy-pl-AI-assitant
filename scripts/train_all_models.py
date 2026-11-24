from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(name: str, *args: str) -> None:
    script = SCRIPTS / name
    print(f"\n=== {name} ===", flush=True)
    subprocess.run([sys.executable, str(script), *args], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FantasyIQ's reproducible model build and evaluation pipeline.")
    parser.add_argument("--skip-slow-evaluations", action="store_true", help="Skip expanding-season, recommender, transfer, and RL backtests.")
    parser.add_argument("--evaluations-only", action="store_true", help="Run evaluations without rebuilding the trained models.")
    args = parser.parse_args()

    if not args.evaluations_only:
        run("build_next_gw_features.py")
        run("train_next_gw_model.py")
        run("train_high_potential_classifier.py")
        run("train_player_profiles.py")
        interactions = ROOT / "data/processed/user_player_interactions.csv"
        if interactions.exists():
            run("train_collaborative_recommender.py")
        else:
            print("Skipping collaborative model: data/processed/user_player_interactions.csv is absent. Collect public picks first.")
    if not args.skip_slow_evaluations:
        run("evaluate_rolling_seasons.py")
        for season in ("2023-24", "2024-25", "2025-26"):
            run("evaluate_hybrid_recommender.py", season)
        run("backtest_transfer_policy.py")
        run("train_transfer_rl.py")
    print("\nFantasyIQ model pipeline finished.")


if __name__ == "__main__":
    main()

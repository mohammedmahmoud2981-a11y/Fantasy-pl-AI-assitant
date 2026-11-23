from __future__ import annotations

import numpy as np
import pandas as pd


GROUP = ["season", "player_id"]
ZERO_STATS = [
    "total_points", "minutes", "starts", "goals_scored", "assists", "clean_sheets",
    "goals_conceded", "own_goals", "penalties_saved", "penalties_missed", "saves",
    "yellow_cards", "red_cards", "bonus", "bps", "tackles", "recoveries",
    "clearances_blocks_interceptions", "defensive_contribution",
]
ROLLING_STATS = [
    "total_points", "minutes", "starts", "goals_scored", "assists", "clean_sheets",
    "saves", "bonus", "bps", "expected_goals", "expected_assists",
    "expected_goal_involvements", "expected_goals_conceded",
]


def create_grid(source: pd.DataFrame) -> pd.DataFrame:
    bounds = source.groupby(GROUP, sort=False)["gameweek"].min().rename("first_gw").reset_index()
    last_by_season = source.groupby("season", sort=False)["gameweek"].max()
    bounds["last_gw"] = bounds["season"].map(last_by_season)
    grids = [
        pd.DataFrame({
            "season": row.season,
            "player_id": row.player_id,
            "gameweek": np.arange(int(row.first_gw), int(row.last_gw) + 1, dtype=np.int16),
        })
        for row in bounds.itertuples(index=False)
    ]
    frame = pd.concat(grids, ignore_index=True).merge(
        source, on=[*GROUP, "gameweek"], how="left", validate="one_to_one",
    )
    frame = frame.sort_values([*GROUP, "gameweek"]).reset_index(drop=True)
    for column in ZERO_STATS:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    for column in ("value", "selected"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
            frame[column] = frame.groupby(GROUP, sort=False)[column].ffill()
    for column in ROLLING_STATS:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ("player_name", "position", "team", "team_id"):
        if column in frame:
            frame[column] = frame.groupby(GROUP, sort=False)[column].transform(lambda series: series.ffill().bfill())
    return frame


def add_features(frame: pd.DataFrame, keep_unlabeled: bool = False) -> pd.DataFrame:
    frame = frame.sort_values([*GROUP, "gameweek"]).reset_index(drop=True)
    grouped = frame.groupby(GROUP, sort=False, group_keys=False)
    base_columns = ["season", "player_id", "player_name", "position", "gameweek"]
    base = frame[base_columns].copy()
    computed: dict[str, pd.Series] = {
        "season_start_year": pd.to_numeric(frame["season"].str[:4], errors="coerce"),
    }

    for stat in ROLLING_STATS:
        if stat not in frame:
            continue
        values = pd.to_numeric(frame[stat], errors="coerce")
        stat_group = values.groupby([frame["season"], frame["player_id"]], sort=False)
        for window in (3, 5):
            name = f"{stat}_mean_{window}gw"
            rolled = stat_group.rolling(window, min_periods=1).mean()
            computed[name] = rolled.reset_index(level=GROUP, drop=True).sort_index()
        name = f"{stat}_season_mean"
        expanded = stat_group.expanding(min_periods=1).mean()
        computed[name] = expanded.reset_index(level=GROUP, drop=True).sort_index()

    if "value" in frame:
        computed["price_m"] = pd.to_numeric(frame["value"], errors="coerce") / 10
    if "selected" in frame:
        computed["selected_managers"] = pd.to_numeric(frame["selected"], errors="coerce")
    computed["season_points_to_date"] = grouped["total_points"].cumsum()
    computed["season_minutes_to_date"] = grouped["minutes"].cumsum()
    computed["weeks_seen"] = grouped.cumcount() + 1

    target_gameweek = frame["gameweek"] + 1
    target_points = grouped["total_points"].shift(-1)
    combined = pd.concat([
        base,
        pd.DataFrame(computed),
        target_gameweek.rename("target_gameweek"),
        target_points.rename("target_points_next_gw"),
    ], axis=1)
    if keep_unlabeled:
        return combined
    training = combined.loc[combined["target_points_next_gw"].notna()].copy()
    training["target_points_next_gw"] = training["target_points_next_gw"].astype("int16")
    return training

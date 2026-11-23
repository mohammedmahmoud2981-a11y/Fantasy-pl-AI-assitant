# FantasyIQ data

## Collected snapshot

`processed/player_gameweeks.csv.gz` is the current training table: one row per player per gameweek, covering 2016/17–2026/27. The first ten seasons come from the public Vaastav FPL archive; 2026/27 completed and checked rounds come from the FPL API. The current snapshot contains 250,907 rows across 11 seasons, with gameweeks 1–10 collected for 2026/27.

Raw downloads are retained separately:

- `raw/archive/<season>/merged_gw.csv.gz` — source player/match rows.
- `raw/archive/<season>/players_raw.csv.gz` — season player IDs, positions, and team metadata used to enrich older rows.
- `raw/fpl/<season>/bootstrap-static.json` and `fixtures.json` — current season metadata.
- `raw/fpl/<season>/gameweeks/gwNN/live.json` — one bulk player response per confirmed gameweek.
- `processed/manifest.json` — collection timestamp, row counts, columns, and known caveats.

## Recollect or update

From the project root, with the project dependencies installed:

```powershell
py scripts\collect_training_data.py
```

The default run reuses downloaded archive CSVs, refreshes checked gameweeks from the current FPL season, and rebuilds the compressed training table. To refresh the archived source files too:

```powershell
py scripts\collect_training_data.py --refresh-archive
```

For a smaller historical range, pass season start years, such as `--start-year 2020 --end-year 2025`.

## Table fields

Each row includes season, gameweek, player ID and name, position, team labels, performance stats, and source. Available columns vary by season because FPL has added statistics over time. Common fields include:

- `total_points` — target value for a future points model.
- `minutes`, `starts`, `goals_scored`, `assists`, `clean_sheets`, `saves`, `bonus`, `bps` — gameweek outcome/performance fields.
- `expected_goals`, `expected_assists`, `expected_goal_involvements`, `expected_goals_conceded` — expected performance fields where present.
- `value`, `selected`, `transfers_in`, `transfers_out` — price, ownership, and transfer context where present.
- `source_xp` — archived FPL `ep_this` projection. Do **not** use this as a model input: the archive notes it may have been captured after a gameweek and can leak post-match information.
- `fixture_count` — number of fixtures represented for the player-gameweek.

In the archive, player-gameweek rows are aggregated from match rows. Performance totals are summed across fixtures; snapshot fields use the last row in the gameweek. The FPL live endpoint already returns gameweek-level totals.

The pandemic-affected 2019/20 archive contains FPL event numbers above 38 (up to 47). These original round numbers are retained as supplied by the source.

## Before model training

Do not shuffle-split this dataset. A prediction for gameweek N must only use facts available before its deadline. Construct rolling features from earlier rounds using a per-player shift, keep `total_points` for N as the label, and evaluate by training on earlier gameweeks/seasons and validating on later ones. Exclude `source_xp` unless a separately timestamped pre-deadline snapshot is collected.

The current-season position and club labels come from the current bootstrap and may reflect a transfer or reclassification later in the season. They are useful for browsing the snapshot, but should not be treated as historically correct pre-deadline features without historical snapshots.

## Build the next-gameweek training table

After collecting the player-gameweek table, run:

```powershell
py scripts\build_next_gw_features.py
```

This writes `processed/next_gw_training.csv.gz`, with rolling 3- and 5-gameweek performance features and `target_points_next_gw`. It shifts the target by one round for each player within each season, pads missing rounds after the player's first observed round with zero performance, and omits the latest round until its next-round target is collected. It excludes archived xP and team name from the features. See `processed/next_gw_manifest.json` for the generated feature list and caveats.

To train and evaluate the reference model:

```powershell
py scripts\train_next_gw_model.py
```

This trains a HistGradientBoostingRegressor and compares it to a training-mean baseline and a last-3-gameweeks baseline. It uses 2024/25 for a temporal validation checkpoint, evaluates the final model on the held-out 2025/26 season, and reports 2026/27 separately as an in-progress diagnostic. Artifacts are written to `models/` and `reports/`.

To train the position-relative high-potential classifier:

```powershell
py scripts\train_high_potential_classifier.py
```

The positive class is defined by the per-position 75th percentile of next-gameweek points, calculated on the training seasons for each split. It reports precision, recall, F1, ROC AUC, and average precision under the same chronological validation/test seasons.

## Sources

- [FPL API](https://fantasy.premierleague.com/api/) for the current season. `event/{gameweek}/live/` returns all players for one round; only rounds marked finished and data-checked are included.
- [Vaastav Fantasy Premier League archive](https://github.com/vaastav/Fantasy-Premier-League) for 2016/17–2025/26. The downloaded match-level columns are described in its [data dictionary](https://github.com/vaastav/Fantasy-Premier-League/blob/master/DATA_DICTIONARY.md).

The FPL API is an internal, unversioned endpoint. The archive and API are community/public data sources; this educational project is not affiliated with the Premier League.

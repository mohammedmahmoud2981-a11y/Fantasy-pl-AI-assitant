from __future__ import annotations

import argparse
import gzip
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data"
ARCHIVE_ROOT = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
FPL_ROOT = "https://fantasy.premierleague.com/api"
USER_AGENT = "FantasyIQ/0.1 educational project data collection"
POSITION_CODES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
SUM_STATS = {
    "total_points", "minutes", "starts", "goals_scored", "assists", "clean_sheets",
    "goals_conceded", "own_goals", "penalties_saved", "penalties_missed", "saves",
    "yellow_cards", "red_cards", "bonus", "bps", "influence", "creativity", "threat",
    "ict_index", "expected_goals", "expected_assists", "expected_goal_involvements",
    "expected_goals_conceded", "tackles", "recoveries", "clearances_blocks_interceptions",
    "defensive_contribution", "mng_clean_sheets", "mng_draw", "mng_goals_scored",
    "mng_loss", "mng_underdog_draw", "mng_underdog_win", "mng_win",
}
ID_COLUMNS = ["season", "gameweek", "player_id"]


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json,text/csv,*/*"})
    retry = Retry(total=5, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def season_name(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def fetch(session: requests.Session, url: str) -> requests.Response:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    return response


def save_json(path: Path, content: bytes) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return json.loads(content)


def download_archive(session: requests.Session, seasons: list[str], refresh: bool) -> list[pd.DataFrame]:
    frames = []
    for season in seasons:
        path = DATA_ROOT / "raw" / "archive" / season / "merged_gw.csv.gz"
        if refresh or not path.exists():
            url = f"{ARCHIVE_ROOT}/{season}/gws/merged_gw.csv"
            try:
                response = fetch(session, url)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    print(f"Archive not available for {season}; skipping.")
                    continue
                raise
            path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(path, "wb", compresslevel=6) as output:
                output.write(response.content)
            print(f"Downloaded {season}: {len(response.content):,} bytes")
            time.sleep(0.25)

        metadata_path = path.parent / "players_raw.csv.gz"
        if refresh or not metadata_path.exists():
            metadata_url = f"{ARCHIVE_ROOT}/{season}/players_raw.csv"
            try:
                metadata_response = fetch(session, metadata_url)
            except requests.HTTPError as exc:
                raise RuntimeError(f"The player metadata file is required for season {season}.") from exc
            with gzip.open(metadata_path, "wb", compresslevel=6) as output:
                output.write(metadata_response.content)
            print(f"Downloaded {season} player metadata: {len(metadata_response.content):,} bytes")
            time.sleep(0.25)

        # The archive has non-UTF-8 player names in some seasons.
        frame = pd.read_csv(path, low_memory=False, encoding="latin-1")
        metadata = pd.read_csv(metadata_path, low_memory=False, encoding="latin-1")
        if "element" not in frame or not ({"round", "GW"} & set(frame.columns)):
            raise ValueError(f"Unexpected archive schema for {season}: {path}")
        round_column = "round" if "round" in frame.columns else "GW"
        frame = frame.rename(columns={"element": "player_id", round_column: "gameweek", "name": "player_name", "xP": "source_xp"})
        metadata["player_id"] = pd.to_numeric(metadata["id"], errors="coerce")
        metadata["metadata_name"] = (metadata["first_name"].fillna("") + " " + metadata["second_name"].fillna("")).str.strip()
        metadata["metadata_position"] = metadata["element_type"].map(POSITION_CODES)
        metadata = metadata[["player_id", "metadata_name", "metadata_position", "team"]].rename(columns={"team": "team_id"})
        frame = frame.merge(metadata, on="player_id", how="left")
        if "position" not in frame:
            frame["position"] = frame["metadata_position"]
        else:
            frame["position"] = frame["position"].fillna(frame["metadata_position"])
        if "team_id" not in frame:
            frame["team_id"] = pd.NA
        if "team" not in frame or pd.api.types.is_numeric_dtype(frame["team"]):
            frame["team"] = frame["team_id"].astype("string")
        frame["player_name"] = frame["metadata_name"].fillna(frame["player_name"])
        frame["season"] = season
        frame["source"] = "vaastav-archive"
        frame["position"] = frame["position"].replace({"GK": "GK", "DEF": "DEF", "MID": "MID", "FWD": "FWD"})
        frame["player_id"] = pd.to_numeric(frame["player_id"], errors="coerce")
        frame["gameweek"] = pd.to_numeric(frame["gameweek"], errors="coerce")
        frames.append(frame)
        print(f"Loaded {season}: {len(frame):,} match rows")
    return frames


def collect_current_season(session: requests.Session) -> tuple[pd.DataFrame, dict]:
    season_dir = DATA_ROOT / "raw" / "fpl"
    bootstrap_response = fetch(session, f"{FPL_ROOT}/bootstrap-static/")
    bootstrap = save_json(season_dir / "bootstrap-static.json", bootstrap_response.content)
    fixtures_response = fetch(session, f"{FPL_ROOT}/fixtures/")
    fixtures = save_json(season_dir / "fixtures.json", fixtures_response.content)

    first_deadline = next((event.get("deadline_time") for event in bootstrap.get("events", []) if event.get("deadline_time")), None)
    if not first_deadline:
        raise ValueError("Could not infer the current season from FPL gameweek deadlines.")
    current_season = season_name(datetime.fromisoformat(first_deadline.replace("Z", "+00:00")).year)
    player_meta = {}
    for player in bootstrap.get("elements", []):
        player_meta[player["id"]] = {
            "player_name": f"{player.get('first_name', '')} {player.get('second_name', '')}".strip(),
            "position": POSITION_CODES.get(player.get("element_type"), "UNK"),
            "team_id": player.get("team"),
        }
    team_names = {team["id"]: team["name"] for team in bootstrap.get("teams", [])}
    fixture_counts: dict[tuple[int, int], int] = {}
    for fixture in fixtures:
        event_id = fixture.get("event")
        if event_id is None:
            continue
        for team_id in (fixture.get("team_h"), fixture.get("team_a")):
            key = (int(event_id), int(team_id))
            fixture_counts[key] = fixture_counts.get(key, 0) + 1

    season_dir = DATA_ROOT / "raw" / "fpl" / current_season
    # Keep current-season snapshots together under their season directory.
    season_dir.mkdir(parents=True, exist_ok=True)
    (season_dir / "bootstrap-static.json").write_bytes(bootstrap_response.content)
    (season_dir / "fixtures.json").write_bytes(fixtures_response.content)

    confirmed_events = [
        event for event in bootstrap.get("events", [])
        if event.get("finished") and event.get("data_checked")
    ]
    skipped_events = [
        event.get("id") for event in bootstrap.get("events", [])
        if not (event.get("finished") and event.get("data_checked"))
    ]
    frames = []
    downloaded_events = []
    for event in confirmed_events:
        gameweek = int(event["id"])
        response = fetch(session, f"{FPL_ROOT}/event/{gameweek}/live/")
        payload = save_json(season_dir / "gameweeks" / f"gw{gameweek:02d}" / "live.json", response.content)
        downloaded_events.append(gameweek)
        for element in payload.get("elements", []):
            player_id = int(element["id"])
            meta = player_meta.get(player_id, {})
            stats = dict(element.get("stats", {}))
            stats.update({
                "season": current_season,
                "gameweek": gameweek,
                "player_id": player_id,
                "player_name": meta.get("player_name", ""),
                "position": meta.get("position", "UNK"),
                "team_id": meta.get("team_id"),
                "team": team_names.get(meta.get("team_id")),
                "fixture_count": fixture_counts.get((gameweek, meta.get("team_id")), 0),
                "source": "fpl-api-live",
            })
            frames.append(stats)
        print(f"Collected confirmed {current_season} GW{gameweek}: {len(payload.get('elements', [])):,} players")
        time.sleep(0.25)

    manifest = {
        "season": current_season,
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": FPL_ROOT,
        "player_count_in_bootstrap": len(player_meta),
        "confirmed_gameweeks_downloaded": downloaded_events,
        "unconfirmed_gameweeks_skipped": skipped_events,
        "note": "Only finished gameweeks with data_checked=true are included in processed training data.",
    }
    manifest_path = season_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return pd.DataFrame(frames), manifest


def aggregate_player_gameweeks(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        raise ValueError("No season data was collected.")
    data = pd.concat(frames, ignore_index=True, sort=False)
    data = data[data["position"].isin(["GK", "DEF", "MID", "FWD"])].copy()
    data["gameweek"] = pd.to_numeric(data["gameweek"], errors="coerce")
    data["player_id"] = pd.to_numeric(data["player_id"], errors="coerce")
    data = data.dropna(subset=ID_COLUMNS)
    data["gameweek"] = data["gameweek"].astype(int)
    data["player_id"] = data["player_id"].astype(int)

    sum_columns = [column for column in SUM_STATS if column in data.columns]
    for column in sum_columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    aggregate = {
        column: ("sum" if column in sum_columns else "last")
        for column in data.columns if column not in ID_COLUMNS and column != "fixture_count"
    }
    if "fixture" in data.columns:
        aggregate["fixture"] = "nunique"
    elif "fixture_count" in data.columns:
        aggregate["fixture_count"] = "last"
    result = data.groupby(ID_COLUMNS, sort=False, dropna=False).agg(aggregate).reset_index()
    if "fixture" in result.columns:
        result = result.rename(columns={"fixture": "fixture_count"})
    if "metadata_name" in result:
        result = result.drop(columns=["metadata_name"])
    if "metadata_position" in result:
        result = result.drop(columns=["metadata_position"])
    result = result.sort_values(["season", "gameweek", "player_id"]).reset_index(drop=True)
    result["gameweek"] = result["gameweek"].astype("int16")
    result["player_id"] = result["player_id"].astype("int32")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect archived and current Fantasy Premier League player-gameweek data.")
    parser.add_argument("--start-year", type=int, default=2016, help="First archived season start year (default: 2016).")
    parser.add_argument("--end-year", type=int, default=2025, help="Last archived season start year (default: 2025).")
    parser.add_argument("--skip-archive", action="store_true", help="Use only the current season FPL API data.")
    parser.add_argument("--skip-current", action="store_true", help="Use only completed archive seasons.")
    parser.add_argument("--refresh-archive", action="store_true", help="Re-download archived season files.")
    args = parser.parse_args()
    if args.end_year < args.start_year:
        parser.error("--end-year must be greater than or equal to --start-year")

    session = make_session()
    frames: list[pd.DataFrame] = []
    if not args.skip_archive:
        seasons = [season_name(year) for year in range(args.start_year, args.end_year + 1)]
        frames.extend(download_archive(session, seasons, args.refresh_archive))

    current_manifest = None
    if not args.skip_current:
        current_frame, current_manifest = collect_current_season(session)
        if not current_frame.empty:
            frames.append(current_frame)

    player_gameweeks = aggregate_player_gameweeks(frames)
    processed_dir = DATA_ROOT / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    output_path = processed_dir / "player_gameweeks.csv.gz"
    player_gameweeks.to_csv(output_path, index=False, compression="gzip")

    collection_manifest = {
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(player_gameweeks),
        "player_count": int(player_gameweeks["player_id"].nunique()),
        "season_counts": {str(key): int(value) for key, value in player_gameweeks.groupby("season").size().items()},
        "columns": list(player_gameweeks.columns),
        "output": str(output_path.relative_to(ROOT)),
        "current_fpl_collection": current_manifest,
        "known_caveats": [
            "Archived source xP is the historical FPL ep_this field and may be post-match; do not use it as a model feature.",
            "Use only information available before the target gameweek when constructing prediction features.",
            "Archived rows are aggregated across fixtures to one player-gameweek; totals are summed and snapshot fields use the last fixture row.",
            "Current-season club and position labels come from the current bootstrap and can reflect later transfers or reclassification.",
        ],
    }
    (processed_dir / "manifest.json").write_text(json.dumps(collection_manifest, indent=2), encoding="utf-8")
    print(f"\nSaved {len(player_gameweeks):,} player-gameweek rows from {player_gameweeks['season'].nunique()} seasons.")
    print(f"Players: {collection_manifest['player_count']:,}")
    print(f"Dataset: {output_path}")
    print(f"Manifest: {processed_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()

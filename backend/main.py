from __future__ import annotations

import threading
import time
from pathlib import Path

import pandas as pd
import json
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from fantasyiq.data import load_players
from fantasyiq.optimizer import optimize_squad
from fantasyiq.recommender import hybrid_recommendations
from fantasyiq.prediction import CLASSIFIER_PATH, MODEL_PATH, SOURCE as TRAINING_SOURCE, infer_current_season, predict_next_gameweek


app = FastAPI(title="FantasyIQ API", version="0.2.0", description="FPL player analytics and squad optimization")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

_cache_lock = threading.Lock()
_cached_data: tuple[pd.DataFrame, dict[int, str], dict[int, str], list[dict]] | None = None
_cache_time = 0.0
_CACHE_TTL_SECONDS = 900
PROFILE_PATH = Path(__file__).resolve().parents[1] / "reports" / "player_profiles.csv"
PROFILE_METRICS_PATH = Path(__file__).resolve().parents[1] / "reports" / "player_profile_metrics.json"
TRANSFER_RL_REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "transfer_rl_metrics.json"
HYBRID_EVAL_REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "hybrid_recommender_evaluation.json"
_prediction_lock = threading.Lock()
_prediction_cache: pd.DataFrame | None = None
_prediction_cache_key: tuple | None = None
_prediction_cache_time = 0.0


def get_data():
    global _cached_data, _cache_time
    if _cached_data is not None and time.monotonic() - _cache_time < _CACHE_TTL_SECONDS:
        return _cached_data
    with _cache_lock:
        if _cached_data is None or time.monotonic() - _cache_time >= _CACHE_TTL_SECONDS:
            try:
                _cached_data = load_players()
                _cache_time = time.monotonic()
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Could not load the FPL data feed: {exc}") from exc
    return _cached_data


def json_records(frame: pd.DataFrame) -> list[dict]:
    records = frame.to_dict(orient="records")
    clean = []
    for record in records:
        item = {}
        for key, value in record.items():
            if value is None or (pd.api.types.is_scalar(value) and pd.isna(value)):
                continue
            if hasattr(value, "item"):
                value = value.item()
            elif hasattr(value, "tolist"):
                value = value.tolist()
            item[key] = value
        clean.append(item)
    return clean


def current_gameweek(events: list[dict]) -> dict | None:
    return next(
        (event for event in events if event.get("is_current")),
        next((event for event in events if event.get("is_next")), None),
    )


def upcoming_gameweek(events: list[dict]) -> dict | None:
    return next(
        (event for event in events if event.get("is_next")),
        next((event for event in events if not event.get("finished")), None),
    )


def get_model_predictions(events: list[dict]) -> tuple[pd.DataFrame, int | None]:
    global _prediction_cache, _prediction_cache_key, _prediction_cache_time
    if not MODEL_PATH.exists() or not TRAINING_SOURCE.exists():
        return pd.DataFrame(columns=["player_id", "fantasyiq_points", "high_potential_probability", "prediction_gameweek"]), None
    season = infer_current_season(events)
    classifier_mtime = Path(CLASSIFIER_PATH).stat().st_mtime_ns if Path(CLASSIFIER_PATH).exists() else 0
    cache_key = (season, Path(MODEL_PATH).stat().st_mtime_ns, classifier_mtime, Path(TRAINING_SOURCE).stat().st_mtime_ns)
    if _prediction_cache is not None and _prediction_cache_key == cache_key and time.monotonic() - _prediction_cache_time < _CACHE_TTL_SECONDS:
        return _prediction_cache, int(_prediction_cache["prediction_gameweek"].max()) if not _prediction_cache.empty else None
    with _prediction_lock:
        if _prediction_cache is None or _prediction_cache_key != cache_key or time.monotonic() - _prediction_cache_time >= _CACHE_TTL_SECONDS:
            try:
                _prediction_cache, _ = predict_next_gameweek(season)
                _prediction_cache_key = cache_key
                _prediction_cache_time = time.monotonic()
            except Exception as exc:
                raise HTTPException(status_code=503, detail=f"Could not generate FantasyIQ predictions: {exc}") from exc
    target_gw = int(_prediction_cache["prediction_gameweek"].max()) if not _prediction_cache.empty else None
    upcoming = upcoming_gameweek(events)
    if target_gw is not None and upcoming and int(upcoming["id"]) != target_gw:
        return pd.DataFrame(columns=["player_id", "fantasyiq_points", "high_potential_probability", "prediction_gameweek"]), None
    return _prediction_cache, target_gw


@app.get("/")
def root():
    return {"status": "ok", "service": "FantasyIQ API", "health": "/api/health", "docs": "/docs"}


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "FantasyIQ API"}


@app.get("/api/fpl-team/{entry_id}")
def fpl_team(entry_id: int, event: int | None = None):
    """Load a public FPL team's latest picks and bank using its team ID."""
    if entry_id < 1:
        raise HTTPException(status_code=422, detail="FPL team ID must be positive.")
    try:
        entry_response = requests.get(f"https://fantasy.premierleague.com/api/entry/{entry_id}/", timeout=15)
        if entry_response.status_code == 404:
            raise HTTPException(status_code=404, detail="FPL team ID was not found.")
        entry_response.raise_for_status()
        entry = entry_response.json()
        _, _, _, events = get_data()
        target_gw = event or (upcoming_gameweek(events) or current_gameweek(events) or {}).get("id")
        if not target_gw:
            raise HTTPException(status_code=503, detail="No gameweek is available yet.")
        candidate_gws = [target_gw] if event else sorted(
            (int(row["id"]) for row in events if row.get("finished") or row.get("is_current") or row.get("is_next")),
            reverse=True,
        )
        picks = None
        gw = None
        for candidate_gw in candidate_gws:
            picks_response = requests.get(f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{candidate_gw}/picks/", timeout=15)
            if picks_response.status_code == 404 and not event:
                continue
            picks_response.raise_for_status()
            candidate_picks = picks_response.json()
            if len(candidate_picks.get("picks", [])) == 15:
                picks, gw = candidate_picks, candidate_gw
                break
        if picks is None:
            raise HTTPException(status_code=404, detail="No saved 15-player picks were found for this FPL team yet.")
    except HTTPException:
        raise
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Could not load the FPL team: {exc}") from exc
    team_picks = picks.get("picks", [])
    player_ids = [int(row["element"]) for row in team_picks]
    if len(player_ids) != 15:
        raise HTTPException(status_code=404, detail="This team has no saved 15-player squad for the selected gameweek.")
    players, _, _, _ = get_data()
    squad = players[players["id"].isin(player_ids)].copy()
    preds, _ = get_model_predictions(events)
    pmap = preds.set_index("player_id")["fantasyiq_points"] if not preds.empty else pd.Series(dtype=float)
    squad["fantasyiq_points"] = squad["id"].map(pmap)
    squad["expected_points"] = squad["fantasyiq_points"].fillna(squad["expected_points"])
    pick_map = {int(row["element"]): row for row in team_picks}
    squad["squad_order"] = squad["id"].map(lambda player_id: int(pick_map[int(player_id)].get("position", 15)))
    squad["is_captain"] = squad["id"].map(lambda player_id: bool(pick_map[int(player_id)].get("is_captain", False)))
    squad["is_vice_captain"] = squad["id"].map(lambda player_id: bool(pick_map[int(player_id)].get("is_vice_captain", False)))
    squad["multiplier"] = squad["id"].map(lambda player_id: int(pick_map[int(player_id)].get("multiplier", 1)))
    history = picks.get("entry_history", {}).get("bank", entry.get("last_deadline_bank", 0)) / 10
    return {"entry_id": entry_id, "team_name": entry.get("name"), "manager": f"{entry.get('player_first_name','')} {entry.get('player_last_name','')}".strip(),
            "event": gw, "bank": history, "free_transfers": 1,
            "captain_id": next((int(row["element"]) for row in team_picks if row.get("is_captain")), None),
            "vice_captain_id": next((int(row["element"]) for row in team_picks if row.get("is_vice_captain")), None),
            "players": json_records(squad.sort_values("squad_order"))}


@app.get("/api/overview")
def overview():
    players, positions, teams, events = get_data()
    gameweek = current_gameweek(events)
    predictions, prediction_gw = get_model_predictions(events)
    return {
        "player_count": int(len(players)),
        "available_count": int((players["status"] == "a").sum()),
        "club_count": len(teams),
        "gameweek": gameweek,
        "prediction_gameweek": prediction_gw or (upcoming_gameweek(events) or {}).get("id"),
        "model_ready": not predictions.empty,
        "positions": list(positions.values()),
        "clubs": list(teams.values()),
    }


@app.get("/api/players")
def players_list(
    position: str | None = None,
    club: str | None = None,
    search: str | None = None,
    min_minutes: int = Query(default=0, ge=0),
    include_unavailable: bool = False,
    limit: int = Query(default=100, ge=1, le=700),
):
    players, _, _, events = get_data()
    predictions, _ = get_model_predictions(events)
    view = players.copy()
    prediction_map = predictions.set_index("player_id")["fantasyiq_points"] if not predictions.empty else pd.Series(dtype=float)
    view["fantasyiq_points"] = view["id"].map(prediction_map)
    probability_map = predictions.set_index("player_id")["high_potential_probability"] if "high_potential_probability" in predictions else pd.Series(dtype=float)
    view["high_potential_probability"] = view["id"].map(probability_map)
    if not include_unavailable:
        view = view[view["status"] == "a"]
    if position:
        view = view[view["position"].str.casefold() == position.casefold()]
    if club:
        view = view[view["team_name"].str.casefold() == club.casefold()]
    if search:
        view = view[view["player"].str.contains(search, case=False, regex=False)]
    view = view[view["minutes"] >= min_minutes].copy()
    view["ranking_points"] = view["fantasyiq_points"].fillna(view["expected_points"])
    view = view.sort_values("ranking_points", ascending=False).head(limit).drop(columns=["ranking_points"])
    return {"count": int(len(view)), "players": json_records(view)}


@app.get("/api/predictions")
def predictions_list(limit: int = Query(default=100, ge=1, le=700)):
    players, _, _, events = get_data()
    predictions, prediction_gw = get_model_predictions(events)
    if predictions.empty:
        raise HTTPException(status_code=503, detail="FantasyIQ model or current-season history is not ready.")
    names = players[["id", "player", "position", "team_name", "cost_m", "status"]].rename(columns={"id": "player_id"})
    view = predictions.merge(names, on="player_id", how="left")
    view = view.sort_values("fantasyiq_points", ascending=False).head(limit)
    return {
        "prediction_gameweek": prediction_gw,
        "last_completed_gameweek": int(predictions["prediction_gameweek"].max()) - 1,
        "model_ready": True,
        "players": json_records(view),
    }


@app.get("/api/analytics/player-profiles")
def player_profiles(limit: int = Query(default=30, ge=1, le=500), anomalies_only: bool = False):
    if not PROFILE_PATH.exists() or not PROFILE_METRICS_PATH.exists():
        raise HTTPException(status_code=503, detail="Player profile analysis has not been trained yet.")
    try:
        profiles = pd.read_csv(PROFILE_PATH)
        metrics = json.loads(PROFILE_METRICS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"Player profile artifacts could not be read: {exc}") from exc
    if anomalies_only:
        profiles = profiles[profiles["is_anomaly"].astype(bool)]
    return {"metrics": metrics, "count": min(limit, len(profiles)), "players": json_records(profiles.head(limit))}


@app.get("/api/analytics/transfer-policy")
def transfer_policy_report():
    if not TRANSFER_RL_REPORT_PATH.exists():
        raise HTTPException(status_code=503, detail="Transfer-policy evaluation has not been run yet.")
    try:
        return json.loads(TRANSFER_RL_REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"Transfer-policy report could not be read: {exc}") from exc


@app.get("/api/analytics/recommender-evaluation")
def recommender_evaluation():
    if not HYBRID_EVAL_REPORT_PATH.exists():
        raise HTTPException(status_code=503, detail="Hybrid recommender evaluation has not been run yet.")
    try:
        return json.loads(HYBRID_EVAL_REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"Recommender evaluation report could not be read: {exc}") from exc


@app.get("/api/recommendations/transfers")
def transfer_recommendations(
    player_id: int = Query(ge=1),
    budget: float = Query(default=15.0, ge=0.0, le=120.0, description="Maximum budget available for the replacement"),
    limit: int = Query(default=5, ge=1, le=20),
    include_unavailable: bool = False,
    free_transfers: int = Query(default=1, ge=1, le=5),
    extra_transfers: int = Query(default=0, ge=0, le=20, description="Number of transfers beyond the free transfers"),
):
    """Recommend same-position replacements, ranked by projected gain and value."""
    players, _, _, events = get_data()
    predictions, prediction_gw = get_model_predictions(events)
    current_rows = players[players["id"] == player_id]
    if current_rows.empty:
        raise HTTPException(status_code=404, detail="Player was not found.")
    current = current_rows.iloc[0]
    position = current["position"]

    pool = players[players["position"] == position].copy()
    if not include_unavailable:
        pool = pool[pool["status"] == "a"]
    prediction_map = predictions.set_index("player_id")["fantasyiq_points"] if not predictions.empty else pd.Series(dtype=float)
    probability_map = predictions.set_index("player_id")["high_potential_probability"] if "high_potential_probability" in predictions else pd.Series(dtype=float)
    pool["fantasyiq_points"] = pool["id"].map(prediction_map)
    pool["high_potential_probability"] = pool["id"].map(probability_map)
    pool["recommendation_points"] = pool["fantasyiq_points"].fillna(pool["expected_points"])
    current_price = float(current["cost_m"])
    current_prediction = prediction_map.get(player_id, float("nan"))
    current_points = float(current_prediction if pd.notna(current_prediction) else current["expected_points"])
    pool = pool[(pool["id"] != player_id) & (pool["cost_m"] <= current_price + budget)].copy()
    if pool.empty:
        raise HTTPException(status_code=422, detail="No eligible same-position replacement fits this budget.")

    if not predictions.empty:
        model_player_ids = set(predictions["player_id"].astype(int))
        pool = pool[(pool["minutes"] >= 90) | pool["id"].isin(model_player_ids)].copy()
    if pool.empty:
        raise HTTPException(status_code=422, detail="No replacement has enough recent data for a reliable comparison.")

    pool["points_gain"] = pool["recommendation_points"] - current_points
    pool["transfers_needed"] = 1
    pool["transfer_cost"] = max(0, extra_transfers - free_transfers) * 4
    pool["net_points_gain"] = pool["points_gain"] - pool["transfer_cost"]
    pool["price_difference"] = pool["cost_m"] - current_price
    pool["value_per_million"] = pool["recommendation_points"] / pool["cost_m"].clip(lower=0.1)
    pool = hybrid_recommendations(pool, current, limit=limit)
    if pool.empty:
        raise HTTPException(status_code=422, detail="No eligible alternatives found for this player.")
    pool = pool.sort_values(["net_points_gain", "hybrid_score"], ascending=False)
    replacements = pool.drop(columns=["expected_points"]).rename(columns={"recommendation_points": "expected_points"})
    return {
        "current_player": json_records(current_rows)[0],
        "current_projection": round(current_points, 2),
        "position": position,
        "available_budget": budget,
        "free_transfers": free_transfers,
        "extra_transfers": extra_transfers,
        "hit_points": max(0, extra_transfers - free_transfers) * 4,
        "prediction_gameweek": prediction_gw or (upcoming_gameweek(events) or {}).get("id"),
        "recommendations": json_records(replacements.drop(columns=["recommendation_points"], errors="ignore")),
    }


@app.get("/api/recommendations/plan")
def transfer_plan(
    player_ids: str = Query(description="Comma-separated player IDs to replace"),
    squad_ids: str = Query(description="Comma-separated IDs for all 15 players in the user's current squad"),
    bank: float = Query(default=0.0, ge=0.0, le=120.0, description="Money already in the bank"),
    free_transfers: int = Query(default=1, ge=1, le=5),
    limit: int = Query(default=1, ge=1, le=5),
):
    """Find a legal, same-position replacement plan for selected players."""
    try:
        ids = list(dict.fromkeys(int(value.strip()) for value in player_ids.split(",") if value.strip()))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="player_ids must be comma-separated integers.") from exc
    if not ids or len(ids) > 5:
        raise HTTPException(status_code=422, detail="Select between 1 and 5 players to replace.")
    try:
        full_squad_ids = list(dict.fromkeys(int(value.strip()) for value in squad_ids.split(",") if value.strip()))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="squad_ids must be comma-separated integers.") from exc
    if len(full_squad_ids) != 15 or not set(ids).issubset(full_squad_ids):
        raise HTTPException(status_code=422, detail="Provide all 15 current squad IDs, including every player being replaced.")

    players, _, _, events = get_data()
    predictions, prediction_gw = get_model_predictions(events)
    squad = players[players["id"].isin(full_squad_ids)].copy()
    if len(squad) != len(full_squad_ids):
        raise HTTPException(status_code=404, detail="One or more squad players were not found.")
    current = squad[squad["id"].isin(ids)].copy()
    if len(current) != len(ids):
        raise HTTPException(status_code=404, detail="One or more selected players were not found.")
    if (current["status"] != "a").any():
        raise HTTPException(status_code=422, detail="Selected players must be currently available.")
    position_counts = {"Goalkeeper": 2, "Defender": 5, "Midfielder": 5, "Forward": 3}
    if squad["position"].value_counts().to_dict() != position_counts:
        raise HTTPException(status_code=422, detail="squad_ids must describe a legal 2-5-5-3 FPL squad.")
    if current["position"].duplicated().any():
        raise HTTPException(status_code=422, detail="Choose at most one outgoing player per position for this plan.")

    pred = predictions.set_index("player_id")["fantasyiq_points"] if not predictions.empty else pd.Series(dtype=float)
    prob = predictions.set_index("player_id")["high_potential_probability"] if "high_potential_probability" in predictions else pd.Series(dtype=float)
    pool = players[players["status"] == "a"].copy()
    pool["fantasyiq_points"] = pool["id"].map(pred)
    pool["high_potential_probability"] = pool["id"].map(prob)
    # Missing FPL/model projections must not become NaN in transfer gains or
    # leak into the JSON response (Starlette's JSON encoder rejects NaN).
    pool["plan_points"] = pd.to_numeric(
        pool["fantasyiq_points"].fillna(pool["expected_points"]), errors="coerce"
    ).replace([float("inf"), float("-inf")], pd.NA).fillna(0.0)
    model_ids = set(predictions["player_id"].astype(int)) if not predictions.empty else set()
    pool = pool[(pool["minutes"] >= 90) | pool["id"].isin(model_ids)]
    current_points = float(pd.to_numeric(
        squad["id"].map(pred).fillna(squad["expected_points"]), errors="coerce"
    ).replace([float("inf"), float("-inf")], pd.NA).fillna(0.0).sum())
    current_cost = float(squad["cost_m"].sum())
    choices = []
    for row in current.itertuples(index=False):
        candidates = pool[(pool["position"] == row.position) & (pool["id"] != row.id)].copy()
        outgoing_points = float(pred.get(row.id, row.expected_points))
        candidates["gain"] = candidates["plan_points"] - outgoing_points
        candidates["price_difference"] = candidates["cost_m"] - float(row.cost_m)
        candidates = candidates.sort_values(["gain", "plan_points"], ascending=False).head(20)
        if candidates.empty:
            raise HTTPException(status_code=422, detail=f"No viable replacement for {row.player}.")
        choices.append((row, candidates))

    plans = []
    def search(index: int, chosen: list[dict], used: set[int], cost_delta: float, gain: float, club_counts: dict[int, int]):
        if len(plans) >= limit and gain <= plans[-1]["gross_points_gain"]:
            return
        if index == len(choices):
            if cost_delta > bank:
                return
            count = len(chosen)
            hits = max(0, count - free_transfers) * 4
            plans.append({"replacements": chosen.copy(), "cost_delta": cost_delta, "gross_points_gain": gain,
                          "transfers": count, "free_transfers_used": min(count, free_transfers),
                          "hit_points": hits, "net_points_gain": gain - hits})
            plans.sort(key=lambda item: item["net_points_gain"], reverse=True)
            del plans[limit:]
            return
        outgoing, candidates = choices[index]
        for candidate in candidates.to_dict(orient="records"):
            new_id = int(candidate["id"])
            club = int(candidate["team"])
            if new_id in used or club_counts.get(club, 0) >= 3:
                continue
            chosen.append({"out": json_records(pd.DataFrame([outgoing._asdict()]))[0],
                           "in": json_records(pd.DataFrame([{key: value for key, value in candidate.items() if key != "plan_points"}]))[0],
                           "points_gain": round(float(candidate["gain"]), 2),
                           "price_difference": round(float(candidate["price_difference"]), 1)})
            used.add(new_id); club_counts[club] = club_counts.get(club, 0) + 1
            search(index + 1, chosen, used, cost_delta + float(candidate["price_difference"]), gain + float(candidate["gain"]), club_counts)
            club_counts[club] -= 1; used.remove(new_id); chosen.pop()

    outgoing_club_counts = squad.groupby("team").size().to_dict()
    for outgoing in current.itertuples(index=False):
        outgoing_club_counts[outgoing.team] -= 1
    search(0, [], set(full_squad_ids), 0.0, 0.0, {int(club): int(count) for club, count in outgoing_club_counts.items()})
    if not plans:
        raise HTTPException(status_code=422, detail="No transfer plan fits your bank and squad constraints.")
    for plan in plans:
        plan["gross_points_gain"] = round(plan["gross_points_gain"], 2)
        plan["net_points_gain"] = round(plan["net_points_gain"], 2)
        plan["cost_delta"] = round(plan["cost_delta"], 1)
    for plan in plans:
        plan["projected_squad_points"] = round(current_points + plan["gross_points_gain"], 2)
        plan["remaining_bank"] = round(bank - plan["cost_delta"], 1)
    return {"player_ids": ids, "bank": bank, "current_squad_projection": round(current_points, 2),
            "prediction_gameweek": prediction_gw, "plans": plans}


@app.get("/api/squad")
def squad(budget: float = Query(default=100.0, ge=80.0, le=120.0), include_unavailable: bool = False):
    players, _, _, events = get_data()
    predictions, prediction_gw = get_model_predictions(events)
    pool = players if include_unavailable else players[players["status"] == "a"]
    pool = pool.copy()
    prediction_map = predictions.set_index("player_id")["fantasyiq_points"] if not predictions.empty else pd.Series(dtype=float)
    probability_map = predictions.set_index("player_id")["high_potential_probability"] if "high_potential_probability" in predictions else pd.Series(dtype=float)
    pool["fantasyiq_points"] = pool["id"].map(prediction_map)
    pool["high_potential_probability"] = pool["id"].map(probability_map)
    pool["projection_source"] = pool["fantasyiq_points"].notna().map({True: "FantasyIQ", False: "FPL fallback"})
    pool["expected_points"] = pool["fantasyiq_points"].fillna(pool["expected_points"])
    try:
        selected = optimize_squad(pool, budget_millions=budget)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    cost = float(selected["cost_m"].sum())
    return {
        "budget": budget,
        "cost": round(cost, 1),
        "remaining_budget": round(budget - cost, 1),
        "combined_fantasyiq_projection": round(float(selected["expected_points"].sum()), 2),
        "prediction_gameweek": prediction_gw or (upcoming_gameweek(events) or {}).get("id"),
        "fantasyiq_players": int((selected["projection_source"] == "FantasyIQ").sum()),
        "fpl_fallback_players": int((selected["projection_source"] == "FPL fallback").sum()),
        "players": json_records(selected),
    }

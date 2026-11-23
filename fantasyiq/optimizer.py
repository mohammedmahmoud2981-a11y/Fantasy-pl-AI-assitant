from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix


SQUAD_COUNTS = {"Goalkeeper": 2, "Defender": 5, "Midfielder": 5, "Forward": 3}


def optimize_squad(players: pd.DataFrame, budget_millions: float = 100.0) -> pd.DataFrame:
    """Choose a legal 15-player FPL squad maximizing feed-provided expected points."""
    pool = players.copy().reset_index(drop=True)
    pool = pool[pool["position"].isin(SQUAD_COUNTS)].reset_index(drop=True)
    if pool.empty:
        raise ValueError("No eligible players are available to optimize.")

    cost = pool["cost_m"].to_numpy(dtype=float)
    xp = pool["expected_points"].to_numpy(dtype=float)
    if not np.isfinite(cost).all() or not np.isfinite(xp).all():
        raise ValueError("Player prices or expected points contain invalid values.")

    constraints = []
    lower = []
    upper = []
    rows, cols, values = [], [], []
    row = 0

    # Position quotas.
    for position, quota in SQUAD_COUNTS.items():
        indices = np.flatnonzero(pool["position"].to_numpy() == position)
        if len(indices) < quota:
            raise ValueError(f"Not enough {position.lower()}s in the selected player pool.")
        rows.extend([row] * len(indices)); cols.extend(indices.tolist()); values.extend([1.0] * len(indices))
        lower.append(quota); upper.append(quota); row += 1

    # Budget uses tenths of a million, the FPL price precision.
    rows.extend([row] * len(pool)); cols.extend(range(len(pool))); values.extend(cost.tolist())
    lower.append(-np.inf); upper.append(float(budget_millions)); row += 1

    # No more than three players from a club.
    club_ids = pool["team"].to_numpy()
    for club in pd.unique(club_ids):
        indices = np.flatnonzero(club_ids == club)
        rows.extend([row] * len(indices)); cols.extend(indices.tolist()); values.extend([1.0] * len(indices))
        lower.append(-np.inf); upper.append(3.0); row += 1

    matrix = coo_matrix((values, (rows, cols)), shape=(row, len(pool))).tocsr()
    result = milp(
        c=-xp,
        integrality=np.ones(len(pool)),
        bounds=Bounds(np.zeros(len(pool)), np.ones(len(pool))),
        constraints=LinearConstraint(matrix, np.asarray(lower), np.asarray(upper)),
        options={"time_limit": 20.0},
    )
    if not result.success or result.x is None:
        raise ValueError("No legal squad fits this budget and availability filter. Try raising the budget or including more players.")

    selected = pool.loc[result.x > 0.5].copy()
    if len(selected) != 15:
        raise RuntimeError("The optimizer did not return a complete 15-player squad.")
    return selected.sort_values(["position", "expected_points"], ascending=[True, False]).reset_index(drop=True)

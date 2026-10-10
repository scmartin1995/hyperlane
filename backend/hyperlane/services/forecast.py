"""Monte Carlo forecasting over weekly throughput.

Two questions:
  how_many  – "how many items will we finish in the next N weeks?"
  when      – "when will we have finished N more items?"

Weekly throughput is sampled with replacement from the last `history_weeks` *complete* weeks
(the current, partial week is excluded; weeks before the first completed item are dropped so a
young project is not diluted with zeros). Fewer than 4 weeks with any throughput -> `warning`. Percentiles follow the usual forecasting convention:
for `how_many`, pXX is the number of items you can expect to finish with XX% confidence (so
p85 <= p50); for `when`, pXX is the date by which you finish with XX% confidence (p50 <= p85).
"""

from __future__ import annotations

import random
import zlib
from collections import Counter
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..models import Project
from . import metrics

NOT_ENOUGH = "Not enough history; forecast is a guess"
MAX_WEEKS = 520


MIN_HISTORY_WEEKS = 4


def history_counts(db: Session, project: Project, history_weeks: int) -> list[int]:
    """Done-item counts for the last `history_weeks` complete weeks (oldest first), from the first
    week that has any throughput."""
    rows = metrics.throughput(db, project, weeks=history_weeks + 1)["weeks"]
    counts = [int(r["count"]) for r in rows[:-1]]  # drop the current partial week
    while counts and counts[0] == 0:
        counts.pop(0)
    return counts


def monte_carlo(
    db: Session,
    project: Project,
    *,
    mode: str,
    weeks: int | None = None,
    items: int | None = None,
    sims: int = 5000,
    history_weeks: int = 12,
    seed: int | None = None,
) -> dict[str, Any]:
    if mode not in ("how_many", "when"):
        raise ValueError("mode must be how_many or when")
    sims = max(100, min(int(sims), 50_000))
    history_weeks = max(1, min(int(history_weeks), 104))
    samples = history_counts(db, project, history_weeks)
    rng = random.Random(seed if seed is not None else zlib.crc32(project.id.encode()))

    warning: str | None = None
    if sum(1 for c in samples if c > 0) < MIN_HISTORY_WEEKS:
        warning = NOT_ENOUGH
    pool = samples if any(samples) else [0]

    out: dict[str, Any] = {
        "mode": mode,
        "simulations": sims,
        "history_weeks": history_weeks,
        "samples": samples,
        "warning": warning,
    }

    if mode == "how_many":
        n_weeks = max(1, int(weeks or 2))
        totals = [sum(rng.choice(pool) for _ in range(n_weeks)) for _ in range(sims)]
        hist = Counter(totals)
        out["how_many"] = {
            "weeks": n_weeks,
            # confidence convention: pXX = you finish at least this many with XX% probability
            "p50": int(metrics.percentile(totals, 50)),
            "p70": int(metrics.percentile(totals, 30)),
            "p85": int(metrics.percentile(totals, 15)),
            "p95": int(metrics.percentile(totals, 5)),
            "histogram": [{"value": v, "count": c} for v, c in sorted(hist.items())],
        }
        return out

    n_items = max(1, int(items or 10))
    if not any(pool):
        out["warning"] = NOT_ENOUGH
    weeks_needed: list[int] = []
    for _ in range(sims):
        done = 0
        w = 0
        while done < n_items and w < MAX_WEEKS:
            done += rng.choice(pool)
            w += 1
        weeks_needed.append(w)
    tdy = metrics.today()

    def to_date(w: float) -> str:
        return (tdy + timedelta(weeks=round(w))).isoformat()

    hist = Counter(weeks_needed)
    out["when"] = {
        "items": n_items,
        "p50_date": to_date(metrics.percentile(weeks_needed, 50)),
        "p70_date": to_date(metrics.percentile(weeks_needed, 70)),
        "p85_date": to_date(metrics.percentile(weeks_needed, 85)),
        "p95_date": to_date(metrics.percentile(weeks_needed, 95)),
        "histogram": [{"date": to_date(w), "count": c} for w, c in sorted(hist.items())],
    }
    if max(weeks_needed) >= MAX_WEEKS and out["warning"] is None:
        out["warning"] = "Some simulations never finished; throughput is too low for this scope"
    return out

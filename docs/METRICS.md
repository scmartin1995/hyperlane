# Telemetry: what the numbers mean

Plain-English definitions for every metric Hyperlane shows. Formulas are what the server computes.

## Flow & agile metrics
| Metric | Meaning | How it's computed |
|---|---|---|
| **Velocity** | Work finished per sprint | Σ points (or item count when estimation = throughput) of items completed inside each closed sprint. Average = last 3–5 sprints. |
| **Committed vs completed** | How well planning predicted delivery | Snapshot of the sprint's scope at start (`SprintCommitment`) vs what reached a *done* state by close. |
| **Throughput** | Items finished per week | Count of items whose `completed_at` falls in each Monday-to-Sunday week. |
| **Cycle time** | How long work takes once started | First transition into an *in progress* state → first transition into *done*. Shown as p50 / p85 / p95 and a scatter plot. |
| **Lead time** | How long from request to done | `created_at` → `completed_at`. |
| **WIP** | Work in progress right now | Items currently in any *in progress* category state. Limits come from the workflow editor. |
| **Flow efficiency** | Share of time spent actively working | Time in *in progress* states ÷ total cycle time, averaged over recent done items. Blocked time counts as waiting. |
| **Cumulative flow** | Where work piles up | Per day, how many items sat in each workflow state (reconstructed from the transition log). Widening bands = bottleneck. |
| **Burndown / burnup** | Sprint progress against the plan | Daily remaining (scope − done) vs the ideal straight line; burnup shows done and scope separately so scope creep is visible. |
| **Health score** | One number for "is this project OK?" | 0–100 built from signals: WIP breaches, velocity trend, blocked items, overdue items, sprint on-track ratio. Each signal is listed with why. |

## Forecasting (Monte Carlo)
Instead of guessing a date, Hyperlane samples your real weekly throughput thousands of times:
- **How many?** – "In the next N weeks we'll finish between X (p85) and Y (p50) items."
- **When?** – "N items will be done by *date* with 85 % confidence."
Percentiles: p50 is a coin flip, p85 is a reasonable commitment, p95 is conservative. With fewer than
4 weeks of history the forecast carries a warning.

## Capacity learning
At every sprint close Hyperlane records planned vs completed points per person and updates an
exponentially weighted profile (recent sprints matter more): average points, throughput, points per
available hour, commitment accuracy and consistency. Planning uses those profiles to suggest how much
each person can take, scaled by their days off and focus factor. Confidence grows with sprints observed.

## Earned value management (AgileEVM)
Configure a **Budget at Completion (BAC)**, the planned scope (points) and the planned schedule
(sprints or dates), then lock the baseline.

| Term | Formula | Read it as |
|---|---|---|
| **PV** Planned value | BAC × planned % complete (sprints elapsed ÷ planned sprints, or working days elapsed ÷ total) | What we should have earned by now |
| **EV** Earned value | BAC × (completed points ÷ planned points) | What we actually earned |
| **AC** Actual cost | Σ actual cost (or hours × rate, or completed points × cost/point) | What we spent |
| **SV** Schedule variance | EV − PV | Negative = behind schedule |
| **CV** Cost variance | EV − AC | Negative = over budget |
| **SPI** Schedule performance index | EV ÷ PV | < 1 behind, > 1 ahead |
| **CPI** Cost performance index | EV ÷ AC | < 1 over budget, > 1 under |
| **EAC** Estimate at completion | BAC ÷ CPI | Projected total cost |
| **ETC** Estimate to complete | EAC − AC | Money still needed |
| **VAC** Variance at completion | BAC − EAC | Negative = will overspend |
| **TCPI** To-complete performance index | (BAC − EV) ÷ (BAC − AC) | Efficiency required from here to hit budget |

Status thresholds: SPI and CPI ≥ 0.95 → on track; ≥ 0.85 → at risk; below → off track.
Daily snapshots build the S-curve (PV, EV, AC over time). Re-lock the baseline after a deliberate
scope change, otherwise EV drifts.

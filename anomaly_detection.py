"""
Sudden performance-change detection for StaffScore.

For every employee with enough monthly history, this module splits their
Overall_Score history in half chronologically (an earlier "baseline" period
and a later "recent" period) and runs a one-way ANOVA (scipy.stats.f_oneway)
comparing the two periods. An employee is FLAGGED when both are true:

  1. Statistical significance — the ANOVA p-value is below `alpha`, meaning
     the difference between the two periods is unlikely to be random noise.
  2. Practical significance — the mean score actually moved by at least
     `min_change` points, so we don't flag noisy-but-tiny wobbles.

This surfaces employees whose performance jumped or dropped abruptly,
which is exactly the kind of thing a manager wants to double-check —
either to recognise a genuine improvement or step in early on a decline.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from calculations import build_monthly_scores

DEFAULT_ALPHA = 0.05          # statistical significance threshold (p-value)
DEFAULT_MIN_CHANGE = 10.0     # minimum swing in Overall_Score points to matter
DEFAULT_MIN_MONTHS = 4        # need at least this many months of history to test


@dataclass
class FlagResult:
    employee_id: int
    months_count: int
    baseline_mean: float
    recent_mean: float
    change: float
    f_stat: float
    p_value: float
    direction: str
    flagged: bool
    reason: str


def _split_scores(scores):
    """Split a chronologically-ordered list of scores into an earlier
    'baseline' half and a later 'recent' half. If the count is odd, the
    extra month goes into the recent half so the test leans toward
    detecting the most current change."""
    n = len(scores)
    cut = n // 2
    baseline = scores[:cut]
    recent = scores[cut:]
    return baseline, recent


def evaluate_employee(scores, alpha=DEFAULT_ALPHA, min_change=DEFAULT_MIN_CHANGE,
                       min_months=DEFAULT_MIN_MONTHS, employee_id=None):
    """Run the ANOVA test for a single employee's chronological score list.
    Returns a FlagResult (flagged=False with a reason if there isn't enough
    data to test)."""
    n = len(scores)
    if n < min_months:
        return FlagResult(employee_id, n, float("nan"), float("nan"), float("nan"),
                           float("nan"), float("nan"), "insufficient data",
                           False, f"Needs at least {min_months} months of history (has {n}).")

    baseline, recent = _split_scores(scores)
    if len(baseline) < 2 or len(recent) < 2:
        return FlagResult(employee_id, n, float("nan"), float("nan"), float("nan"),
                           float("nan"), float("nan"), "insufficient data",
                           False, "Not enough months in one of the two periods to test.")

    # If either group has zero variance in both groups simultaneously,
    # f_oneway divides by zero — guard against that degenerate case.
    if np.std(baseline) == 0 and np.std(recent) == 0:
        f_stat, p_value = 0.0, 1.0
    else:
        f_stat, p_value = stats.f_oneway(baseline, recent)

    baseline_mean = float(np.mean(baseline))
    recent_mean = float(np.mean(recent))
    change = recent_mean - baseline_mean
    direction = "Improved" if change > 0 else ("Declined" if change < 0 else "No change")

    is_significant = (not np.isnan(p_value)) and p_value < alpha
    is_meaningful = abs(change) >= min_change
    flagged = is_significant and is_meaningful

    if flagged:
        reason = (f"{direction} by {abs(change):.1f} pts "
                  f"({baseline_mean:.1f} -> {recent_mean:.1f}), ANOVA p={p_value:.4f}")
    elif is_significant and not is_meaningful:
        reason = "Statistically significant but change is small — not flagged."
    elif is_meaningful and not is_significant:
        reason = "Score moved but not statistically significant (could be noise)."
    else:
        reason = "Stable performance."

    return FlagResult(employee_id, n, baseline_mean, recent_mean, change,
                       float(f_stat), float(p_value), direction, flagged, reason)


def detect_flagged_employees(employees_df, performance_df, weights,
                              alpha=DEFAULT_ALPHA, min_change=DEFAULT_MIN_CHANGE,
                              min_months=DEFAULT_MIN_MONTHS):
    """
    Run the ANOVA sudden-change test for every employee.

    Returns a DataFrame (one row per employee that has *any* performance
    history) with columns:
        employee_id, name, department, months_count, baseline_score,
        recent_score, change, f_stat, p_value, direction, flagged, reason
    Sorted so flagged employees appear first, largest absolute change first.
    """
    monthly = build_monthly_scores(performance_df, weights).sort_values("month")

    rows = []
    for employee_id, emp_history in monthly.groupby("employee_id"):
        scores = emp_history.sort_values("month")["Overall_Score"].tolist()
        result = evaluate_employee(scores, alpha=alpha, min_change=min_change,
                                    min_months=min_months, employee_id=employee_id)
        rows.append(result)

    if not rows:
        return pd.DataFrame(columns=[
            "employee_id", "name", "department", "months_count", "baseline_score",
            "recent_score", "change", "f_stat", "p_value", "direction", "flagged", "reason",
        ])

    result_df = pd.DataFrame([{
        "employee_id": r.employee_id,
        "months_count": r.months_count,
        "baseline_score": r.baseline_mean,
        "recent_score": r.recent_mean,
        "change": r.change,
        "f_stat": r.f_stat,
        "p_value": r.p_value,
        "direction": r.direction,
        "flagged": r.flagged,
        "reason": r.reason,
    } for r in rows])

    result_df = employees_df[["employee_id", "name", "department"]].merge(
        result_df, on="employee_id", how="right"
    )

    result_df["abs_change"] = result_df["change"].abs()
    result_df = result_df.sort_values(
        by=["flagged", "abs_change"], ascending=[False, False]
    ).drop(columns="abs_change").reset_index(drop=True)

    return result_df

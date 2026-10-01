"""
All the scoring + salary/bonus formulas used across the app, in one place,
so that Dashboard, Dataset and Employee pages always agree with each other.

Salary & Bonus model
---------------------
    In Hand Salary = Monthly Base Salary + HRA + Allowance + Total Bonus

    Total Bonus = Performance Bonus     (% of Monthly Base Salary, from bonus_policy)
                + Spot Bonus            (one-time individual reward)
                + Team Bonus share      (team pool split evenly across its members)
                + Profit-Sharing share  (company pool split evenly across all employees)
                + Referral Bonus        (paid referrals only)

Performance Bonus is the only component computed from the Overall Score;
the other four are one-time/period events recorded directly in their own
tables and simply summed up for whichever date range is selected.
"""

import streamlit as st
import pandas as pd


def date_range_filter(performance_df, key_prefix=""):
    """Show a date range picker and return performance_df filtered to that range (by month).
    If there's no performance data yet (e.g. a brand-new database with no employees
    added), there's nothing to filter — just return the empty dataframe as-is."""
    if performance_df.empty:
        return performance_df

    all_months = sorted(performance_df["month"].unique())
    min_date, max_date = pd.to_datetime(all_months[0]), pd.to_datetime(all_months[-1])

    date_range = st.date_input("Date Range", value=(min_date, max_date),
                                min_value=min_date, max_value=max_date, key=f"{key_prefix}_range")
    start, end = date_range if isinstance(date_range, tuple) and len(date_range) == 2 else (min_date, max_date)

    start_month, end_month = str(start)[:7], str(end)[:7]
    return performance_df[(performance_df["month"] >= start_month) & (performance_df["month"] <= end_month)]


def _month_in_range(month_series, performance_df_in_range):
    """Boolean mask: which rows of month_series fall inside the min/max month
    currently present in performance_df_in_range (i.e. the selected date range)."""
    if performance_df_in_range.empty:
        return pd.Series([False] * len(month_series), index=month_series.index)
    lo, hi = performance_df_in_range["month"].min(), performance_df_in_range["month"].max()
    return (month_series >= lo) & (month_series <= hi)


def add_kpi_columns(df):
    """Add Task Completion Rate, On-Time Delivery Rate, Customer Satisfaction
    and Attendance Rate columns to a performance-style dataframe."""
    df = df.copy()
    df["Task_Completion_Rate"] = (df["completed_tasks"] / df["assigned_tasks"]) * 100
    df["On_Time_Delivery_Rate"] = (
        df["completed_before_deadline"] / df["completed_tasks"].replace(0, pd.NA)
    ) * 100
    df["On_Time_Delivery_Rate"] = df["On_Time_Delivery_Rate"].fillna(0)
    df["Customer_Satisfaction"] = (df["customer_rating"] / 5) * 100
    df["Attendance_Rate"] = (df["present_days"] / df["working_days"]) * 100
    return df


def add_overall_score(df, weights):
    """Add Overall_Score column using the given KPI weights dict."""
    df = df.copy()
    df["Overall_Score"] = (
        weights["task"] * df["Task_Completion_Rate"]
        + weights["ontime"] * df["On_Time_Delivery_Rate"]
        + weights["satisfaction"] * df["Customer_Satisfaction"]
        + weights["attendance"] * df["Attendance_Rate"]
    )
    return df


def add_bonus_column(df, bonus_policy_df):
    """Add Bonus_Percent column by looking up each Overall_Score in the bonus policy table."""
    df = df.copy()

    def lookup_bonus(score):
        for _, row in bonus_policy_df.iterrows():
            if row["min_score"] <= score <= row["max_score"]:
                return float(row["bonus_percent"])
        return 0.0

    df["Bonus_Percent"] = df["Overall_Score"].apply(lookup_bonus)
    return df


def build_employee_summary(employees_df, performance_df, weights, bonus_policy_df):
    """
    Combine all months of performance per employee into one summary row,
    then apply the KPI / Overall Score / Bonus-% formulas on the totals.
    This is the table used by the Dashboard and Dataset pages.
    """
    totals = performance_df.groupby("employee_id").agg(
        assigned_tasks=("assigned_tasks", "sum"),
        completed_tasks=("completed_tasks", "sum"),
        completed_before_deadline=("completed_before_deadline", "sum"),
        working_days=("working_days", "sum"),
        present_days=("present_days", "sum"),
        customer_rating=("customer_rating", "mean"),
    ).reset_index()

    summary = employees_df.merge(totals, on="employee_id", how="left")
    summary = add_kpi_columns(summary)
    summary = add_overall_score(summary, weights)
    summary = add_bonus_column(summary, bonus_policy_df)
    return summary


def build_monthly_scores(performance_df, weights):
    """Per employee, per month KPI + Overall Score (used for the Employee trend chart)."""
    monthly = add_kpi_columns(performance_df)
    monthly = add_overall_score(monthly, weights)
    return monthly


def get_recommendation(score):
    """Rule-based recommendation text, matching the brief's 3 scenarios."""
    if score >= 90:
        return "Highest Bonus, Promotion Candidate"
    elif score >= 60:
        return "Normal Bonus, Training Recommended"
    else:
        return "No Bonus, Performance Improvement Plan (PIP)"


# ==========================================================================
# Salary + full bonus breakdown
# ==========================================================================

def add_salary_columns(summary_df, salary_df):
    """Merge fixed monthly salary components (base, HRA, allowance) onto the
    summary and add a Performance_Bonus_Amount column (= bonus % applied to
    the monthly base salary, i.e. the "basic salary")."""
    df = summary_df.merge(salary_df, on="employee_id", how="left")
    for col in ("monthly_base_salary", "hra", "allowance"):
        df[col] = df[col].fillna(0)
    df["Performance_Bonus"] = df["monthly_base_salary"] * df["Bonus_Percent"] / 100
    df["Monthly_Fixed_Salary"] = df["monthly_base_salary"] + df["hra"] + df["allowance"]
    return df


def aggregate_spot_bonus(spot_bonus_df, performance_df_in_range):
    """Total Spot Bonus per employee, for whichever months are in range."""
    if spot_bonus_df.empty:
        return pd.DataFrame(columns=["employee_id", "Spot_Bonus"])
    mask = _month_in_range(spot_bonus_df["month"], performance_df_in_range)
    totals = spot_bonus_df[mask].groupby("employee_id")["amount"].sum().reset_index()
    return totals.rename(columns={"amount": "Spot_Bonus"})


def aggregate_team_bonus(team_bonus_df, team_members_df, performance_df_in_range):
    """Total Team Bonus share per employee: each team_bonus record's
    total_amount is split evenly across that team's current members, for
    whichever months are in range."""
    if team_bonus_df.empty or team_members_df.empty:
        return pd.DataFrame(columns=["employee_id", "Team_Bonus"])

    mask = _month_in_range(team_bonus_df["month"], performance_df_in_range)
    in_range = team_bonus_df[mask]

    member_counts = team_members_df.groupby("team_id")["employee_id"].nunique()
    shares = []
    for _, row in in_range.iterrows():
        count = member_counts.get(row["team_id"], 0)
        if count == 0:
            continue
        per_member = float(row["total_amount"]) / count
        members = team_members_df[team_members_df["team_id"] == row["team_id"]]["employee_id"]
        for emp_id in members:
            shares.append({"employee_id": emp_id, "Team_Bonus": per_member})

    if not shares:
        return pd.DataFrame(columns=["employee_id", "Team_Bonus"])
    return pd.DataFrame(shares).groupby("employee_id")["Team_Bonus"].sum().reset_index()


def aggregate_profit_sharing(profit_sharing_df, employees_df, performance_df_in_range):
    """Total Profit-Sharing share per employee: each period's pool_amount is
    split evenly across every current employee, for periods in range."""
    if profit_sharing_df.empty or employees_df.empty:
        return pd.DataFrame(columns=["employee_id", "Profit_Share_Bonus"])

    mask = _month_in_range(profit_sharing_df["period"], performance_df_in_range)
    in_range = profit_sharing_df[mask]
    if in_range.empty:
        return pd.DataFrame(columns=["employee_id", "Profit_Share_Bonus"])

    per_employee_total = in_range["pool_amount"].astype(float).sum() / len(employees_df)
    return pd.DataFrame({
        "employee_id": employees_df["employee_id"],
        "Profit_Share_Bonus": per_employee_total,
    })


def aggregate_referral_bonus(referral_df, performance_df_in_range):
    """Total Referral Bonus per employee — only bonuses that have actually
    been marked 'Paid', for whichever payout months are in range."""
    if referral_df.empty:
        return pd.DataFrame(columns=["employee_id", "Referral_Bonus"])
    paid = referral_df[referral_df["eligibility_status"] == "Paid"].copy()
    if paid.empty:
        return pd.DataFrame(columns=["employee_id", "Referral_Bonus"])
    mask = _month_in_range(paid["payout_month"].fillna(""), performance_df_in_range)
    totals = paid[mask].groupby("referrer_employee_id")["bonus_amount"].sum().reset_index()
    return totals.rename(columns={"referrer_employee_id": "employee_id", "bonus_amount": "Referral_Bonus"})

def build_department_analytics(summary_df, full_summary_df):
    """Per-department rollup for whatever date range summary_df /
    full_summary_df were already built for: headcount, average score,
    attendance, task completion, and total bonus cost. Reuses the same
    tables the Dashboard already computes, so these numbers always agree
    with everything else shown there. Sorted best average score first."""
    headcount = summary_df.groupby("department")["employee_id"].count().rename("Employees")
    avg_score = summary_df.groupby("department")["Overall_Score"].mean().rename("Avg_Score")
    avg_attendance = summary_df.groupby("department")["Attendance_Rate"].mean().rename("Attendance")
    avg_task_completion = summary_df.groupby("department")["Task_Completion_Rate"].mean().rename("Task_Completion")
    bonus_cost = full_summary_df.groupby("department")["Total_Bonus"].sum().rename("Bonus_Cost")

    dept_df = pd.concat(
        [headcount, avg_score, avg_attendance, avg_task_completion, bonus_cost], axis=1
    ).reset_index()
    return dept_df.sort_values("Avg_Score", ascending=False).reset_index(drop=True)


def format_lakhs(amount):
    """Indian-style short form for large rupee amounts, e.g. 320000 -> '₹3.2L'."""
    return f"₹{amount / 100000:.1f}L"

def build_full_salary_summary(summary_df, performance_df_in_range, salary_df,
                                spot_bonus_df, team_bonus_df, team_members_df,
                                profit_sharing_df, employees_df, referral_df):
    """Combine performance-based summary + every bonus source into the final
    salary breakdown table: Monthly_Fixed_Salary, each bonus component,
    Total_Bonus and In_Hand_Salary (for the selected date range)."""
    df = add_salary_columns(summary_df, salary_df)

    for component_df, col in (
        (aggregate_spot_bonus(spot_bonus_df, performance_df_in_range), "Spot_Bonus"),
        (aggregate_team_bonus(team_bonus_df, team_members_df, performance_df_in_range), "Team_Bonus"),
        (aggregate_profit_sharing(profit_sharing_df, employees_df, performance_df_in_range), "Profit_Share_Bonus"),
        (aggregate_referral_bonus(referral_df, performance_df_in_range), "Referral_Bonus"),
    ):
        df = df.merge(component_df, on="employee_id", how="left")
        df[col] = df[col].fillna(0)

    df["Total_Bonus"] = (
        df["Performance_Bonus"] + df["Spot_Bonus"] + df["Team_Bonus"]
        + df["Profit_Share_Bonus"] + df["Referral_Bonus"]
    )
    df["In_Hand_Salary"] = df["Monthly_Fixed_Salary"] + df["Total_Bonus"]
    return df

def build_budget_utilization(budgets_df, employees_df, performance_df, weights, bonus_policy_df,
                              salary_df, spot_bonus_df, team_bonus_df, team_members_df,
                              profit_sharing_df, referral_df):
    """For each row in budgets_df (department, period_start, period_end,
    allocated_amount), computes how much of that budget has actually been
    spent: the total of every bonus component (Performance, Spot, Team,
    Profit-Sharing, Referral) paid to employees in that department during
    that period.

    Pooled bonus types (Team, Profit-Sharing) are always calculated against
    the FULL company for that period first, using the same aggregation
    functions as the rest of the app, and only summed down to one
    department afterward - splitting a pooled bonus using just a
    department's headcount as the denominator would overstate that
    department's real share and disagree with what the rest of the app
    shows for the same employees.

    Returns budgets_df with Spent, Remaining, Percent_Used and Status
    columns added. Status is "OK" below 90% used, "Near Limit" from 90% to
    100%, and "Over Budget" past that - informational only, nothing here
    blocks a bonus from being recorded."""
    if budgets_df.empty:
        return budgets_df.assign(Spent=0.0, Remaining=0.0, Percent_Used=0.0, Status="OK")

    period_cache = {}
    rows = []

    for _, budget in budgets_df.iterrows():
        period_key = (str(budget["period_start"]), str(budget["period_end"]))

        if period_key not in period_cache:
            start_month, end_month = period_key[0][:7], period_key[1][:7]
            period_perf = performance_df[
                (performance_df["month"] >= start_month) & (performance_df["month"] <= end_month)
            ]
            if period_perf.empty:
                period_cache[period_key] = None
            else:
                summary = build_employee_summary(employees_df, period_perf, weights, bonus_policy_df)
                period_cache[period_key] = build_full_salary_summary(
                    summary, period_perf, salary_df, spot_bonus_df, team_bonus_df,
                    team_members_df, profit_sharing_df, employees_df, referral_df,
                )

        full_summary = period_cache[period_key]

        if full_summary is None:
            spent = 0.0
        elif budget["department"] == "ALL":
            spent = float(full_summary["Total_Bonus"].sum())
        else:
            spent = float(full_summary.loc[full_summary["department"] == budget["department"], "Total_Bonus"].sum())

        allocated = float(budget["allocated_amount"])
        remaining = allocated - spent
        pct_used = (spent / allocated * 100) if allocated > 0 else 0.0
        status = "Over Budget" if pct_used >= 100 else ("Near Limit" if pct_used >= 90 else "OK")

        rows.append({
            **budget.to_dict(),
            "Spent": spent,
            "Remaining": remaining,
            "Percent_Used": pct_used,
            "Status": status,
        })

    return pd.DataFrame(rows)

def build_month_payslip(emp_id, month, employees_df, performance_df, weights, bonus_policy_df,
                         salary_df, spot_bonus_df, team_bonus_df, team_members_df,
                         profit_sharing_df, referral_df):
    """Pay breakdown for one employee for a single month - what actually goes
    on a payslip, as opposed to the lifetime/date-range totals used by the
    Salary & Bonus Breakdown section. Returns None if there's no performance
    record for that employee in that month."""
    emp_row = employees_df[employees_df["employee_id"] == emp_id]
    if emp_row.empty:
        return None
    employee = emp_row.iloc[0]

    month_perf = performance_df[
        (performance_df["employee_id"] == emp_id) & (performance_df["month"] == month)
    ]
    if month_perf.empty:
        return None

    scored = build_monthly_scores(month_perf, weights)
    scored = add_bonus_column(scored, bonus_policy_df)
    perf_row = scored.iloc[0]

    salary_row = salary_df[salary_df["employee_id"] == emp_id]
    base = float(salary_row["monthly_base_salary"].iloc[0]) if not salary_row.empty else 0.0
    hra = float(salary_row["hra"].iloc[0]) if not salary_row.empty else 0.0
    allowance = float(salary_row["allowance"].iloc[0]) if not salary_row.empty else 0.0
    performance_bonus = base * perf_row["Bonus_Percent"] / 100

    # Reuse the same aggregation functions as the date-range summary, just
    # scoped to this one month's performance row instead of a wider range.
    def _lookup(component_df, col):
        row = component_df[component_df["employee_id"] == emp_id]
        return float(row[col].iloc[0]) if not row.empty else 0.0

    spot_amt = _lookup(aggregate_spot_bonus(spot_bonus_df, month_perf), "Spot_Bonus")
    team_amt = _lookup(aggregate_team_bonus(team_bonus_df, team_members_df, month_perf), "Team_Bonus")
    profit_amt = _lookup(aggregate_profit_sharing(profit_sharing_df, employees_df, month_perf), "Profit_Share_Bonus")
    referral_amt = _lookup(aggregate_referral_bonus(referral_df, month_perf), "Referral_Bonus")

    total_bonus = performance_bonus + spot_amt + team_amt + profit_amt + referral_amt

    return {
        "employee_id": emp_id,
        "name": employee["name"],
        "department": employee["department"],
        "email": employee["email"],
        "month": month,
        "overall_score": float(perf_row["Overall_Score"]),
        "bonus_percent": float(perf_row["Bonus_Percent"]),
        "base_salary": base,
        "hra": hra,
        "allowance": allowance,
        "performance_bonus": performance_bonus,
        "spot_bonus": spot_amt,
        "team_bonus": team_amt,
        "profit_share_bonus": profit_amt,
        "referral_bonus": referral_amt,
        "total_bonus": total_bonus,
        "gross_pay": base + hra + allowance + total_bonus,
    }

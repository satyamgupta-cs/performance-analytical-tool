import calendar
from datetime import date

import streamlit as st

from ui_design import apply_modern_ui, top_profile_bar
from db_utils import (
    get_employees_df, get_performance_df, get_weights, get_bonus_policy,
    get_salary_structure_df, get_spot_bonus_df, get_team_bonus_df,
    get_team_members_df, get_profit_sharing_df, get_referral_bonus_df,
    get_bonus_budgets_df, add_bonus_budget, delete_bonus_budget,
    log_audit_action,
)
from calculations import build_budget_utilization

st.set_page_config(page_title="Budgets", layout="wide")

if "role" not in st.session_state or st.session_state.role != "admin":
    st.error("Access denied. Admins only.")
    st.stop()

apply_modern_ui()
top_profile_bar()

st.title("Bonus Budgets")
st.caption(
    "Allocate a bonus pool per department, or company-wide, for a period. "
    "Spend is the total of every bonus type already recorded (Performance, "
    "Spot, Team, Profit-Sharing, Referral) for employees in that department "
    "during that period."
)

if "budget_msg" in st.session_state:
    st.success(st.session_state.pop("budget_msg"))

employees_df = get_employees_df()
performance_df = get_performance_df()
weights = get_weights()
bonus_policy_df = get_bonus_policy()
salary_df = get_salary_structure_df()
spot_bonus_df = get_spot_bonus_df()
team_bonus_df = get_team_bonus_df()
team_members_df = get_team_members_df()
profit_sharing_df = get_profit_sharing_df()
referral_df = get_referral_bonus_df()
budgets_df = get_bonus_budgets_df()

departments = sorted(employees_df["department"].unique().tolist()) if not employees_df.empty else []

# ---------------- Add a new budget ----------------
with st.expander("Allocate a new budget", expanded=budgets_df.empty):
    period_type = st.selectbox("Period type", ["Custom", "Monthly", "Quarterly", "Yearly"])

    today = date.today()
    if period_type == "Custom":
        c1, c2 = st.columns(2)
        period_start = c1.date_input("Start date", value=today.replace(day=1))
        period_end = c2.date_input("End date", value=today)
    elif period_type == "Monthly":
        c1, c2 = st.columns(2)
        year = c1.number_input("Year", min_value=2000, max_value=2100, value=today.year, step=1)
        month = c2.selectbox("Month", list(range(1, 13)), index=today.month - 1,
                              format_func=lambda m: calendar.month_name[m])
        period_start = date(year, month, 1)
        period_end = date(year, month, calendar.monthrange(year, month)[1])
    elif period_type == "Quarterly":
        c1, c2 = st.columns(2)
        year = c1.number_input("Year", min_value=2000, max_value=2100, value=today.year, step=1)
        quarter = c2.selectbox("Quarter", ["Q1", "Q2", "Q3", "Q4"], index=(today.month - 1) // 3)
        q_num = int(quarter[1])
        start_month = (q_num - 1) * 3 + 1
        end_month = start_month + 2
        period_start = date(year, start_month, 1)
        period_end = date(year, end_month, calendar.monthrange(year, end_month)[1])
    else:  # Yearly
        year = st.number_input("Year", min_value=2000, max_value=2100, value=today.year, step=1)
        period_start = date(year, 1, 1)
        period_end = date(year, 12, 31)

    st.caption(f"Period: {period_start} to {period_end}")

    c1, c2 = st.columns(2)
    scope = c1.selectbox("Scope", ["Company-wide (ALL)"] + departments)
    department = "ALL" if scope == "Company-wide (ALL)" else scope
    allocated_amount = c2.number_input("Allocated amount (₹)", min_value=0.0, value=100000.0, step=5000.0)
    notes = st.text_input("Notes (optional)")

    if st.button("Create budget"):
        try:
            add_bonus_budget(department, period_type.lower(), period_start, period_end, allocated_amount, notes)
        except ValueError as e:
            st.error(str(e))
        else:
            current_user = st.session_state.get("username", "Admin")
            log_audit_action(
                username=current_user,
                action=f"Allocated bonus budget for {department}",
                old_val="—",
                new_val=f"₹{allocated_amount:,.0f} for {period_start} to {period_end}",
            )
            st.session_state["budget_msg"] = f"Budget created for {department}."
            st.rerun()

st.divider()

if budgets_df.empty:
    st.info("No budgets allocated yet.")
    st.stop()

utilization = build_budget_utilization(
    budgets_df, employees_df, performance_df, weights, bonus_policy_df,
    salary_df, spot_bonus_df, team_bonus_df, team_members_df, profit_sharing_df, referral_df,
)

def render_budget_row(row):
    label = "Company-wide pool" if row["department"] == "ALL" else row["department"]
    st.markdown(f"**{label}** — {row['period_start']} to {row['period_end']} · Status: {row['Status']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Allocated", f"₹{row['allocated_amount']:,.0f}")
    c2.metric("Spent", f"₹{row['Spent']:,.0f}")
    c3.metric("Remaining", f"₹{row['Remaining']:,.0f}")
    c4.metric("Used", f"{row['Percent_Used']:.0f}%")
    st.progress(min(row["Percent_Used"] / 100, 1.0))
    if row["Status"] == "Over Budget":
        st.error(f"Over budget by ₹{-row['Remaining']:,.0f}.")
    elif row["Status"] == "Near Limit":
        st.warning("Approaching the allocated limit.")
    if row.get("notes"):
        st.caption(row["notes"])


# ---------------- Company-wide pool ----------------
company_rows = utilization[utilization["department"] == "ALL"]
if not company_rows.empty:
    st.subheader("Company-wide pool")
    for _, row in company_rows.sort_values("period_start", ascending=False).iterrows():
        render_budget_row(row)
        st.divider()

# ---------------- Per-department budgets ----------------
dept_rows = utilization[utilization["department"] != "ALL"]
if not dept_rows.empty:
    st.subheader("Per-department budgets")
    for _, row in dept_rows.sort_values(["period_start", "department"], ascending=[False, True]).iterrows():
        render_budget_row(row)
        st.divider()

# ---------------- Delete a budget ----------------
with st.expander("Remove a budget"):
    options = {
        f"{row['budget_id']} — {row['department']} ({row['period_start']} to {row['period_end']})": row["budget_id"]
        for _, row in budgets_df.iterrows()
    }
    if options:
        choice = st.selectbox("Budget to remove", list(options.keys()))
        if st.button("Delete budget", type="secondary"):
            budget_id = options[choice]
            delete_bonus_budget(budget_id)
            current_user = st.session_state.get("username", "Admin")
            log_audit_action(
                username=current_user,
                action="Deleted bonus budget",
                old_val=choice,
                new_val="—",
            )
            st.session_state["budget_msg"] = "Budget removed."
            st.rerun()
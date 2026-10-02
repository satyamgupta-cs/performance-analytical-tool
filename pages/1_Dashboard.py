import plotly.express as px
import streamlit as st
import pandas as pd
from db_utils import run_query

from anomaly_detection import (
    DEFAULT_ALPHA,
    DEFAULT_MIN_CHANGE,
    DEFAULT_MIN_MONTHS,
    detect_flagged_employees,
)
from calculations import (
    build_employee_summary,
    build_full_salary_summary,
    build_monthly_scores,
    date_range_filter,
    build_department_analytics,
    format_lakhs,
)
from db_utils import (
    get_all_performance_with_standing,
    get_bonus_policy,
    get_employees_df,
    get_performance_df,
    get_profit_sharing_df,
    get_referral_bonus_df,
    get_salary_structure_df,
    get_spot_bonus_df,
    get_team_bonus_df,
    get_team_members_df,
    get_weights,
)
from ui_design import apply_modern_ui, top_profile_bar

st.set_page_config(page_title="Dashboard", layout="wide")

if "role" not in st.session_state or st.session_state.role != "admin":
    st.error("Access denied. Admins only.")
    st.stop()

apply_modern_ui()
top_profile_bar()

st.title("Performance & Standings Dashboard")

# Load Data
employees_df = get_employees_df()
full_performance_df = get_performance_df()
weights = get_weights()
bonus_policy_df = get_bonus_policy()
salary_df = get_salary_structure_df()
spot_bonus_df = get_spot_bonus_df()
team_bonus_df = get_team_bonus_df()
team_members_df = get_team_members_df()
profit_sharing_df = get_profit_sharing_df()
referral_df = get_referral_bonus_df()

# Standings Overview Table
df = get_all_performance_with_standing()
if not df.empty:
    st.subheader("Employee Performance Overview")
    st.dataframe(
        df,
        column_order=["Employee Name", "Department", "Total Score", "Dept_Standing"],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No performance records found in the database.")

performance_df = date_range_filter(full_performance_df, key_prefix="dash")

if employees_df.empty or full_performance_df.empty:
    st.info("No employee data yet. Add employees and records on the **Dataset** page.")
    st.stop()

if performance_df.empty:
    st.warning("No performance records found for the selected date range. Try widening your date filter.")
    st.stop()

summary = build_employee_summary(employees_df, performance_df, weights, bonus_policy_df)
full_summary = build_full_salary_summary(
    summary, performance_df, salary_df, spot_bonus_df, team_bonus_df,
    team_members_df, profit_sharing_df, employees_df, referral_df,
)

# ---------------- KPI cards ----------------
col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
col1.metric("Total Employees", len(summary))
col2.metric("Avg Task Completion", f"{summary['Task_Completion_Rate'].mean():.1f}%")
col3.metric("Avg On-Time Delivery", f"{summary['On_Time_Delivery_Rate'].mean():.1f}%")
col4.metric("Avg Attendance", f"{summary['Attendance_Rate'].mean():.1f}%")
col5.metric("Avg Bonus", f"{summary['Bonus_Percent'].mean():.1f}%")
top_row = summary.loc[summary["Overall_Score"].idxmax()]
low_row = summary.loc[summary["Overall_Score"].idxmin()]
col6.metric("Highest Performer", top_row["name"], f"{top_row['Overall_Score']:.1f}")
col7.metric("Lowest Performer", low_row["name"], f"{low_row['Overall_Score']:.1f}")

st.divider()

# ---------------- Salary & Bonus KPIs ----------------
st.subheader("Salary & Bonus (selected date range)")
p1, p2, p3, p4 = st.columns(4)
p1.metric("Avg Monthly Fixed Salary", f"₹{full_summary['Monthly_Fixed_Salary'].mean():,.0f}")
p2.metric("Avg Total Bonus", f"₹{full_summary['Total_Bonus'].mean():,.0f}")
p3.metric("Avg In Hand Salary", f"₹{full_summary['In_Hand_Salary'].mean():,.0f}")
p4.metric("Total Bonus Paid Out", f"₹{full_summary['Total_Bonus'].sum():,.0f}")

with st.expander("Bonus mix by type (company-wide total for this range)"):
    bonus_mix = full_summary[[
        "Performance_Bonus", "Spot_Bonus", "Team_Bonus", "Profit_Share_Bonus", "Referral_Bonus",
    ]].sum().reset_index()
    bonus_mix.columns = ["Bonus Type", "Total Amount"]
    fig_mix = px.pie(bonus_mix, names="Bonus Type", values="Total Amount",
                     title="Total Bonus Paid by Type", hole=0.4)
    st.plotly_chart(fig_mix, use_container_width=True)

st.divider()

# ---------------- Charts ----------------
# ---------------- Charts ----------------
top10 = summary.sort_values("Overall_Score", ascending=False).head(10)
fig1 = px.bar(top10, x="name", y="Overall_Score", title="Top 10 Employees (Overall Score)")
st.plotly_chart(fig1, width="stretch")

st.divider()

# ---------------- Department Analytics ----------------
st.subheader("Department Analytics")
st.caption("Per-department rollup for the date range selected above.")

dept_analytics = build_department_analytics(summary, full_summary)

if dept_analytics.empty:
    st.info("No department data for the selected range.")
else:
    best_dept = dept_analytics.iloc[0]
    worst_dept = dept_analytics.iloc[-1]

    b1, b2 = st.columns(2)
    b1.success(f"Highest performing: **{best_dept['department']}** — {best_dept['Avg_Score']:.1f} avg score")
    if worst_dept["department"] != best_dept["department"]:
        b2.warning(f"Needs intervention: **{worst_dept['department']}** — {worst_dept['Avg_Score']:.1f} avg score")

    for _, row in dept_analytics.iterrows():
        with st.container(border=True):
            st.markdown(f"**{row['department']}**")
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Employees", int(row["Employees"]))
            m2.metric("Avg Score", f"{row['Avg_Score']:.1f}")
            m3.metric("Attendance", f"{row['Attendance']:.0f}%")
            m4.metric("Task Completion", f"{row['Task_Completion']:.0f}%")
            m5.metric("Bonus Cost", format_lakhs(row["Bonus_Cost"]))

    st.markdown("##### Department comparison")
    comparison_df = dept_analytics.copy()
    comparison_df["Avg Score"] = comparison_df["Avg_Score"].round(1)
    comparison_df["Bonus Cost"] = comparison_df["Bonus_Cost"].apply(format_lakhs)
    st.dataframe(
        comparison_df[["department", "Avg Score", "Bonus Cost"]].rename(columns={"department": "Department"}),
        use_container_width=True, hide_index=True,
    )

# ============================================================
# Flagged Employees — sudden change in performance (ANOVA)
# ============================================================
st.subheader("Flagged Employees — Sudden Performance Change (ANOVA)")
st.caption(
    "For every employee with enough monthly history, their Overall Score history is split "
    "into an earlier baseline period and a later recent period. A one-way ANOVA "
    "(scipy.stats.f_oneway) tests whether the two periods differ significantly. An employee "
    "is flagged when the difference is both statistically significant *and* large enough in "
    "points to matter — catching sudden jumps or drops, not normal month-to-month noise."
)

with st.expander("Detection settings", expanded=False):
    s1, s2, s3 = st.columns(3)
    alpha = s1.slider("Significance level (alpha)", 0.01, 0.20, DEFAULT_ALPHA, step=0.01,
                      help="Lower = stricter. A p-value below this is considered statistically significant.")
    min_change = s2.slider("Minimum score swing to flag (points)", 1.0, 30.0, DEFAULT_MIN_CHANGE, step=1.0,
                           help="Ignore statistically-significant but tiny changes below this many points.")
    min_months = s3.slider("Minimum months of history required", 3, 12, DEFAULT_MIN_MONTHS, step=1,
                           help="Employees with fewer months than this can't be tested yet.")

flagged_all = detect_flagged_employees(
    employees_df, full_performance_df, weights,
    alpha=alpha, min_change=min_change, min_months=min_months,
)
flagged_only = flagged_all[flagged_all["flagged"]].reset_index(drop=True)

if flagged_only.empty:
    st.success("No employees currently show a statistically significant sudden change in performance.")
else:
    st.warning(f"{len(flagged_only)} employee(s) flagged for a sudden change in performance.")

    display_df = flagged_only.copy()
    display_df["Direction"] = display_df["direction"]
    display_df["Change (pts)"] = display_df["change"].round(1)
    display_df["Baseline Score"] = display_df["baseline_score"].round(1)
    display_df["Recent Score"] = display_df["recent_score"].round(1)
    display_df["ANOVA p-value"] = display_df["p_value"].round(4)
    display_df["Months of Data"] = display_df["months_count"]

    st.dataframe(
        display_df[[
            "name", "department", "Direction", "Baseline Score", "Recent Score",
            "Change (pts)", "ANOVA p-value", "Months of Data",
        ]].rename(columns={"name": "Employee", "department": "Department"}),
        width="stretch", hide_index=True,
    )

    st.markdown("##### Check an individual flagged employee")

    label_by_id = {
        row["employee_id"]: (
            f"{row['name']} ({row['department']}) — "
            f"{row['direction']} {abs(row['change']):.1f} pts (p={row['p_value']:.4f})"
        )
        for _, row in flagged_only.iterrows()
    }

    selected_id = st.selectbox(
        "Search flagged employee by name",
        options=list(label_by_id.keys()),
        format_func=lambda eid: label_by_id[eid],
        index=None,
        placeholder="Start typing a name...",
        key="flagged_employee_search",
    )

    if selected_id is not None:
        row = flagged_only[flagged_only["employee_id"] == selected_id].iloc[0]
        emp_history = full_performance_df[full_performance_df["employee_id"] == selected_id]
        monthly = build_monthly_scores(emp_history, weights).sort_values("month")

        d1, d2, d3 = st.columns(3)
        d1.metric("Baseline Score", f"{row['baseline_score']:.1f}")
        d2.metric("Recent Score", f"{row['recent_score']:.1f}", f"{row['change']:.1f}")
        d3.metric("ANOVA p-value", f"{row['p_value']:.4f}")

        fig = px.line(monthly, x="month", y="Overall_Score", markers=True,
                      title=f"{row['name']} — Monthly Overall Score")
        st.plotly_chart(fig,use_container_width=True, key=f"flag_chart_{selected_id}")

        st.caption(row["reason"])

        if st.button(f"Open full profile for {row['name']} →", key=f"open_emp_{selected_id}"):
            st.session_state["employee_search"] = str(selected_id)
            try:
                st.switch_page("pages/3_Employee.py")
            except Exception:
                st.info("Go to the **Employee** page from the sidebar and search for "
                        f"ID {selected_id} ({row['name']}).")

def render_risk_classification_section(df_employees: pd.DataFrame):
    if df_employees is None or df_employees.empty:
        st.info("No performance data found for the current month.")
        return

    df_classified = df_employees.copy()

    # Classification logic based on calculated score
    def classify_simple(score):
        try:
            val = float(score)
        except (ValueError, TypeError):
            val = 0.0

        if val >= 85:
            return "High Performer", "🟢"
        elif val >= 70:
            return "Watch", "🟡"
        else:
            return "At Risk", "🔴"

    df_classified["tier_info"] = df_classified["score"].apply(classify_simple)
    df_classified["tier"] = df_classified["tier_info"].apply(lambda x: x[0])

    # Count metrics per category
    tier_counts = df_classified["tier"].value_counts().to_dict()
    high_perf = tier_counts.get("High Performer", 0)
    watch = tier_counts.get("Watch", 0)
    at_risk = tier_counts.get("At Risk", 0)

    st.subheader("Employee Risk Classification Dashboard")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="🟢 High Performers (Score ≥ 85)", value=high_perf)
    with col2:
        st.metric(label="🟡 Watch / Monitor (Score 70–84)", value=watch)
    with col3:
        st.metric(label="🔴 At Risk (Score < 70)", value=at_risk)

    st.divider()

    # Category Filter
    selected_tier = st.selectbox(
        "Filter Category View",
        options=["All Categories", "🟢 High Performer", "🟡 Watch", "🔴 At Risk"]
    )

    filtered_df = df_classified.copy()
    if selected_tier != "All Categories":
        clean_tier = selected_tier.split(" ", 1)[1] if " " in selected_tier else selected_tier
        filtered_df = filtered_df[filtered_df["tier"] == clean_tier]

    # Display Table
    st.dataframe(
        filtered_df[[
            "employee_id", "name", "department", "score", "tier", 
            "completed_tasks", "assigned_tasks", "customer_rating"
        ]],
        column_config={
            "score": st.column_config.ProgressColumn(
                "Calculated Score",
                format="%d",
                min_value=0,
                max_value=100,
            ),
            "tier": st.column_config.TextColumn("Health Category"),
            "completed_tasks": st.column_config.NumberColumn("Completed Tasks"),
            "assigned_tasks": st.column_config.NumberColumn("Assigned Tasks"),
            "customer_rating": st.column_config.NumberColumn("Customer Rating (1-5)"),
        },
        hide_index=True,
        width="stretch"
    )

# Fetch latest month performance and compute score dynamically
query = """
SELECT 
    e.employee_id,
    e.name,
    e.department,
    p.month,
    p.assigned_tasks,
    p.completed_tasks,
    p.completed_before_deadline,
    p.working_days,
    p.present_days,
    p.customer_rating,
    ROUND(
        (COALESCE(p.completed_tasks::float / NULLIF(p.assigned_tasks, 0), 0) * 40) +
        (COALESCE(p.present_days::float / NULLIF(p.working_days, 0), 0) * 30) +
        (COALESCE(p.completed_before_deadline::float / NULLIF(p.completed_tasks, 0), 0) * 20) +
        (COALESCE(p.customer_rating::float / 5.0, 0) * 10)
    ) AS score
FROM employees e
JOIN performance p ON e.employee_id = p.employee_id
WHERE p.month = (SELECT MAX(month) FROM performance)
"""
# Run query and render dashboard
df_employees = run_query(query, fetch=True)
render_risk_classification_section(df_employees)
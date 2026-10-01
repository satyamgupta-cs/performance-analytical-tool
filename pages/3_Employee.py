import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from forecasting_utils import analyze_trend_and_forecast

from ui_design import apply_modern_ui, top_profile_bar
from db_utils import (
    get_employees_df, get_performance_df, get_weights, get_bonus_policy,
    get_salary_structure_df, get_spot_bonus_df, get_team_bonus_df,
    get_team_members_df, get_profit_sharing_df, get_referral_bonus_df,
    get_all_performance_with_standing, get_employee_raw_performance
)
from calculations import (
    build_employee_summary, build_monthly_scores, build_full_salary_summary, build_month_payslip,
)
from recommendation_utils import analyze_performance
from anomaly_detection import evaluate_employee
from payslip_utils import generate_payslip_pdf

st.set_page_config(page_title="Employee Profile", layout="wide")

if "role" not in st.session_state or st.session_state.role != "admin":
    st.error("Access denied. Admins only.")
    st.stop()
apply_modern_ui()
top_profile_bar()

# Load Data
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

summary = build_employee_summary(employees_df, performance_df, weights, bonus_policy_df)
full_summary = build_full_salary_summary(
    summary, performance_df, salary_df, spot_bonus_df, team_bonus_df,
    team_members_df, profit_sharing_df, employees_df, referral_df,
)

# Role-Based Search Setup
st.title("Employee Search & Profiles")
search = st.text_input("Search by Employee ID, Name, Email or Phone", key="employee_search")

if search:
    mask = (
        full_summary["employee_id"].astype(str).str.contains(search, case=False)
        | full_summary["name"].str.contains(search, case=False, na=False)
        | full_summary["email"].str.contains(search, case=False, na=False)
        | full_summary["phone"].astype(str).str.contains(search, case=False, na=False)
    )
    results = full_summary[mask]

    if results.empty:
        st.warning("No employee found matching your search.")
    else:
        emp = results.iloc[0]
        emp_id = int(emp["employee_id"])

        # Fetch Department Standings
        df_rankings = get_all_performance_with_standing()
        standing_val = "Standard"
        if df_rankings is not None and not df_rankings.empty:
            match = df_rankings[df_rankings["employee_id"] == emp_id]
            if not match.empty:
                standing_val = match.iloc[0]["Dept_Standing"]

        # Run ANOVA sudden-change test
        emp_history = performance_df[performance_df["employee_id"] == emp_id]
        monthly = build_monthly_scores(emp_history, weights).sort_values("month")
        if not monthly.empty:
            flag = evaluate_employee(monthly["Overall_Score"].tolist(), employee_id=emp_id)
        else:
            flag = type("Flag", (), {"flagged": False})()

        header = f"{emp['name']} — {emp['department']}"
        if flag.flagged:
            st.subheader(header)
            (st.success if flag.direction == "Improved" else st.error)(
                f"Sudden performance change detected: {flag.direction} by "
                f"{abs(flag.change):.1f} points (ANOVA p={flag.p_value:.4f})."
            )
        else:
            st.subheader(header)

        # High-Level Score Card
        with st.container(border=True):
            m1, m2, m3 = st.columns(3)
            m1.metric("Overall Score", f"{emp['Overall_Score']:.1f} / 100")
            m2.metric("Department Standing", standing_val)
            m3.metric("Performance Bonus", f"{emp['Bonus_Percent']:.0f}% of basic")

        # Work Progress
        months_tracked = emp_history.shape[0]
        pace = emp["completed_tasks"] / months_tracked if months_tracked else 0
        months_left = max(0.0, round((emp["assigned_tasks"] - emp["completed_tasks"]) / pace, 1)) if pace else 0
        
        progress_val = max(0.0, min(float(emp["completed_tasks"]) / max(float(emp["assigned_tasks"]), 1.0), 1.0))
        st.write("**Task Completion Progress**")
        st.progress(progress_val)
        st.caption(f"{emp['completed_tasks']:.0f} / {emp['assigned_tasks']:.0f} tasks completed | Est. time remaining: {months_left} month(s)")

        # KPI Overview Metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Task Completion", f"{emp['Task_Completion_Rate']:.1f}%")
        c2.metric("On-Time Delivery", f"{emp['On_Time_Delivery_Rate']:.1f}%")
        c3.metric("Customer Satisfaction", f"{emp['Customer_Satisfaction']:.1f}%")
        c4.metric("Attendance", f"{emp['Attendance_Rate']:.1f}%")

        st.divider()

        # Explainable Performance & Targeted Recommendations
        st.subheader("Explainable Performance Analysis")
        raw_data = get_employee_raw_performance(emp_id)

        if raw_data:
            analysis = analyze_performance(
                completed_tasks=raw_data["completed_tasks"],
                assigned_tasks=raw_data["assigned_tasks"],
                completed_before_deadline=raw_data["completed_before_deadline"],
                present_days=raw_data["present_days"],
                working_days=raw_data["working_days"],
                customer_rating=raw_data["customer_rating"]
            )

            with st.container(border=True):
                st.markdown(f"#### KPI Status Breakdown {analysis['summary_text']}")
                table_data = [
                    {"KPI": kpi, "Score": details["value"], "Status": details["status"]}
                    for kpi, details in analysis["kpis"].items()
                ]
                st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

                st.markdown("#### Targeted Action Plan")
                st.markdown(f"**Primary Focus Area:** `{analysis['primary_focus']}`")
                st.markdown("**Suggested Actions:**")
                for action in analysis["actions"]:
                    st.markdown(f"- {action}")
        else:
            st.info("Detailed KPI raw records unavailable for granular recommendation breakdown.")

        st.divider()

        # Salary & Bonus Breakdown
        st.subheader("Salary & Bonus Breakdown")
        s1, s2, s3 = st.columns(3)
        s1.metric("Monthly Base Salary", f"₹{emp['monthly_base_salary']:,.0f}")
        s2.metric("HRA", f"₹{emp['hra']:,.0f}")
        s3.metric("Allowance", f"₹{emp['allowance']:,.0f}")

        st.markdown("**Bonus Components**")
        b1, b2, b3, b4, b5 = st.columns(5)
        b1.metric("Performance Bonus", f"₹{emp['Performance_Bonus']:,.0f}")
        b2.metric("Spot Bonus", f"₹{emp['Spot_Bonus']:,.0f}")
        b3.metric("Team Bonus", f"₹{emp['Team_Bonus']:,.0f}")
        b4.metric("Profit Share", f"₹{emp['Profit_Share_Bonus']:,.0f}")
        b5.metric("Referral Bonus", f"₹{emp['Referral_Bonus']:,.0f}")

        f1, f2, f3 = st.columns(3)
        f1.metric("Monthly Fixed Salary", f"₹{emp['Monthly_Fixed_Salary']:,.0f}")
        f2.metric("Total Bonus", f"₹{emp['Total_Bonus']:,.0f}")
        f3.metric("In-Hand Salary", f"₹{emp['In_Hand_Salary']:,.0f}")
        st.markdown("**Payslip**")
        available_months = sorted(emp_history["month"].unique(), reverse=True)
        if available_months:
            payslip_month = st.selectbox("Month", available_months, key=f"payslip_month_{emp_id}")
            payslip_data = build_month_payslip(
                emp_id, payslip_month, employees_df, performance_df, weights, bonus_policy_df,
                salary_df, spot_bonus_df, team_bonus_df, team_members_df, profit_sharing_df, referral_df,
            )
            if payslip_data:
                st.download_button(
                    "Download Payslip (PDF)",
                    data=generate_payslip_pdf(payslip_data),
                    file_name=f"payslip_{emp_id}_{payslip_month}.pdf",
                    mime="application/pdf",
                )
            else:
                st.info("No payslip data available for that month.")
        else:
            st.info("No performance records yet, so no payslip can be generated.")

        st.divider()

        # Performance Trend & Next Month Forecast
        st.subheader("Performance Trend & Next Month Forecast")

        trend_data = analyze_trend_and_forecast(monthly, score_col="Overall_Score")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Performance Trend", trend_data["trend"])
        m2.metric("Current Score", f"{trend_data['current_score']:.1f}")

        growth_val = trend_data["growth_3m"]
        growth_str = f"{'+' if growth_val >= 0 else ''}{growth_val:.1f} pts"
        m3.metric("3-Month Growth", growth_str, delta=growth_val)

        m4.metric("Predicted Next Month", f"{trend_data['predicted_next']:.1f}")

        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=monthly["month"],
                y=monthly["Overall_Score"],
                mode="lines+markers",
                name="Actual Score",
                line=dict(color="#1f77b4", width=3),
                marker=dict(size=8),
            )
        )

        if len(monthly) >= 2:
            last_month = str(monthly["month"].iloc[-1])
            fig.add_trace(
                go.Scatter(
                    x=[last_month, "Next Month (Pred.)"],
                    y=[trend_data["current_score"], trend_data["predicted_next"]],
                    mode="lines+markers",
                    name="Linear Forecast",
                    line=dict(color="#ff7f0e", width=2, dash="dash"),
                    marker=dict(size=10, symbol="star"),
                )
            )

        fig.update_layout(
            title="Historical Performance & Next-Month Projection",
            xaxis_title="Month",
            yaxis_title="Overall Score (0-100)",
            yaxis=dict(range=[0, 105]),
            hovermode="x unified",
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
            ),
        )

        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Detailed Monthly Historical Scores"):
            st.dataframe(
                monthly[
                    [
                        "month",
                        "Task_Completion_Rate",
                        "On_Time_Delivery_Rate",
                        "Customer_Satisfaction",
                        "Attendance_Rate",
                        "Overall_Score",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

else:
    st.info("Enter an Employee ID, name, email, or phone number to search.")
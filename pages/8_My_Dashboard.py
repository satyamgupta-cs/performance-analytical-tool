import pandas as pd
import streamlit as st

from ui_design import apply_modern_ui, top_profile_bar
from db_utils import (
    get_employees_df, get_performance_df, get_weights, get_bonus_policy,
    get_salary_structure_df, get_spot_bonus_df, get_team_bonus_df,
    get_team_members_df, get_profit_sharing_df, get_referral_bonus_df,
)
from calculations import build_employee_summary, build_full_salary_summary, build_month_payslip
from payslip_utils import generate_payslip_pdf

st.set_page_config(page_title="My Dashboard", layout="wide")

if "role" not in st.session_state or st.session_state.role != "employee":
    st.error("Access denied.")
    st.stop()

apply_modern_ui()
top_profile_bar()

st.title("My Dashboard")

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

emp_id = st.session_state.get("employee_id")
summary = build_employee_summary(employees_df, performance_df, weights, bonus_policy_df)
full_summary = build_full_salary_summary(
    summary, performance_df, salary_df, spot_bonus_df, team_bonus_df,
    team_members_df, profit_sharing_df, employees_df, referral_df,
)

emp_row = full_summary[full_summary["employee_id"] == emp_id]
if emp_row.empty:
    st.info("No performance data recorded for your account yet. Check back after your first month is entered.")
    st.stop()

emp = emp_row.iloc[0]

# Rank within department, by Overall Score, among everyone with data
dept_peers = summary[summary["department"] == emp["department"]].sort_values(
    "Overall_Score", ascending=False
).reset_index(drop=True)
dept_rank = int(dept_peers[dept_peers["employee_id"] == emp_id].index[0]) + 1
dept_size = len(dept_peers)

# ---------------- My Performance ----------------
st.subheader("My Performance")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Overall Score", f"{emp['Overall_Score']:.1f}")
c2.metric("Department Rank", f"{dept_rank} / {dept_size}")
c3.metric("Attendance", f"{emp['Attendance_Rate']:.0f}%")
c4.metric("Task Completion", f"{emp['Task_Completion_Rate']:.0f}%")
c5.metric("Customer Rating", f"{emp['customer_rating']:.1f}/5")

st.divider()

# ---------------- My Goals ----------------
st.subheader("My Goals")
st.caption("How you're tracking against a full (100%) task completion goal and a top (5/5) customer rating goal.")
goals_df = pd.DataFrame([
    {"Goal": "Task Target", "Achievement": f"{emp['Task_Completion_Rate']:.0f}%"},
    {"Goal": "Customer Rating", "Achievement": f"{emp['Customer_Satisfaction']:.0f}%"},
])
st.dataframe(goals_df, hide_index=True, use_container_width=True)

st.divider()

# ---------------- My Bonuses ----------------
st.subheader("My Bonuses")
bonuses_df = pd.DataFrame([
    {"Bonus": "Performance Bonus", "Amount": emp["Performance_Bonus"]},
    {"Bonus": "Spot Bonus", "Amount": emp["Spot_Bonus"]},
    {"Bonus": "Team Bonus", "Amount": emp["Team_Bonus"]},
    {"Bonus": "Profit-Sharing Bonus", "Amount": emp["Profit_Share_Bonus"]},
    {"Bonus": "Referral Bonus", "Amount": emp["Referral_Bonus"]},
])
bonuses_df["Amount"] = bonuses_df["Amount"].apply(lambda x: f"₹{x:,.0f}")
st.dataframe(bonuses_df, hide_index=True, use_container_width=True)
st.metric("Total", f"₹{emp['Total_Bonus']:,.0f}")

st.divider()

# ---------------- Payslip ----------------
st.subheader("Payslip")
emp_history = performance_df[performance_df["employee_id"] == emp_id]
available_months = sorted(emp_history["month"].unique(), reverse=True)
if available_months:
    payslip_month = st.selectbox("Month", available_months)
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
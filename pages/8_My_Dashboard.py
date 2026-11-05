import pandas as pd
import streamlit as st

from ui_design import apply_modern_ui, top_profile_bar
from db_utils import (
    get_employee_by_id, get_performance_by_employee_id,
    get_salary_structure_by_employee_id, get_spot_bonus_by_employee_id,
    get_team_bonus_by_employee_id, get_team_members_by_employee_id,
    get_profit_sharing_df, get_referral_bonus_by_employee_id,
    get_active_employee_count, get_department_rank_and_size,
    get_weights, get_bonus_policy,
    change_user_password,
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

emp_id = st.session_state.get("employee_id")

# Fetch only this employee's own records at the SQL level (Finding H-8).
# No other employee's salary, KPI data, or ratings are loaded into memory.
employees_df = get_employee_by_id(emp_id)
performance_df = get_performance_by_employee_id(emp_id)

if employees_df.empty:
    st.info("No employee record found for your account. Contact your administrator.")
    st.stop()

weights = get_weights()
bonus_policy_df = get_bonus_policy()
salary_df = get_salary_structure_by_employee_id(emp_id)
spot_bonus_df = get_spot_bonus_by_employee_id(emp_id)
team_bonus_df = get_team_bonus_by_employee_id(emp_id)
team_members_df = get_team_members_by_employee_id(emp_id)
profit_sharing_df = get_profit_sharing_df()
referral_df = get_referral_bonus_by_employee_id(emp_id)
active_headcount = get_active_employee_count()

summary = build_employee_summary(employees_df, performance_df, weights, bonus_policy_df)
full_summary = build_full_salary_summary(
    summary, performance_df, salary_df, spot_bonus_df, team_bonus_df,
    team_members_df, profit_sharing_df, employees_df, referral_df,
    total_headcount=active_headcount,
)

emp_row = full_summary[full_summary["employee_id"].astype(str) == str(emp_id)]
if performance_df.empty or emp_row.empty:
    st.info("No performance data recorded for your account yet. Check back after your first month is entered.")
    st.stop()

emp = emp_row.iloc[0]

# Department rank is computed server-side without loading peer records into the page
dept_rank, dept_size = get_department_rank_and_size(emp_id, weights)

# ---------------- My Performance ----------------
st.subheader("My Performance")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Overall Score", f"{emp['Overall_Score']:.1f}")
c2.metric("Department Rank", f"{dept_rank} / {dept_size}")
c3.metric("Attendance", f"{emp['Attendance_Rate']:.0f}%")
c4.metric("Task Completion", f"{emp['Task_Completion_Rate']:.0f}%")
rating_display = f"{emp['customer_rating']:.1f}/5" if pd.notna(emp.get("customer_rating")) else "—/5"
c5.metric("Customer Rating", rating_display)

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
# performance_df is already scoped to this employee only
available_months = sorted(performance_df["month"].unique(), reverse=True)
if available_months:
    payslip_month = st.selectbox("Month", available_months)
    payslip_data = build_month_payslip(
        emp_id, payslip_month, employees_df, performance_df, weights, bonus_policy_df,
        salary_df, spot_bonus_df, team_bonus_df, team_members_df, profit_sharing_df, referral_df,
        total_headcount=active_headcount,
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

# ============================================================
# Change Password
# ============================================================
st.divider()
st.subheader("Change Password")
st.caption("Use this form to change your password. You must enter your current password to confirm the change.")

with st.form("change_password_form", clear_on_submit=True):
    current_password = st.text_input("Current Password", type="password")
    new_password = st.text_input("New Password", type="password")
    confirm_password = st.text_input("Confirm New Password", type="password")
    submitted = st.form_submit_button("Update Password")

    if submitted:
        if not current_password or not new_password or not confirm_password:
            st.error("All fields are required.")
        elif new_password != confirm_password:
            st.error("New passwords do not match.")
        elif len(new_password) < 6:
            st.error("New password must be at least 6 characters long.")
        elif new_password == current_password:
            st.error("New password must be different from your current password.")
        else:
            username = st.session_state.get("username", "")
            if change_user_password(username, current_password, new_password):
                st.success("Password updated successfully.")
            else:
                st.error("Current password is incorrect. Please try again.")
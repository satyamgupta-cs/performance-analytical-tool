import streamlit as st
import pandas as pd
from ui_design import apply_modern_ui, top_profile_bar
import json
from db_utils import get_payslip_config, save_payslip_config
from db_utils import (
    get_weights, update_weights, get_bonus_policy, update_bonus_percent,
    current_db_info, save_db_config, init_schema,
    get_employees_df, get_salary_structure_df, upsert_salary_structure,
    get_company_settings, update_company_settings, log_audit_action
)
st.set_page_config(page_title="Settings", layout="wide")
if "role" not in st.session_state or st.session_state.role != "admin":
    st.error("Access denied. Admins only.")
    st.stop()

apply_modern_ui()
top_profile_bar()


st.title("Settings")

if "settings_success_msg" in st.session_state:
    st.success(st.session_state.pop("settings_success_msg"))

# ============================================================
# Database engine
# ============================================================
st.subheader("Database Connection")
st.caption(
    "StaffScore works with either MySQL or PostgreSQL — pick whichever one you or your "
    "friend already have running. This is saved to `database/db_config.json` and used the "
    "next time the app starts (an environment variable of the same name, e.g. DB_TYPE, "
    "always overrides this).\n\n"
    "⚠️ **Security note:** The database password is **not** saved to `db_config.json` "
    "(to avoid plaintext credentials on disk). Set `DB_PASSWORD` in your `.env` file or "
    "as an OS environment variable instead."
)

info = current_db_info()
st.info(f"Currently connected to **{info['type'].upper()}** at `{info['host']}:{info['port']}`, "
        f"database `{info['name']}`, user `{info['user']}`.")

with st.form("db_form"):
    d1, d2 = st.columns(2)
    db_type = d1.selectbox("Engine", ["mysql", "postgres"],
                            index=0 if info["type"] == "mysql" else 1)
    db_host = d2.text_input("Host", value=info["host"])
    d3, d4 = st.columns(2)
    default_port = "3306" if db_type == "mysql" else "5432"
    db_port = d3.text_input("Port", value=str(info["port"]) if str(info["port"]) else default_port)
    db_name = d4.text_input("Database name", value=info["name"])
    db_user = st.text_input("User", value=info["user"])
    st.info("🔒 Set `DB_PASSWORD` in your `.env` file or as an OS environment variable — "
            "it is not stored here to avoid plaintext credentials on disk.")

    saved = st.form_submit_button("Save & use this database")
    if saved:
        save_db_config(db_type, db_host, db_port, db_user, "", db_name)
        current_user = st.session_state.get("username", "Admin")
        log_audit_action(
            username=current_user,
            action="Updated Database Connection Configuration",
            old_val=f"{info['type']} ({info['host']}:{info['port']})",
            new_val=f"{db_type} ({db_host}:{db_port})"
        )
        st.success("Saved. Restart the Streamlit app for the new connection to take effect.")

st.caption(
    "First time connecting to a fresh database? Run the matching script in `database/` "
    "(`schema_mysql.sql` or `schema_postgres.sql`) once, or click below to have the app "
    "create the tables for you using the connection settings currently saved above."
)
if st.button("Create / verify tables on this database"):
    try:
        admin_password = init_schema()
        if admin_password:
            st.success(
                "Schema created. A default admin account was set up: "
                f"username `admin`, one-time password `{admin_password}` — "
                "save it now, it will not be shown again, and change it after your first login."
            )
        else:
            st.success("Schema created (or already existed) successfully.")
    except Exception as e:
        st.error(f"Could not initialize schema: {e}")

st.divider()

# ============================================================
# Performance Bonus Policy
# ============================================================
st.subheader("Performance Bonus Policy")
st.caption(
    "Bonus % awarded on top of an employee's **monthly base salary**, based on their Overall "
    "Score. This is only the performance component — Spot, Team, Profit-Sharing and Referral "
    "bonuses are managed on the **Bonuses & Teams** page."
)

bonus_df = get_bonus_policy()
with st.form("bonus_form"):
    new_values = {}
    for _, row in bonus_df.iterrows():
        label = f"Score {row['min_score']:.0f}-{row['max_score']:.0f}"
        new_values[row["policy_id"]] = st.number_input(
            label, 0.0, 100.0, float(row["bonus_percent"]), step=1.0,
            key=f"bonus_{row['policy_id']}",
            help=f"Bonus % of monthly base salary awarded when Overall Score falls between "
                 f"{row['min_score']:.0f} and {row['max_score']:.0f}.",
        )

    if st.form_submit_button("Save bonus policy"):
        changes = []
        for policy_id, percent in new_values.items():
            row_info = bonus_df[bonus_df["policy_id"] == policy_id].iloc[0]
            old_p = row_info["bonus_percent"]
            if old_p != percent:
                changes.append(f"Slab {row_info['min_score']:.0f}-{row_info['max_score']:.0f}: {old_p}% → {percent}%")
            update_bonus_percent(policy_id, percent)
        
        # Log Audit Action
        if changes:
            current_user = st.session_state.get("username", "Admin")
            log_audit_action(
                username=current_user,
                action="Updated Performance Bonus Policy Slabs",
                old_val="Previous Bonus Policy",
                new_val="; ".join(changes)
            )
        st.success("Bonus policy updated.")
        st.rerun()

st.divider()

# ============================================================
# Overall Score Weights
# ============================================================
st.subheader("Overall Score Weights")
st.caption("Enter any four values — they'll be auto-normalized to add up to 1.0 when saved. Changes reflect on the Dashboard, Dataset and Employee pages.")

weights = get_weights()
with st.form("weights_form"):
    c1, c2, c3, c4 = st.columns(4)
    task = c1.number_input("Task Completion weight", 0.0, 1.0, weights["task"], step=0.05,
                            help="Task Completion Rate = (Completed_Tasks / Assigned_Tasks) x 100")
    ontime = c2.number_input("On-Time Delivery weight", 0.0, 1.0, weights["ontime"], step=0.05,
                              help="On-Time Delivery Rate = (Completed_Before_Deadline / Completed_Tasks) x 100")
    satisfaction = c3.number_input("Customer Satisfaction weight", 0.0, 1.0, weights["satisfaction"], step=0.05,
                                    help="Customer Satisfaction = (Customer Rating / 5) x 100")
    attendance = c4.number_input("Attendance weight", 0.0, 1.0, weights["attendance"], step=0.05,
                                  help="Attendance Rate = (Present_Days / Working_Days) x 100")

    if st.form_submit_button("Save weights"):
        total = task + ontime + satisfaction + attendance
        if total <= 0:
            st.error("Weights can't all be zero.")
        else:
            old_w_str = f"Task: {weights['task']:.2f}, OnTime: {weights['ontime']:.2f}, Sat: {weights['satisfaction']:.2f}, Att: {weights['attendance']:.2f}"
            task, ontime, satisfaction, attendance = (w / total for w in (task, ontime, satisfaction, attendance))
            update_weights(task, ontime, satisfaction, attendance)
            
            # Log Audit Action
            current_user = st.session_state.get("username", "Admin")
            new_w_str = f"Task: {task:.2f}, OnTime: {ontime:.2f}, Sat: {satisfaction:.2f}, Att: {attendance:.2f}"
            log_audit_action(
                username=current_user,
                action="Updated Performance Score Weights",
                old_val=old_w_str,
                new_val=new_w_str
            )
            
            st.session_state["settings_success_msg"] = (
                f"Weights saved (auto-normalized to add up to 1.0): "
                f"Task {task:.3f}, On-Time {ontime:.3f}, Satisfaction {satisfaction:.3f}, Attendance {attendance:.3f}"
            )
            st.toast("✅ Weights saved successfully!")
            st.rerun()
st.divider()

# ============================================================
# Salary Structure per employee
# ============================================================
st.subheader("Salary Structure")
st.caption("Set each employee's monthly base salary, HRA and allowance. In Hand Salary = "
           "Monthly Base Salary + HRA + Allowance + Total Bonus.")

employees_df = get_employees_df()
salary_df = get_salary_structure_df()

if employees_df.empty:
    st.info("Add employees on the Dataset page first.")
else:
    merged = employees_df.merge(salary_df, on="employee_id", how="left")
    emp_choice = st.selectbox(
        "Employee", options=merged["employee_id"],
        format_func=lambda eid: merged.loc[merged["employee_id"] == eid, "name"].iloc[0],
    )
    row = merged[merged["employee_id"] == emp_choice].iloc[0]

    with st.form("salary_form"):
        c1, c2, c3 = st.columns(3)
        base = c1.number_input("Monthly Base Salary (₹)", min_value=0.0,
                                value=float(row["monthly_base_salary"]) if not pd.isna(row["monthly_base_salary"]) else 0.0, step=1000.0)
        hra = c2.number_input("HRA (₹)", min_value=0.0,
                               value=float(row["hra"]) if not pd.isna(row["hra"]) else 0.0, step=500.0)
        allowance = c3.number_input("Allowance (₹)", min_value=0.0,
                                     value=float(row["allowance"]) if not pd.isna(row["allowance"]) else 0.0, step=500.0)
        if st.form_submit_button("Save salary structure"):
            old_base = float(row["monthly_base_salary"]) if not pd.isna(row["monthly_base_salary"]) else 0.0
            old_hra_v = float(row["hra"]) if not pd.isna(row["hra"]) else 0.0
            old_allow_v = float(row["allowance"]) if not pd.isna(row["allowance"]) else 0.0

            upsert_salary_structure(emp_choice, base, hra, allowance)
            
            # Log Audit Action
            current_user = st.session_state.get("username", "Admin")
            log_audit_action(
                username=current_user,
                action=f"Updated Salary Structure for {row['name']} (ID: {emp_choice})",
                old_val=f"Base: ₹{old_base:,.0f}, HRA: ₹{old_hra_v:,.0f}, Allow: ₹{old_allow_v:,.0f}",
                new_val=f"Base: ₹{base:,.0f}, HRA: ₹{hra:,.0f}, Allow: ₹{allowance:,.0f}"
            )
            st.success(f"Salary structure saved for {row['name']}.")
            st.rerun()

st.divider()

# ============================================================
# Company-wide bonus defaults
# ============================================================
st.subheader("Company-wide Bonus Defaults")
st.caption("Default amounts used when recording new Referral or Profit-Sharing bonuses on the "
           "Bonuses & Teams page. You can still override these per-record.")

company_settings = get_company_settings()
with st.form("company_settings_form"):
    cc1, cc2 = st.columns(2)
    default_referral = cc1.number_input("Default Referral Bonus (₹)", min_value=0.0,
                                         value=company_settings["default_referral_bonus"], step=1000.0)
    default_pool_pct = cc2.number_input("Default Profit-Sharing Pool %", min_value=0.0, max_value=100.0,
                                         value=company_settings["default_profit_pool_percent"], step=0.5)
    if st.form_submit_button("Save company defaults"):
        old_ref = company_settings["default_referral_bonus"]
        old_pool = company_settings["default_profit_pool_percent"]
        
        update_company_settings(default_referral, default_pool_pct)
        
        # Log Audit Action
        current_user = st.session_state.get("username", "Admin")
        log_audit_action(
            username=current_user,
            action="Updated Company Bonus Defaults",
            old_val=f"Referral: ₹{old_ref:,.0f}, Pool: {old_pool}%",
            new_val=f"Referral: ₹{default_referral:,.0f}, Pool: {default_pool_pct}%"
        )
        
        st.success("Company-wide bonus defaults updated.")

st.title("⚙️ System Settings")

st.subheader("💳 Salary & Payslip Component Configuration")
st.caption("Enable or disable earnings and deduction fields per employment tier.")

# Available Master Fields
ALL_EARNINGS = [
    "Basic Salary", "HRA", "Dearness Allowance (DA)", "Travel Allowance",
    "Medical Allowance", "Special Allowance", "Conveyance Allowance",
    "Performance Bonus", "Incentive", "Overtime Pay", "Shift Allowance",
    "Night Shift Allowance", "Leave Encashment", "Arrears", "Commission", "Other Allowance"
]

ALL_DEDUCTIONS = [
    "PF", "Professional Tax", "TDS", "ESI", "Labour Welfare Fund",
    "Loan Recovery", "Advance Recovery", "Insurance Premium", "VPF", "NPS", "Other Deduction"
]

config = get_payslip_config()

# Select Employee Category to Configure
emp_type = st.radio("Select Employee Type to Configure:", ["Corporate", "Government", "Contract"], horizontal=True)

col_earn, col_ded = st.columns(2)

with col_earn:
    st.markdown("### 🟢 Active Earnings")
    selected_earnings = []
    current_earnings = config.get(emp_type, {}).get("earnings", [])
    
    for item in ALL_EARNINGS:
        checked = st.checkbox(item, value=(item in current_earnings), key=f"earn_{emp_type}_{item}")
        if checked:
            selected_earnings.append(item)

with col_ded:
    st.markdown("### 🔴 Active Deductions")
    selected_deductions = []
    current_deductions = config.get(emp_type, {}).get("deductions", [])
    
    for item in ALL_DEDUCTIONS:
        checked = st.checkbox(item, value=(item in current_deductions), key=f"ded_{emp_type}_{item}")
        if checked:
            selected_deductions.append(item)

if st.button("Save Salary Component Configuration", type="primary"):
    config[emp_type] = {
        "earnings": selected_earnings,
        "deductions": selected_deductions
    }
    save_payslip_config(config)
    st.success(f"Payslip setup for {emp_type} saved successfully!")
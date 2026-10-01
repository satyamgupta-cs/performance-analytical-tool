import streamlit as st

from ui_design import apply_modern_ui, top_profile_bar

import pandas as pd

from db_utils import (
    get_employees_df, get_performance_df, get_weights, get_bonus_policy,
    get_salary_structure_df, add_employee, add_column_to_performance,
    ALLOWED_COLUMN_TYPES,
    bulk_import_from_df, REQUIRED_UPLOAD_COLUMNS,log_audit_action
)
from calculations import build_employee_summary, add_salary_columns, date_range_filter

st.set_page_config(page_title="Dataset", layout="wide")

if "role" not in st.session_state or st.session_state.role != "admin":
    st.error("Access denied. Admins only.")
    st.stop()

apply_modern_ui()
top_profile_bar()

st.title("Dataset - Full Employee Ranking")
if "dataset_msg" in st.session_state:
    st.success(st.session_state.pop("dataset_msg"))

if "bulk_credentials" in st.session_state:
    creds = st.session_state.pop("bulk_credentials")
    creds_df = pd.DataFrame(creds, columns=["Name", "Email", "Temporary Password"])
    st.warning(
        f"{len(creds)} login(s) were created with one-time passwords. "
        "Download and distribute them now — they won't be shown again."
    )
    st.dataframe(creds_df, use_container_width=True, hide_index=True)
    st.download_button(
        "Download credentials (CSV)",
        creds_df.to_csv(index=False),
        file_name="new_employee_credentials.csv",
        mime="text/csv",
    )

employees_df = get_employees_df()
performance_df = get_performance_df()
weights = get_weights()
bonus_policy_df = get_bonus_policy()
salary_df = get_salary_structure_df()

performance_df = date_range_filter(performance_df, key_prefix="dataset")

summary = build_employee_summary(employees_df, performance_df, weights, bonus_policy_df)
summary = add_salary_columns(summary, salary_df)
summary = summary.sort_values("Overall_Score", ascending=False).reset_index(drop=True)
summary.insert(0, "Rank", range(1, len(summary) + 1))

# ---------------- Search + filter ----------------
col1, col2 = st.columns([2, 1])
search_text = col1.text_input("Search by name or email")
dept_filter = col2.selectbox("Filter by department", ["All"] + sorted(summary["department"].unique().tolist()))

filtered = summary.copy()
if search_text:
    mask = (
        filtered["name"].str.contains(search_text, case=False, na=False)
        | filtered["email"].str.contains(search_text, case=False, na=False)
    )
    filtered = filtered[mask]
if dept_filter != "All":
    filtered = filtered[filtered["department"] == dept_filter]

display_cols = [
    "Rank", "employee_id", "name", "department", "email", "phone",
    "Overall_Score", "Bonus_Percent", "monthly_base_salary", "hra", "allowance",
    "Monthly_Fixed_Salary", "Performance_Bonus",
]
st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)
st.caption(
    "Performance_Bonus here is only the score-based slab bonus (% of monthly base salary). "
    "Spot, Team, Profit-Sharing and Referral bonuses are on the **Employee** page's Salary & Bonus "
    "breakdown, and are managed on the **Bonuses & Teams** page."
)

# ---------------- Download as CSV ----------------
st.download_button(
    "Download as CSV",
    filtered.to_csv(index=False).encode("utf-8"),
    file_name="staffscore_ranking.csv",
    mime="text/csv",
)

st.divider()

# ---------------- Add new record ----------------
with st.expander("Add a new employee record"):
    with st.form("add_record"):
        st.markdown("**Basic details**")
        c1, c2 = st.columns(2)
        name = c1.text_input("Name")
        department = c2.text_input("Department")
        email = c1.text_input("Email")
        phone = c1.text_input("Phone")

        st.markdown("**First month's performance**")
        c1, c2 = st.columns(2)
        month = c1.text_input("Month (YYYY-MM)", value="2026-07")
        assigned_tasks = c2.number_input("Assigned Tasks", min_value=0, value=20)
        completed_tasks = c1.number_input("Completed Tasks", min_value=0, value=18)
        completed_before_deadline = c2.number_input("Completed Before Deadline", min_value=0, value=15)
        working_days = c1.number_input("Working Days", min_value=0, value=22)
        present_days = c2.number_input("Present Days", min_value=0, value=20)
        customer_rating = c1.number_input("Customer Rating (0-5)", min_value=0.0, max_value=5.0, value=4.0)

        st.markdown("**Monthly salary structure**")
        c1, c2, c3 = st.columns(3)
        monthly_base_salary = c1.number_input("Monthly Base Salary (₹)", min_value=0.0, value=50000.0, step=1000.0)
        hra = c2.number_input("HRA (₹)", min_value=0.0, value=15000.0, step=500.0)
        allowance = c3.number_input("Allowance (₹)", min_value=0.0, value=5000.0, step=500.0)
        
        st.markdown("**Company details**")
        c1, c2 = st.columns(2)
        experience = c1.number_input("Experience (Years)", min_value=0, max_value=50, step=1, value=0)
        joining_year = c2.number_input("Joining Year", min_value=1990, max_value=2030, step=1, value=2026)

        submitted = st.form_submit_button("Add record")
        if submitted:
            try:
                new_id, temp_password = add_employee(
                    name, department, email, phone, month, assigned_tasks,
                    completed_tasks, completed_before_deadline, working_days,
                    present_days, customer_rating,
                    monthly_base_salary, hra, allowance,
                    experience, joining_year,
                )
            except ValueError as e:
                st.error(str(e))
            else:
                current_user = st.session_state.get("username", "Admin")
                log_audit_action(
                    username=current_user,
                    action=f"Added new employee record: {name}",
                    old_val="—",
                    new_val=f"Dept: {department}, Base Salary: ₹{monthly_base_salary:,.0f}"
                )
                msg = f"Added {name}."
                if temp_password:
                    msg += (
                        f" Login created for {email} with one-time password `{temp_password}` "
                        "— share it securely; it won't be shown again, and the employee "
                        "should change it after signing in."
                    )
                st.session_state["dataset_msg"] = msg
                st.rerun()

# ---------------- Add new column ----------------
with st.expander("Add a new column to the performance table"):
    with st.form("add_column"):
        col_name = st.text_input("Column name")
        col_type = st.selectbox("Column type", sorted(ALLOWED_COLUMN_TYPES))
        submitted_col = st.form_submit_button("Add column")
        if submitted_col and col_name:
            try:
                add_column_to_performance(col_name, col_type)
            except ValueError as e:
                st.error(str(e))
            else:
                current_user = st.session_state.get("username", "Admin")
                log_audit_action(
                    username=current_user,
                    action=f"Added new column '{col_name}' to Performance table",
                    old_val="—",
                    new_val=f"Type: {col_type}"
                )
                st.session_state["dataset_msg"] = f"Added column '{col_name}'."
                st.rerun()

# ---------------- Upload CSV/Excel ----------------
with st.expander("Upload employee data (CSV or Excel)"):
    st.caption("File must have these columns: " + ", ".join(REQUIRED_UPLOAD_COLUMNS))
    uploaded = st.file_uploader("Choose a file", type=["csv", "xlsx"])
    if uploaded:
        uploaded.seek(0)
        upload_df = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)
        st.dataframe(upload_df.head(), use_container_width=True, hide_index=True)
        if st.button("Import into database"):
            missing_cols = [col for col in REQUIRED_UPLOAD_COLUMNS if col not in upload_df.columns]
            if missing_cols:
                st.error(f"Missing required columns in uploaded file: {', '.join(missing_cols)}")
            else:
                count, created_logins, errors = bulk_import_from_df(upload_df)
                if errors:
                    st.error(f"Import stopped - {len(errors)} problem(s) found. Nothing was imported:")
                    for err in errors:
                        st.write(f"- {err}")
                else:
                    current_user = st.session_state.get("username", "Admin")
                    file_name = uploaded.name if uploaded else "CSV/Excel File"
                    log_audit_action(
                        username=current_user,
                        action=f"Bulk imported dataset ({file_name})",
                        old_val="—",
                        new_val=f"Imported {count} records"
                    )
                    st.session_state["dataset_msg"] = f"Imported {count} records."
                    if created_logins:
                        st.session_state["bulk_credentials"] = created_logins
                    st.rerun()
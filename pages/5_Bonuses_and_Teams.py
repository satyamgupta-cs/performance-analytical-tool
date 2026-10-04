import datetime
import pandas as pd
import streamlit as st
from ui_design import apply_modern_ui, top_profile_bar
from db_utils import (
    get_employees_df, get_company_settings,
    get_teams_df, create_team, get_team_members_df, add_team_member, remove_team_member,
    get_spot_bonus_df, add_spot_bonus, SPOT_BONUS_REASONS,
    get_team_bonus_df, add_team_bonus,
    get_profit_sharing_df, add_profit_sharing,
    get_referral_bonus_df, add_referral, update_referral_status, REFERRAL_STATUSES,
    log_audit_action, get_payslip_config
)
from payslip_utils import generate_payslip_pdf

# --- Access Control & Layout Setup ---
if "role" not in st.session_state or st.session_state.role != "admin":
    st.error("Access denied. Admins only.")
    st.stop()

st.set_page_config(page_title="Bonuses & Teams", layout="wide")
apply_modern_ui()
top_profile_bar()

st.title("Bonuses & Teams")
st.caption(
    "Record the one-time / period bonus events that feed into each employee's Salary & Bonus "
    "breakdown on the Employee page: Spot Bonus, Team Bonus, Profit-Sharing Bonus and Referral "
    "Bonus. Teams (with a manager) are set up here too, since Team Bonus needs them."
)

# Fetch Employees & Settings
employees_df = get_employees_df()
company_settings = get_company_settings()

if employees_df.empty:
    st.info("Add employees on the Dataset page first.")
    st.stop()

# Build Mapping Helpers
emp_name_by_id = dict(zip(employees_df["employee_id"], employees_df["name"]))

# Tabs Setup
tab_teams, tab_spot, tab_team_bonus, tab_profit, tab_referral = st.tabs(
    ["Teams", "Spot Bonus", "Team Bonus", "Profit-Sharing Bonus", "Referral Bonus"]
)

# ============================================================
# 1. Teams (manager + members)
# ============================================================
with tab_teams:
    st.subheader("Teams")
    st.caption("A team has one manager. Team Bonus is split evenly across a team's members.")
    teams_df = get_teams_df()
    if not teams_df.empty:
        st.dataframe(teams_df, width='stretch', hide_index=True)
    else:
        st.info("No teams yet — create one below.")

    with st.form("create_team_form"):
        c1, c2 = st.columns(2)
        team_name = c1.text_input("Team name")
        manager_id = c2.selectbox(
            "Manager", 
            options=employees_df["employee_id"],
            format_func=lambda eid: emp_name_by_id[eid]
        )
        if st.form_submit_button("Create team") and team_name:
            create_team(team_name, manager_id)
            log_audit_action(
                username=st.session_state.get("username", "Admin"),
                action=f"Created Team: {team_name}",
                old_val="—",
                new_val=f"Manager: {emp_name_by_id[manager_id]} (ID: {manager_id})"
            )
            st.success(f"Team '{team_name}' created. Refresh to see it in the list.")

    st.markdown("##### Team Members")
    teams_df = get_teams_df()
    if not teams_df.empty:
        with st.form("add_member_form"):
            c1, c2 = st.columns(2)
            member_team = c1.selectbox(
                "Team", 
                options=teams_df["team_id"],
                format_func=lambda tid: teams_df.loc[teams_df["team_id"] == tid, "team_name"].iloc[0],
                key="member_team"
            )
            member_emp = c2.selectbox(
                "Employee", 
                options=employees_df["employee_id"],
                format_func=lambda eid: emp_name_by_id[eid], 
                key="member_emp"
            )
            if st.form_submit_button("Add to team"):
                add_team_member(member_team, member_emp)
                log_audit_action(
                    username=st.session_state.get("username", "Admin"),
                    action=f"Added employee to Team ID {member_team}",
                    old_val="—",
                    new_val=f"Member: {emp_name_by_id[member_emp]} (ID: {member_emp})"
                )
                st.success("Added. Refresh to see the update.")

        members_df = get_team_members_df()
        if not members_df.empty:
            st.dataframe(members_df, width='stretch', hide_index=True)

# ============================================================
# 2. Spot Bonus
# ============================================================
with tab_spot:
    st.subheader("Spot Bonus")
    st.caption("A one-time reward for an individual's exceptional contribution — e.g. fixing a "
               "critical production bug, an emergency release, a time-saving automation, a hard "
               "technical problem solved, or exceptional client appreciation.")
    with st.form("spot_bonus_form"):
        c1, c2, c3 = st.columns(3)
        sb_employee = c1.selectbox(
            "Employee", 
            options=employees_df["employee_id"],
            format_func=lambda eid: emp_name_by_id[eid], 
            key="sb_emp"
        )
        sb_month = c2.text_input("Month (YYYY-MM)", value=datetime.date.today().strftime("%Y-%m"))
        sb_amount = c3.number_input("Amount (₹)", min_value=0.0, value=5000.0, step=500.0)
        sb_reason = st.selectbox("Reason", SPOT_BONUS_REASONS)
        sb_notes = st.text_input("Notes (optional)")
        if st.form_submit_button("Add Spot Bonus"):
            add_spot_bonus(sb_employee, sb_month, sb_amount, sb_reason, sb_notes)
            log_audit_action(
                username=st.session_state.get("username", "Admin"),
                action=f"Awarded Spot Bonus to {emp_name_by_id[sb_employee]}",
                old_val="—",
                new_val=f"Amount: ₹{sb_amount:,.0f}, Month: {sb_month}, Reason: {sb_reason}"
            )
            st.success("Spot bonus recorded.")

    spot_df = get_spot_bonus_df()
    if not spot_df.empty:
        st.dataframe(spot_df, width='stretch', hide_index=True)

# ============================================================
# 3. Team Bonus
# ============================================================
with tab_team_bonus:
    st.subheader("Team Bonus")
    st.caption("A bonus pool for a whole team's collective performance — split evenly across "
               "that team's members when computing each person's pay.")
    teams_df = get_teams_df()
    if teams_df.empty:
        st.info("Create a team in the Teams tab first.")
    else:
        with st.form("team_bonus_form"):
            c1, c2, c3 = st.columns(3)
            tb_team = c1.selectbox(
                "Team", 
                options=teams_df["team_id"],
                format_func=lambda tid: teams_df.loc[teams_df["team_id"] == tid, "team_name"].iloc[0]
            )
            tb_month = c2.text_input("Month (YYYY-MM)", value=datetime.date.today().strftime("%Y-%m"), key="tb_month")
            tb_amount = c3.number_input("Total Pool Amount (₹)", min_value=0.0, value=20000.0, step=1000.0)
            tb_reason = st.text_input("Reason (optional)", key="tb_reason")
            if st.form_submit_button("Add Team Bonus"):
                add_team_bonus(tb_team, tb_month, tb_amount, tb_reason)
                team_name_val = teams_df.loc[teams_df["team_id"] == tb_team, "team_name"].iloc[0]
                log_audit_action(
                    username=st.session_state.get("username", "Admin"),
                    action=f"Awarded Team Bonus Pool to '{team_name_val}'",
                    old_val="—",
                    new_val=f"Pool Amount: ₹{tb_amount:,.0f}, Month: {tb_month}"
                )
                st.success("Team bonus recorded. It will be split evenly across the team's current members.")

        team_bonus_df = get_team_bonus_df()
        if not team_bonus_df.empty:
            st.dataframe(team_bonus_df, width='stretch', hide_index=True)

# ============================================================
# 4. Profit-Sharing Bonus
# ============================================================
with tab_profit:
    st.subheader("Profit-Sharing Bonus")
    st.caption("Based on overall company profitability, not individual performance. The pool "
               "(company profit x pool %) is split evenly across every employee.")
    with st.form("profit_sharing_form"):
        c1, c2, c3 = st.columns(3)
        ps_period = c1.text_input("Period (YYYY-MM)", value=datetime.date.today().strftime("%Y-%m"))
        ps_profit = c2.number_input("Company Profit (₹)", min_value=0.0, value=100000000.0, step=100000.0,
                                     help="e.g. ₹10 crore = 100000000")
        ps_percent = c3.number_input("Pool %", min_value=0.0, max_value=100.0,
                                     value=company_settings.get("default_profit_pool_percent", 5.0), step=0.5)
        preview = ps_profit * ps_percent / 100
        st.caption(f"Pool amount = ₹{ps_profit:,.0f} x {ps_percent:.1f}% = **₹{preview:,.0f}**, "
                   f"split evenly across {len(employees_df)} employee(s) "
                   f"(≈ ₹{preview / len(employees_df):,.0f} each).")
        if st.form_submit_button("Add Profit-Sharing Pool"):
            add_profit_sharing(ps_period, ps_profit, ps_percent)
            log_audit_action(
                username=st.session_state.get("username", "Admin"),
                action=f"Recorded Profit-Sharing Pool ({ps_period})",
                old_val="—",
                new_val=f"Profit: ₹{ps_profit:,.0f}, Pool: {ps_percent}% (₹{preview:,.0f})"
            )
            st.success("Profit-sharing pool recorded.")

    profit_df = get_profit_sharing_df()
    if not profit_df.empty:
        st.dataframe(profit_df, width='stretch', hide_index=True)

# ============================================================
# 5. Referral Bonus
# ============================================================
with tab_referral:
    st.subheader("Referral Bonus")
    st.caption("Paid to the referring employee once their referred candidate is hired and "
               "completes the required eligibility period.")
    with st.form("referral_form"):
        c1, c2, c3 = st.columns(3)
        rb_referrer = c1.selectbox(
            "Referring Employee", 
            options=employees_df["employee_id"],
            format_func=lambda eid: emp_name_by_id[eid], 
            key="rb_emp"
        )
        rb_candidate = c2.text_input("Candidate Name")
        rb_date = c3.date_input("Referral Date", value=datetime.date.today())
        rb_amount = st.number_input("Bonus Amount (₹)", min_value=0.0,
                                     value=company_settings.get("default_referral_bonus", 10000.0), step=1000.0)
        if st.form_submit_button("Add Referral"):
            add_referral(rb_referrer, rb_candidate, rb_date, rb_amount)
            log_audit_action(
                username=st.session_state.get("username", "Admin"),
                action=f"Recorded Referral for Candidate '{rb_candidate}'",
                old_val="—",
                new_val=f"Referrer: {emp_name_by_id[rb_referrer]}, Amount: ₹{rb_amount:,.0f}, Status: Pending"
            )
            st.success("Referral recorded with status 'Pending'.")

    referral_df = get_referral_bonus_df()
    if not referral_df.empty:
        st.dataframe(referral_df, width='stretch', hide_index=True)
        st.markdown("##### Update a referral's status")
        st.caption("Flow: Pending → Hired → Eligible → Paid (or Rejected at any point). "
                   "The bonus only counts toward In Hand Salary once marked 'Paid', with a payout month.")
        with st.form("referral_status_form"):
            c1, c2, c3, c4 = st.columns(4)
            ref_id = c1.selectbox(
                "Referral", 
                options=referral_df["referral_id"],
                format_func=lambda rid: f"#{rid} - " + referral_df.loc[referral_df['referral_id'] == rid, 'candidate_name'].iloc[0]
            )
            new_status = c2.selectbox("New Status", REFERRAL_STATUSES)
            hire_date = c3.date_input("Hire Date (if applicable)", value=None)
            payout_month = c4.text_input("Payout Month (YYYY-MM, if Paid)", value="")
            if st.form_submit_button("Update Status"):
                update_referral_status(
                    ref_id, new_status,
                    hire_date=hire_date if hire_date else None,
                    payout_month=payout_month if payout_month else None,
                )
                log_audit_action(
                    username=st.session_state.get("username", "Admin"),
                    action=f"Updated Referral Status (ID: #{ref_id})",
                    old_val="—",
                    new_val=f"Status: {new_status}, Payout Month: {payout_month if payout_month else 'N/A'}"
                )
                st.success("Referral status updated.")

# ============================================================
# 6. Dynamic Payslip Builder & PDF Generator
# ============================================================
st.divider()

def render_dynamic_payslip(employee_info):
    """Renders dynamic payslip builder based on active settings and provides PDF generation."""
    emp_type = employee_info.get("emp_type", "Corporate")  # Corporate, Government, or Contract
    config = get_payslip_config()
    
    type_config = config.get(emp_type, config.get("Corporate", {}))
    active_earnings = type_config.get("earnings", ["Basic Salary", "HRA"])
    active_deductions = type_config.get("deductions", ["PF", "TDS"])

    st.subheader(f"📄 Dynamic Payslip Generator — {employee_info.get('name')} ({emp_type})")
    
    col_meta1, col_meta2 = st.columns(2)
    with col_meta1:
        target_month = st.selectbox("Target Month", [f"{m:02d}" for m in range(1, 13)], index=datetime.datetime.now().month - 1)
    with col_meta2:
        target_year = st.selectbox("Target Year", [2024, 2025, 2026, 2027], index=2)

    col_e_inputs, col_d_inputs = st.columns(2)
    earnings_data = {}
    deductions_data = {}

    with col_e_inputs:
        st.markdown("#### Earnings Breakdown")
        for field in active_earnings:
            default_val = 85000.0 if field in ["Basic Salary", "Base Salary"] else (34000.0 if field == "HRA" else 0.0)
            earnings_data[field] = st.number_input(f"{field} (₹)", min_value=0.0, value=default_val, step=500.0)

    with col_d_inputs:
        st.markdown("#### Deductions Breakdown")
        for field in active_deductions:
            default_val = 1800.0 if field in ["PF", "Provident Fund (PF)"] else (2500.0 if field in ["TDS", "Tax Deducted at Source (TDS)"] else 0.0)
            deductions_data[field] = st.number_input(f"{field} (₹)", min_value=0.0, value=default_val, step=100.0)

    # Calculations
    gross_earnings = sum(earnings_data.values())
    total_deductions = sum(deductions_data.values())
    net_salary = gross_earnings - total_deductions

    st.divider()

    # Payslip Display Output
    st.markdown("### 🧾 Salary Slip Preview")
    slip_col1, slip_col2 = st.columns(2)

    with slip_col1:
        st.write("**Earnings**")
        df_earn = pd.DataFrame(list(earnings_data.items()), columns=["Component", "Amount (₹)"])
        st.dataframe(df_earn, hide_index=True, width="stretch")
        st.markdown(f"**Gross Earnings:** `₹{gross_earnings:,.2f}`")

    with slip_col2:
        st.write("**Deductions**")
        df_ded = pd.DataFrame(list(deductions_data.items()), columns=["Component", "Amount (₹)"])
        st.dataframe(df_ded, hide_index=True, width="stretch")
        st.markdown(f"**Total Deductions:** `₹{total_deductions:,.2f}`")

    st.success(f"### 💵 Net Take-Home Salary: ₹{net_salary:,.2f}")

    # Generate PDF Action
    if st.button("📄 Export Official Payslip PDF", type="primary", use_container_width=True):
        # Prepare payload for reportlab generator
        pdf_payload = {
            'id': employee_info.get('employee_id', employee_info.get('id', 'N/A')),
            'name': employee_info.get('name', 'N/A'),
            'department': employee_info.get('department', 'N/A'),
            'email': employee_info.get('email', 'N/A'),
            'emp_type': emp_type,
            **earnings_data,
            **deductions_data
        }

        try:
            pdf_bytes = generate_payslip_pdf(
                employee_data=pdf_payload,
                month_str=target_month,
                year_str=target_year
            )
            filename = f"payslip_{pdf_payload['id']}_{target_year}-{target_month}.pdf"
            st.download_button(
                label="⬇️ Download Official Payslip PDF",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
                use_container_width=True
            )
            log_audit_action(
                username=st.session_state.get("username", "Admin"),
                action=f"Generated Payslip PDF for {employee_info.get('name')}",
                old_val="—",
                new_val=f"Period: {target_year}-{target_month}, Net Pay: ₹{net_salary:,.2f}"
            )
        except Exception as e:
            st.error(f"Error generating PDF: {e}")

# Select Employee for Payslip Generation
st.subheader("Generate Employee Payslip")
sel_emp_id = st.selectbox(
    "Select Employee for Payslip Generation", 
    options=employees_df["employee_id"],
    format_func=lambda eid: f"{emp_name_by_id[eid]} (ID: {eid})"
)

selected_emp_row = employees_df[employees_df["employee_id"] == sel_emp_id].iloc[0].to_dict()
render_dynamic_payslip(selected_emp_row)
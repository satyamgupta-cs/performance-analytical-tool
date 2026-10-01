import streamlit as st
import random
import time
from db_utils import attempt_login, run_query, admin_reset_password
from ui_design import apply_modern_ui

# Initialize session state variables
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "reset_mode" not in st.session_state:
    st.session_state.reset_mode = False
if "recovery_code" not in st.session_state:
    st.session_state.recovery_code = None
if "reset_email" not in st.session_state:
    st.session_state.reset_email = None


def login_page():
    # st.set_page_config must be the first Streamlit command in a run. This
    # function only ever runs as the page st.navigation selected below, so
    # it's safe to call here the same way every other page calls its own.
    st.set_page_config(page_title="StaffScore Login", layout="centered")
    apply_modern_ui()

    # Hide sidebar on login screen
    # st.markdown("""
    #     <style>
    #         [data-testid="stSidebar"] {display: none;}
    #         [data-testid="collapsedControl"] {display: none;}
    #     </style>
    # """, unsafe_allow_html=True)

    # ==========================================
    # LOGIN SCREEN
    # ==========================================
    if not st.session_state.reset_mode:
        st.title("StaffScore Login")

        with st.form("login_form"):
            username = st.text_input("Email / Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")

            if submitted:
                user, error = attempt_login(username, password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.role = user["role"]
                    st.session_state.employee_id = user["employee_id"]
                    st.session_state.username = user["username"]
                    st.rerun()
                else:
                    st.error(error)

        # Forgot password toggle
        if st.button("Forgot Password?"):
            st.session_state.reset_mode = True
            st.rerun()

    # ==========================================
    # FORGOT PASSWORD SCREEN
    # ==========================================
    else:
        st.title("Reset Password")
        st.write("Enter your registered email address to receive a recovery code.")

        email_input = st.text_input("Email Address", key="reset_email_input")

        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("Cancel & Go Back"):
                st.session_state.reset_mode = False
                st.session_state.recovery_code = None
                st.rerun()

        with col2:
            if st.button("Send Recovery Code"):
                df = run_query("SELECT username FROM users WHERE username=%s", (email_input,), fetch=True)

                if not df.empty:
                    st.session_state.reset_email = email_input
                    st.session_state.recovery_code = str(random.randint(100000, 999999))

                    with st.spinner("Sending email..."):
                        from email_utils import send_recovery_email
                        success, message = send_recovery_email(email_input, st.session_state.recovery_code)

                    if success:
                        st.success("Recovery code sent to your email. Check your spam folder if you don't see it.")
                    else:
                        st.error(message)
                        st.session_state.recovery_code = None
                else:
                    st.error("We couldn't find an account with that email address.")

        # Show the reset form only if a code has been generated and sent
        if st.session_state.recovery_code:
            st.divider()
            with st.form("new_password_form"):
                entered_code = st.text_input("Enter 6-Digit Code")
                new_pass = st.text_input("New Password", type="password")
                confirm_pass = st.text_input("Confirm New Password", type="password")

                if st.form_submit_button("Update Password"):
                    if entered_code != st.session_state.recovery_code:
                        st.error("Invalid recovery code.")
                    elif new_pass != confirm_pass:
                        st.error("Passwords do not match.")
                    elif len(new_pass) < 6:
                        st.error("Password must be at least 6 characters long.")
                    else:
                        success = admin_reset_password(st.session_state.reset_email, new_pass)
                        if success:
                            st.success("Password updated successfully. Redirecting to login...")
                            time.sleep(2)
                            st.session_state.reset_mode = False
                            st.session_state.recovery_code = None
                            st.rerun()
                        else:
                            st.error("A database error occurred.")


# ==========================================
# st.navigation is called unconditionally on every run - including while
# logged out - with a different page list depending on auth state. Calling
# it only inside an "if logged in" branch (as an earlier version of this
# file did) makes Streamlit inconsistently fall back to its older,
# folder-based page discovery on runs where that branch isn't reached,
# which then conflicts with st.navigation on the next run and crashes with
# "This page cannot be called directly." Always calling st.navigation
# avoids that entirely.
# ==========================================
if not st.session_state.logged_in:
    pages = [st.Page(login_page, title="Login")]
elif st.session_state.role == "admin":
    pages = [
        st.Page("pages/1_Dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True),
        st.Page("pages/2_Dataset.py", title="Dataset", icon=":material/table_view:"),
        st.Page("pages/3_Employee.py", title="Employee", icon=":material/person:"),
        st.Page("pages/4_Settings.py", title="Settings", icon=":material/settings:"),
        st.Page("pages/5_Bonuses_and_Teams.py", title="Bonuses & Teams", icon=":material/payments:"),
        st.Page("pages/6_Audit_Log.py", title="Audit Log", icon=":material/history:"),
        st.Page("pages/7_Budgets.py", title="Budgets", icon=":material/account_balance_wallet:"),
    ]
else:
    pages = [
        st.Page("pages/8_My_Dashboard.py", title="My Dashboard", icon=":material/space_dashboard:", default=True),
    ]

pg = st.navigation(pages)
pg.run()
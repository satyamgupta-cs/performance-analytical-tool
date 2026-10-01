import pandas as pd
import streamlit as st
from db_utils import get_audit_logs_df
from ui_design import apply_modern_ui, top_profile_bar

# Access Control
if "role" not in st.session_state or st.session_state.role != "admin":
    st.error("Access denied. Admins only.")
    st.stop()

st.set_page_config(page_title="Audit Log", layout="wide")
apply_modern_ui()
top_profile_bar()

st.title("System Audit Log")
st.caption(
    "Tracks all critical system changes including salary adjustments, bonus percentage overrides, score weight updates, and user role modifications for accountability and security."
)

logs_df = get_audit_logs_df()

if logs_df.empty:
    st.info("No audit logs recorded yet.")
else:
    # Summary Metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Logged Actions", len(logs_df))
    m2.metric("Unique Admin Users", logs_df["User"].nunique())
    m3.metric("Latest System Change", str(logs_df["Date & Time"].iloc[0]))

    st.divider()

    # Search and Filtering Controls
    c1, c2 = st.columns([2, 1])
    search_term = c1.text_input(
        "Search by User or Action", placeholder="e.g., Admin1, Salary updated..."
    )
    user_filter = c2.selectbox(
        "Filter by User", ["All"] + sorted(logs_df["User"].unique().tolist())
    )

    filtered_df = logs_df.copy()

    if search_term:
        mask = filtered_df["Action"].str.contains(
            search_term, case=False, na=False
        ) | filtered_df["User"].str.contains(search_term, case=False, na=False)
        filtered_df = filtered_df[mask]

    if user_filter != "All":
        filtered_df = filtered_df[filtered_df["User"] == user_filter]

    # Audit Table Display
    st.dataframe(
        filtered_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Date & Time": st.column_config.TextColumn(
                "Date & Time", width="medium"
            ),
            "User": st.column_config.TextColumn("User", width="small"),
            "Action": st.column_config.TextColumn("Action", width="large"),
            "Old Value": st.column_config.TextColumn(
                "Old Value", width="medium"
            ),
            "New Value": st.column_config.TextColumn(
                "New Value", width="medium"
            ),
        },
    )

    # Export Button
    st.download_button(
        label="Download Audit Log (CSV)",
        data=filtered_df.to_csv(index=False).encode("utf-8"),
        file_name="system_audit_log.csv",
        mime="text/csv",
    )
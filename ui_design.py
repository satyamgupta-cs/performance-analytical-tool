import streamlit as st

def apply_modern_ui():
    """Injects custom CSS to remove Streamlit branding and elevate UI components."""
    custom_css = """
    <style>
        /* Hide the default Streamlit top menu and footer */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        
        /* Add modern SaaS styling to all metric cards */
        div[data-testid="metric-container"] {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            padding: 15px;
            border-radius: 10px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            transition: transform 0.2s ease;
        }
        
        /* Subtle hover effect for metric cards */
        div[data-testid="metric-container"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
        }
        
        /* Style the main dataframe tables to look cleaner */
        .stDataFrame {
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid #E2E8F0;
        }

        /* Collapsible icon sidebar: shows page icons only until hovered,
           then expands to reveal full page names. Targets stable
           data-testid/label attributes rather than Streamlit's
           auto-generated class names, which change between builds. */
        section[data-testid="stSidebar"] {
            width: 4.5rem !important;
            min-width: 4.5rem !important;
            transition: width 0.2s ease, min-width 0.2s ease;
            overflow-x: hidden;
        }
        section[data-testid="stSidebar"]:hover {
            width: 17rem !important;
            min-width: 17rem !important;
        }
        /* Icon stays full size and never gets squeezed */
        a[data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"] {
            flex-shrink: 0;
        }
        /* Label text is hidden while collapsed, revealed on hover */
        a[data-testid="stSidebarNavLink"] span[label] {
            opacity: 0;
            width: 0;
            overflow: hidden;
            white-space: nowrap;
            transition: opacity 0.15s ease;
        }
        section[data-testid="stSidebar"]:hover a[data-testid="stSidebarNavLink"] span[label] {
            opacity: 1;
            width: auto;
        }
    </style>
    """
    st.markdown(custom_css, unsafe_allow_html=True)

def top_profile_bar():
    """Displays a standardized top-right profile box with a logout button."""
    if st.session_state.get("logged_in"):
        # Use columns to push the box all the way to the right
        col1, col2 = st.columns([8, 2])
        
        with col2:
            with st.container(border=True):
                # Display the user type
                if st.session_state.role == "admin":
                    st.markdown("**Admin**")
                else:
                    st.markdown(f"**Employee #{st.session_state.employee_id}**")
                
                # Full-width logout button inside the box
                if st.button("Log Out", use_container_width=True):
                    st.session_state.clear()
                    st.rerun()
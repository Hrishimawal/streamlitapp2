import streamlit as st
import auth.azure_auth as azure_auth
from user_app.structure import render_app

# Initialize Azure authentication
azure_auth.load_config()

# Check if user is logged in
if not st.user.get("is_logged_in", False):
    azure_auth.login_screen()
    st.stop()

# Check if user has roles
roles = azure_auth.get_user_roles()
if not roles:
    st.warning("⚠️ You do not have any assigned roles. Please contact your administrator.")
    st.button("Log out", on_click=st.logout)
    st.stop()

# Render the main application
render_app()

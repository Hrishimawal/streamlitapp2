import streamlit as st
import auth.azure_auth as azure_auth
from user_app.content import (
    render_admin_content,
    render_member_content,
    render_unauthorized_content,
)

def render_app():
    # Get user information and roles
    roles = azure_auth.get_user_roles()
    user_info = {
        "name": st.user.name,
        "preferred_username": getattr(st.user, "preferred_username", ""),
        "roles": roles
    }

    st.set_page_config(
        page_title="Azure Authenticated App",
        layout="wide"
    )

    st.header(f"Welcome, {user_info['name']}!")

    # Render appropriate content based on user role
    if azure_auth.check_user_role("Admin"):
        render_admin_content()
    elif azure_auth.check_user_role("Member"):
        render_member_content()
    else:
        render_unauthorized_content()

    col1, col2 = st.columns(2)
    with col1:
        st.button("Log out", on_click=st.logout)
    with col2:
        if st.button("Refresh Roles"):
            azure_auth.clear_role_cache(user_info['preferred_username'])
            st.success("Cache cleared! Fetching fresh roles...")
            st.rerun()

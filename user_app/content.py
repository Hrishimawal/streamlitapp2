import streamlit as st

def render_admin_content():
    """Content to show for users with Admin role."""
    st.success("🔧 Admin Panel Access")
    st.write("You have administrator privileges!")


def render_member_content():
    """Content to show for users with Member role."""
    st.info("👤 Member Access")
    st.write("You have member access!")


def render_unauthorized_content():
    """Content to show for users without specific roles."""
    st.warning("No specific role assigned")

    # Add your limited access content here
    st.write("You have limited access to this application.")
    st.write("Please contact your administrator for role assignment.")

import streamlit as st
import os
import json
from streamlit.runtime.secrets import secrets_singleton
from azure.appconfiguration import AzureAppConfigurationClient
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from datetime import datetime, timedelta

# In-memory cache for roles with TTL to improve performance
_role_cache = {}
_cache_ttl = 300  # seconds (5 minutes)

def load_config():
    auth_secrets = {
        "auth": {
            "redirect_uri": os.getenv('AZURE_AUTH_REDIRECT_URI'),
            "cookie_secret": "xxx",
            "microsoft": {
                "client_id": os.getenv('AZURE_AUTH_CLIENT_ID'),
                "client_secret": os.getenv('AZURE_AUTH_CLIENT_SECRET'),
                "server_metadata_url": f"https://login.microsoftonline.com/{os.getenv('AZURE_AUTH_TENANT_ID')}/v2.0/.well-known/openid-configuration",
                "client_kwargs": {
                    "scope": "openid profile email",
                    "prompt": "select_account"
                }
            }
        }
    }
    secrets_singleton._secrets = auth_secrets
    for k, v in auth_secrets.items():
        secrets_singleton._maybe_set_environment_variable(k, v)


def login_screen():
    """Display login screen."""
    st.subheader("Please log in.")
    if st.button("Login with Microsoft"):
        st.login("microsoft")


def get_app_config_client():
    # try connection string if available
    connection_string = os.getenv('AZURE_APPCONFIG_CONNECTION_STRING')
    if connection_string:
        try:
            return AzureAppConfigurationClient.from_connection_string(connection_string)
        except Exception as e:
            st.error(f"Failed to connect using connection string: {str(e)}")

    # try managed identity or other methods via DefaultAzureCredential
    endpoint = os.getenv('AZURE_APPCONFIG_ENDPOINT')
    if endpoint:
        try:
            credential = DefaultAzureCredential()
            return AzureAppConfigurationClient(base_url=endpoint, credential=credential)
        except Exception as e:
            st.error(f"Failed to connect using managed identity or other credentials: {str(e)}")

    return None


def get_user_roles(force_refresh=False):
    if not hasattr(st.user, 'preferred_username') or not st.user.preferred_username:
        return []

    user_email = st.user.preferred_username.lower()
    # Check cache first
    if not force_refresh and user_email in _role_cache:
        cache_entry = _role_cache[user_email]
        if datetime.now() < cache_entry['expires']:
            return cache_entry['roles']

    try:
        client = get_app_config_client()
        if not client:
            return []

        # Get role configuration
        key = f"users:{user_email}:roles"
        try:
            setting = client.get_configuration_setting(key=key)

            roles = []
            if setting and setting.value:
                try:
                    roles = json.loads(setting.value)
                except Exception:
                    roles = [setting.value]  # Single role as string

            # Update cache with TTL
            _role_cache[user_email] = {
                'roles': roles,
                'expires': datetime.now() + timedelta(seconds=_cache_ttl)
            }

            return roles

        except ResourceNotFoundError:
            # This is normal for new users - no need to show an error
            _role_cache[user_email] = {
                'roles': [],
                'expires': datetime.now() + timedelta(seconds=_cache_ttl)
            }
            return []

    except Exception as e:
        st.error(f"Error connecting to App Configuration: {str(e)}")
        return []


def is_logged_in_and_in_role():
    return st.user.get("is_logged_in", False) and bool(get_user_roles())


def check_user_role(required_role):
    return required_role in get_user_roles()


def clear_role_cache(user_email=None):
    global _role_cache

    if user_email is not None:
        user_email = user_email.lower()
        if user_email in _role_cache:
            del _role_cache[user_email]
            return True
    else:
        _role_cache.clear()
        return True

    return False

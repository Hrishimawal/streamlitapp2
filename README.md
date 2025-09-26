# webapp-yoshi Web App

A Streamlit application template with Azure AD authentication and role-based access control using Azure App
Configuration.

## Overview

This template provides a modular Streamlit application with:

- Azure AD Authentication: Secure user login using Microsoft identity platform
- Role-Based Access Control: Using Azure App Configuration for flexible permission management
- Modular Design: Clean separation between authentication and application code
- CI/CD Pipeline: GitLab CI integration for automated deployment to Azure Web App

## Respository Structure

The application follows a modular architecture that separates concerns:

```
├── auth/                           # Authentication module
│   └── azure_auth.py               # Azure AD authentication and role management
├── config/                         # Configuration files
│   └── users.json                  # User role assignments
├── scripts/                        # Utility scripts
│   └── manage_app_config_roles.py  # Role management tool
├── user_app/                       # User application code (where you add your content)
│   ├── content.py                  # Define your UI components here
│   └── structure.py                # Application structure and layout
├── .gitlab-ci.yml                  # CI Pipeline
├── Dockerfile                      # Container definition
├── README.md                       #
├── app.py                          # Main application entry point (authentication wrapper)
└── requirements.txt                # Python dependencies
```

## Getting Started

### Prerequisites

### Environment Variables

The application requires the following environment variables:

```sh
# Authentication
AZURE_AUTH_CLIENT_ID=<your-azure-ad-app-client-id>
AZURE_AUTH_CLIENT_SECRET=<your-azure-ad-app-client-secret>
AZURE_AUTH_TENANT_ID=<your-azure-ad-tenant-id>
AUTH_REDIRECT_URI=<your-auth-callback-url>

# App Configuration
AZURE_APPCONFIG_ENDPOINT=<your-app-config-endpoint>
```

For local development, you can create a `.env` file with these variables.

### Customizing the Application

#### Adding Your Content

To add your own application content, you only need to modify files in the `user_app` directory:

- Define Role-Specific Content: Modify content.py to implement the UI for each role:

```python
import streamlit as st

def render_admin_content():
    """Content to show for users with Admin role."""
    st.success("🔧 Admin Panel Access")
    st.write("You have administrator privileges!")

    # Add your admin-specific UI components here
    st.subheader("My Admin Dashboard")
    # ...

def render_member_content():
    """Content to show for users with Member role."""
    st.info("👤 Member Access")
    st.write("You have member access!")

    # Add your member-specific UI components here
    # ...
```

### User Role Management

User roles are managed in Azure App Configuration with the following structure:

- Key Format: users:{email}:roles
- Value: JSON array of role names (e.g., ["Admin"] or ["Member"])

Use the included management script to update roles:

```python
python scripts/manage_app_config_roles.py \
  --file config/users.json \
  --endpoint "$AZURE_APPCONFIG_ENDPOINT"
```

## Deployment

### Container Deployment

The application includes a Dockerfile for containerization:

```sh
# Build the container
docker build -t streamlit-auth-app .

# Run locally
docker run -p 8501:8000 --env-file .env streamlit-auth-app
```

### Azure Web App Deployment

The included GitLab CI pipeline automates deployment to Azure Web App:

- Updates user roles in Azure App Configuration
- Builds and pushes the container to Azure Container Registry
- Updates the Azure Web App to use the latest container image

## Security Considerations

- The application uses Azure AD for secure authentication
- Role information is cached for 5 minutes for performance
- Service principals require appropriate permissions:
- App Configuration Data Reader/Owner permissions
- AcrPull/AcrPush permissions for Azure Container Registry

## Advanced Configuration

### Adding New Roles

- Update your `users.json` file with the new role assignments
- Run the `manage_app_config_roles.py` script to update Azure App Configuration
- Update your `content.py` to handle the new role

### Customizing Authentication Behavior

Authentication settings can be adjusted in `azure_auth.py`, including:

- Cache TTL for role information
- Authentication prompts and scopes
- Error handling behavior

## Troubleshooting

### Role Refresh

- If role updates aren't visible, users can click "Refresh Roles" to clear their role cache.

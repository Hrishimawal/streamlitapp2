import sys
import json
import time
import argparse
import logging
from typing import List, Dict, Any, Optional, Tuple

from azure.appconfiguration import AzureAppConfigurationClient, ConfigurationSetting
from azure.core.exceptions import (
    ResourceNotFoundError,
    HttpResponseError,
    ServiceRequestError,
    ClientAuthenticationError
)
from azure.identity import (
    AzureCliCredential,
    ChainedTokenCredential,
    ManagedIdentityCredential,
    EnvironmentCredential
)

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 25  # Process users in batches for better performance
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2

class RoleAssignmentError(Exception):
    pass

def setup_logging(log_level: int = logging.INFO) -> None:
    root_logger = logging.getLogger()
    if root_logger.handlers:
        # Avoid duplicate handlers in case this function is called multiple times
        for handler in root_logger.handlers:
            root_logger.removeHandler(handler)

    log_format = '%(asctime)s [%(levelname)s] [%(name)s] - %(message)s'
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    # Disable verbose HTTP and other logging from Azure SDK
    logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("azure.identity").setLevel(logging.WARNING)
    logging.getLogger("azure.identity._internal.decorators").setLevel(logging.WARNING)

    logging.getLogger(__name__).setLevel(log_level)

def load_users(file_path: str) -> List[Dict[str, Any]]:
    try:
        with open(file_path, 'r') as f:
            users = json.load(f)
            logger.info(f"Successfully loaded {len(users)} users from {file_path}")
            return users
    except FileNotFoundError:
        logger.error(f"User file not found: {file_path}")
        raise
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in user file: {file_path}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error loading users: {str(e)}")
        raise


def get_app_config_client(
    connection_string: Optional[str] = None,
    endpoint: Optional[str] = None,
) -> AzureAppConfigurationClient:
    if connection_string:
        logger.info("Connecting with connection string")
        try:
            return AzureAppConfigurationClient.from_connection_string(connection_string)
        except Exception as e:
            logger.error(f"Failed to connect using connection string: {str(e)}")
            raise ClientAuthenticationError("Connection string authentication failed") from e
    elif endpoint:
        logger.info(f"Connecting to endpoint {endpoint}")

        try:
            credential = ChainedTokenCredential(
                ManagedIdentityCredential(),
                EnvironmentCredential(),
                AzureCliCredential()
            )

            logger.info("Using ChainedTokenCredential for authentication")
            client = AzureAppConfigurationClient(base_url=endpoint, credential=credential)

            try:
                next(iter(client.list_configuration_settings(key_filter="*")), None)
                logger.info("Connection test successful")
                return client
            except Exception as e:
                logger.error(f"Connection test failed: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Authentication failed: {str(e)}")
            raise ClientAuthenticationError(f"Failed to authenticate to {endpoint}") from e
    else:
        raise ValueError("Either connection_string or endpoint must be provided")


def get_existing_role_keys(client: AzureAppConfigurationClient) -> List[str]:
    existing_keys = []
    attempt = 0

    while attempt < MAX_RETRY_ATTEMPTS:
        try:
            logger.info("Fetching existing role configuration keys")
            for setting in client.list_configuration_settings(key_filter="users:*"):
                existing_keys.append(setting.key)
            logger.info(f"Found {len(existing_keys)} existing role configuration keys")
            return existing_keys
        except ServiceRequestError as e:
            attempt += 1
            if attempt < MAX_RETRY_ATTEMPTS:
                logger.warning(f"Network error listing keys (attempt {attempt}/{MAX_RETRY_ATTEMPTS}): {str(e)}")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                logger.error(f"Failed to list keys after {MAX_RETRY_ATTEMPTS} attempts: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Error listing configuration settings: {str(e)}")
            raise


def process_user_batch(
    client: AzureAppConfigurationClient,
    users: List[Dict[str, Any]],
    start_idx: int,
    end_idx: int,
) -> Tuple[int, int]:
    successful = 0
    failed = 0

    for idx in range(start_idx, min(end_idx, len(users))):
        user = users[idx]
        email = user.get('name', '').lower()
        role = user.get('role', '')

        if not email or not role:
            logger.info(f"Skipping invalid user entry: {user}")
            continue

        key = f"users:{email}:roles"

        try:
            # Try to get existing setting first
            try:
                existing_setting = client.get_configuration_setting(key=key)
                logger.debug(f"Updating existing role for {email}")
                existing_setting.value = json.dumps([role])
                client.set_configuration_setting(configuration_setting=existing_setting)
            except ResourceNotFoundError:
                logger.debug(f"Creating new role entry for {email}")
                setting = ConfigurationSetting(
                    key=key,
                    value=json.dumps([role]),
                    content_type="application/json"
                )
                client.add_configuration_setting(configuration_setting=setting)

            successful += 1
            logger.info(f"Set {key} to [{role}]")

        except HttpResponseError as e:
            failed += 1
            logger.error(f"HTTP Error for {email}: {str(e)} (Status: {getattr(e, 'status_code', 'Unknown')})")
        except Exception as e:
            failed += 1
            logger.error(f"Unexpected error for {email}: {str(e)}")

    return successful, failed


def remove_obsolete_roles(
    client: AzureAppConfigurationClient,
    existing_keys: List[str],
    current_emails: List[str],
) -> Tuple[int, int]:
    successful = 0
    failed = 0

    for key in existing_keys:
        # Extract email from the key (format is "users:email:roles")
        parts = key.split(':')
        if len(parts) == 3 and parts[0] == 'users':
            email = parts[1]
            if email not in current_emails:
                logger.info(f"Removing {key} as user is no longer in the list")
                try:
                    client.delete_configuration_setting(key=key)
                    successful += 1
                except ResourceNotFoundError:
                    logger.info(f"Key {key} not found, already deleted")
                    successful += 1  # Count as success since the end state is as expected
                except Exception as e:
                    logger.error(f"Failed to remove {key}: {str(e)}")
                    failed += 1

    return successful, failed


def update_user_roles(
    users: List[Dict[str, Any]],
    connection_string: Optional[str] = None,
    endpoint: Optional[str] = None,
    remove_missing: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Dict[str, Any]:
    start_time = time.time()
    metrics = {
        "successful_updates": 0,
        "failed_updates": 0,
        "successful_removals": 0,
        "failed_removals": 0,
        "total_users": len(users),
        "execution_time_seconds": 0
    }

    try:
        client = get_app_config_client(connection_string, endpoint)

        # Get existing role keys if needed for removal
        existing_keys = []
        if remove_missing:
            existing_keys = get_existing_role_keys(client)

        # Process users in batches for better performance
        for i in range(0, len(users), batch_size):
            batch_start = i
            batch_end = min(i + batch_size, len(users))
            logger.info(f"Processing batch {batch_start+1}-{batch_end} of {len(users)} users")

            successful, failed = process_user_batch(client, users, batch_start, batch_end)
            metrics["successful_updates"] += successful
            metrics["failed_updates"] += failed

        # Remove obsolete roles if requested
        if remove_missing:
            current_emails = [user.get('name', '').lower() for user in users
                              if user.get('name')]

            successful, failed = remove_obsolete_roles(client, existing_keys, current_emails)
            metrics["successful_removals"] = successful
            metrics["failed_removals"] = failed

    except ClientAuthenticationError as e:
        logger.error(f"Authentication error: {str(e)}")
        raise RoleAssignmentError(f"Authentication failed: {str(e)}") from e
    except Exception as e:
        logger.error(f"Unexpected error in role assignment: {str(e)}")
        raise RoleAssignmentError(f"Role assignment failed: {str(e)}") from e
    finally:
        # Always record execution time
        metrics["execution_time_seconds"] = round(time.time() - start_time, 2)

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description='Manage user roles in Azure App Configuration')
    parser.add_argument('--file', required=True, help='Path to users JSON file')
    parser.add_argument('--connection-string', help='Azure App Configuration connection string')
    parser.add_argument('--endpoint', help='Azure App Configuration endpoint URL')
    parser.add_argument('--remove-missing', action='store_true',
                        help='Remove roles for users not in the input file')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                        help=f'Number of users to process in each batch (default: {DEFAULT_BATCH_SIZE})')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        default='INFO', help='Set the logging level')

    args = parser.parse_args()

    log_level = getattr(logging, args.log_level)
    setup_logging(log_level)

    if not args.connection_string and not args.endpoint:
        logger.error("Either --connection-string or --endpoint must be provided")
        sys.exit(1)

    try:
        logger.info(f"Starting role assignment process for {args.file}")
        users = load_users(args.file)

        metrics = update_user_roles(
            users,
            args.connection_string,
            args.endpoint,
            args.remove_missing,
            args.batch_size
        )

        # Log summary statistics
        logger.info("Role assignment completed")
        logger.info(f"{metrics['successful_updates']} roles updated successfully")

        if metrics['failed_updates'] > 0:
            logger.warning(f"{metrics['failed_updates']} role updates failed")

        if args.remove_missing:
            logger.info(f"{metrics['successful_removals']} obsolete roles removed")
            if metrics['failed_removals'] > 0:
                logger.warning(f"{metrics['failed_removals']} role removals failed")

        logger.info(f"Total execution time: {metrics['execution_time_seconds']} seconds")

        # Return non-zero exit code if any operations failed
        if metrics['failed_updates'] > 0 or metrics['failed_removals'] > 0:
            sys.exit(1)

    except FileNotFoundError:
        logger.error(f"User file not found: {args.file}")
        sys.exit(2)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in user file: {args.file}")
        sys.exit(3)
    except RoleAssignmentError as e:
        logger.error(str(e))
        sys.exit(4)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        sys.exit(10)


if __name__ == "__main__":
    main()

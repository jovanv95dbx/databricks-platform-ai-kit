"""
Credential management for Terraform-based workspace provisioning.

Stores and retrieves cloud credentials securely using macOS Keychain
(preferred) or environment variables (fallback).
"""

import json
import os
import platform
import subprocess
import sys

# Keychain service name prefix
_KEYCHAIN_SERVICE_PREFIX = "databricks-ai-dev-kit"

# Env var mappings for Azure
_AZURE_ENV_VARS = {
    "subscription_id": "ARM_SUBSCRIPTION_ID",
    "tenant_id": "ARM_TENANT_ID",
    "client_id": "ARM_CLIENT_ID",
    "client_secret": "ARM_CLIENT_SECRET",
}

# Env var mappings for Databricks account (OAuth M2M — modern pattern)
_DATABRICKS_ENV_VARS = {
    "account_id": "DATABRICKS_ACCOUNT_ID",
    "client_id": "DATABRICKS_CLIENT_ID",
    "client_secret": "DATABRICKS_CLIENT_SECRET",
}

# Legacy: also check for token-based auth
_DATABRICKS_TOKEN_ENV_VARS = {
    "account_id": "DATABRICKS_ACCOUNT_ID",
    "token": "DATABRICKS_TOKEN",
}

# Env var mappings for GCP
_GCP_ENV_VARS = {
    "google_project": "GOOGLE_PROJECT",
    "google_service_account": "GOOGLE_SERVICE_ACCOUNT",
    "google_region": "GOOGLE_REGION",
}


def _keychain_available() -> bool:
    """Check if macOS Keychain is available."""
    return platform.system() == "Darwin"


def _keychain_service(profile: str, cred_type: str) -> str:
    """Build the Keychain service name."""
    return f"{_KEYCHAIN_SERVICE_PREFIX}-{cred_type}-{profile}"


def _keychain_store(service: str, account: str, data: dict) -> None:
    """Store a JSON blob in macOS Keychain."""
    password = json.dumps(data)
    # Delete existing entry first (ignore errors if not found)
    subprocess.run(
        ["security", "delete-generic-password", "-s", service, "-a", account],
        capture_output=True,
    )
    result = subprocess.run(
        [
            "security",
            "add-generic-password",
            "-s", service,
            "-a", account,
            "-w", password,
            "-U",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to store credentials in Keychain: {result.stderr}")


def _keychain_retrieve(service: str, account: str) -> dict | None:
    """Retrieve a JSON blob from macOS Keychain."""
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return None


def _keychain_delete(service: str, account: str) -> bool:
    """Delete a Keychain entry. Returns True if deleted."""
    result = subprocess.run(
        ["security", "delete-generic-password", "-s", service, "-a", account],
        capture_output=True,
    )
    return result.returncode == 0


def _keychain_list_profiles() -> list[str]:
    """List all stored credential profiles by scanning Keychain."""
    result = subprocess.run(
        ["security", "dump-keychain"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []

    profiles = set()
    for line in result.stdout.splitlines():
        if f'"{_KEYCHAIN_SERVICE_PREFIX}-' in line and "svce" in line:
            # Extract service name from: "svce"<blob>="databricks-ai-dev-kit-azure-default"
            try:
                start = line.index(f'"{_KEYCHAIN_SERVICE_PREFIX}-') + 1
                end = line.index('"', start)
                service = line[start:end]
                # Parse profile from service name: prefix-type-profile
                parts = service.replace(f"{_KEYCHAIN_SERVICE_PREFIX}-", "").split("-", 1)
                if len(parts) == 2:
                    profiles.add(parts[1])
            except (ValueError, IndexError):
                continue
    return sorted(profiles)


def store_azure_credentials(
    subscription_id: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    profile: str = "default",
) -> dict:
    """
    Store Azure Service Principal credentials.

    Args:
        subscription_id: Azure subscription ID
        tenant_id: Azure AD tenant ID
        client_id: Service principal application (client) ID
        client_secret: Service principal secret
        profile: Credential profile name (default: "default")

    Returns:
        dict with status and storage backend used
    """
    data = {
        "subscription_id": subscription_id,
        "tenant_id": tenant_id,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    if _keychain_available():
        service = _keychain_service(profile, "azure")
        _keychain_store(service, "azure-sp", data)
        return {"status": "stored", "backend": "keychain", "profile": profile}
    else:
        return {
            "status": "error",
            "error": "Keychain not available on this platform. "
                     "Set environment variables instead: "
                     "ARM_SUBSCRIPTION_ID, ARM_TENANT_ID, ARM_CLIENT_ID, ARM_CLIENT_SECRET",
        }


def get_azure_credentials(profile: str = "default") -> dict:
    """
    Retrieve Azure credentials from Keychain or environment variables.

    Args:
        profile: Credential profile name (default: "default")

    Returns:
        dict with subscription_id, tenant_id, client_id, client_secret
        or dict with error key if not found
    """
    # Try Keychain first
    if _keychain_available():
        service = _keychain_service(profile, "azure")
        data = _keychain_retrieve(service, "azure-sp")
        if data:
            return data

    # Fall back to environment variables
    env_creds = {}
    missing = []
    for key, env_var in _AZURE_ENV_VARS.items():
        value = os.environ.get(env_var)
        if value:
            env_creds[key] = value
        else:
            missing.append(env_var)

    if not missing:
        return env_creds

    return {
        "error": f"Azure credentials not found for profile '{profile}'. "
                 f"Store them with manage_credentials(action='store_azure') or "
                 f"set environment variables: {', '.join(missing)}",
    }


def store_databricks_account_credentials(
    account_id: str,
    client_id: str = None,
    client_secret: str = None,
    token: str = None,
    profile: str = "default",
) -> dict:
    """
    Store Databricks account-level credentials.

    Supports two auth modes:
    - OAuth M2M (recommended): account_id + client_id + client_secret
    - PAT token (legacy): account_id + token

    Args:
        account_id: Databricks account ID
        client_id: Service principal application ID (OAuth M2M)
        client_secret: Service principal secret (OAuth M2M)
        token: Account-level API token (legacy, use OAuth M2M instead)
        profile: Credential profile name (default: "default")

    Returns:
        dict with status and storage backend used
    """
    data = {"account_id": account_id}
    if client_id and client_secret:
        data["client_id"] = client_id
        data["client_secret"] = client_secret
        data["auth_type"] = "oauth-m2m"
    elif token:
        data["token"] = token
        data["auth_type"] = "pat"
    else:
        return {
            "status": "error",
            "error": "Provide either client_id+client_secret (OAuth M2M) or token (PAT).",
        }

    if _keychain_available():
        service = _keychain_service(profile, "databricks")
        _keychain_store(service, "databricks-account", data)
        return {"status": "stored", "backend": "keychain", "profile": profile, "auth_type": data["auth_type"]}
    else:
        return {
            "status": "error",
            "error": "Keychain not available on this platform. "
                     "Set environment variables instead: "
                     "DATABRICKS_ACCOUNT_ID, DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET",
        }


def store_gcp_credentials(
    google_project: str,
    google_service_account: str,
    google_region: str = "us-central1",
    profile: str = "default",
) -> dict:
    """
    Store GCP credentials for Databricks workspace provisioning.

    Args:
        google_project: GCP project ID
        google_service_account: Email of the GCP service account
        google_region: GCP region (default: us-central1)
        profile: Credential profile name (default: "default")

    Returns:
        dict with status and storage backend used
    """
    data = {
        "google_project": google_project,
        "google_service_account": google_service_account,
        "google_region": google_region,
    }

    if _keychain_available():
        service = _keychain_service(profile, "gcp")
        _keychain_store(service, "gcp-sa", data)
        return {"status": "stored", "backend": "keychain", "profile": profile}
    else:
        return {
            "status": "error",
            "error": "Keychain not available on this platform. "
                     "Set environment variables instead: "
                     "GOOGLE_PROJECT, GOOGLE_SERVICE_ACCOUNT, GOOGLE_REGION",
        }


def get_gcp_credentials(profile: str = "default") -> dict:
    """
    Retrieve GCP credentials from Keychain or environment variables.

    Args:
        profile: Credential profile name (default: "default")

    Returns:
        dict with google_project, google_service_account, google_region
        or dict with error key if not found
    """
    if _keychain_available():
        service = _keychain_service(profile, "gcp")
        data = _keychain_retrieve(service, "gcp-sa")
        if data:
            return data

    env_creds = {}
    missing = []
    for key, env_var in _GCP_ENV_VARS.items():
        value = os.environ.get(env_var)
        if value:
            env_creds[key] = value
        else:
            missing.append(env_var)

    if not missing:
        return env_creds

    return {
        "error": f"GCP credentials not found for profile '{profile}'. "
                 f"Store them with manage_credentials(action='store_gcp') or "
                 f"set environment variables: {', '.join(missing)}",
    }


def get_databricks_account_credentials(profile: str = "default") -> dict:
    """
    Retrieve Databricks account credentials from Keychain or environment variables.

    Supports OAuth M2M (client_id/client_secret) and legacy PAT (token).

    Args:
        profile: Credential profile name (default: "default")

    Returns:
        dict with account_id and either client_id+client_secret or token,
        or dict with error key if not found
    """
    # Try Keychain first
    if _keychain_available():
        service = _keychain_service(profile, "databricks")
        data = _keychain_retrieve(service, "databricks-account")
        if data:
            return data

    # Fall back to environment variables — try OAuth M2M first
    env_creds = {}
    missing = []
    for key, env_var in _DATABRICKS_ENV_VARS.items():
        value = os.environ.get(env_var)
        if value:
            env_creds[key] = value
        else:
            missing.append(env_var)

    if not missing:
        env_creds["auth_type"] = "oauth-m2m"
        return env_creds

    # Try legacy token auth
    env_creds = {}
    missing = []
    for key, env_var in _DATABRICKS_TOKEN_ENV_VARS.items():
        value = os.environ.get(env_var)
        if value:
            env_creds[key] = value
        else:
            missing.append(env_var)

    if not missing:
        env_creds["auth_type"] = "pat"
        return env_creds

    return {
        "error": f"Databricks account credentials not found for profile '{profile}'. "
                 f"Store them with manage_credentials(action='store_databricks_account') or "
                 f"set environment variables: DATABRICKS_ACCOUNT_ID + "
                 f"DATABRICKS_CLIENT_ID/DATABRICKS_CLIENT_SECRET (OAuth M2M) or "
                 f"DATABRICKS_TOKEN (PAT)",
    }


def list_credential_profiles() -> list[str]:
    """
    List all stored credential profiles.

    Returns:
        List of profile names that have stored credentials.
    """
    if _keychain_available():
        return _keychain_list_profiles()
    # For env var fallback, can only report "default" if all vars are set
    azure_set = all(os.environ.get(v) for v in _AZURE_ENV_VARS.values())
    db_set = all(os.environ.get(v) for v in _DATABRICKS_ENV_VARS.values())
    if azure_set or db_set:
        return ["default (env vars)"]
    return []


def delete_credentials(profile: str = "default") -> dict:
    """
    Delete stored credentials for a profile.

    Args:
        profile: Credential profile name (default: "default")

    Returns:
        dict with status
    """
    if not _keychain_available():
        return {"status": "error", "error": "Keychain not available. Unset environment variables manually."}

    deleted = []
    for cred_type, account in [("azure", "azure-sp"), ("databricks", "databricks-account"), ("gcp", "gcp-sa")]:
        service = _keychain_service(profile, cred_type)
        if _keychain_delete(service, account):
            deleted.append(cred_type)

    if deleted:
        return {"status": "deleted", "profile": profile, "deleted_types": deleted}
    return {"status": "not_found", "profile": profile}

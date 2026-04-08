"""
Account-level and workspace configuration API for Databricks.

SDK-based functions for managing account-level resources (users, groups,
service principals, workspace assignments) and workspace-level configuration
(IP access lists, secret scopes, cluster policies, SQL warehouses).

Account-level operations use AccountClient (requires account credentials).
Workspace-level operations use WorkspaceClient (from auth.py).
"""

import json
import logging
from typing import Any, Dict, List, Optional

from databricks.sdk import AccountClient
from databricks.sdk.service.catalog import (
    AzureManagedIdentityRequest,
    AwsIamRoleRequest,
    CreateAccountsMetastore,
    CreateAccountsStorageCredential,
    UpdateAccountsMetastore,
)

from databricks_platform_core.auth import get_workspace_client
from databricks_platform_core.identity import PRODUCT_NAME, PRODUCT_VERSION
from databricks_platform_core.credentials import (
    get_databricks_account_credentials,
    get_azure_credentials,
    get_gcp_credentials,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Account Client Factory
# =============================================================================


def get_account_client(
    cloud: Optional[str] = None,
    profile: str = "default",
) -> AccountClient:
    """Get a Databricks AccountClient using stored credentials.

    Args:
        cloud: Cloud provider ("azure", "aws", "gcp"). Auto-detected from
               stored credential profiles if not provided.
        profile: Credential profile name.

    Returns:
        Configured AccountClient instance.

    Raises:
        ValueError: If credentials are not found or cloud cannot be determined.
    """
    creds = get_databricks_account_credentials(profile)
    if "error" in creds:
        raise ValueError(creds["error"])

    account_id = creds["account_id"]

    if cloud is None:
        cloud = _detect_cloud(profile)

    host_map = {
        "azure": "https://accounts.azuredatabricks.net",
        "aws": "https://accounts.cloud.databricks.com",
        "gcp": "https://accounts.gcp.databricks.com",
    }
    host = host_map.get(cloud.lower())
    if not host:
        raise ValueError(f"Unknown cloud: {cloud}. Use 'azure', 'aws', or 'gcp'.")

    kwargs: Dict[str, Any] = {
        "host": host,
        "account_id": account_id,
        "product": PRODUCT_NAME,
        "product_version": PRODUCT_VERSION,
    }

    if creds.get("auth_type") == "oauth-m2m":
        kwargs["client_id"] = creds["client_id"]
        kwargs["client_secret"] = creds["client_secret"]
    elif creds.get("token"):
        kwargs["token"] = creds["token"]

    return AccountClient(**kwargs)


def _detect_cloud(profile: str = "default") -> str:
    """Detect cloud provider from stored credential profiles."""
    azure = get_azure_credentials(profile)
    if "error" not in azure:
        return "azure"
    gcp = get_gcp_credentials(profile)
    if "error" not in gcp:
        return "gcp"
    return "aws"


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    """Convert SDK object to serializable dict."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "as_dict"):
        return obj.as_dict()
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    return vars(obj)


# =============================================================================
# Account Identity: Users
# =============================================================================


def list_account_users(
    cloud: Optional[str] = None,
    profile: str = "default",
    filter_str: Optional[str] = None,
    max_results: int = 100,
) -> List[Dict[str, Any]]:
    """List users in the Databricks account.

    Args:
        cloud: Cloud provider (auto-detected if not provided).
        profile: Credential profile name.
        filter_str: SCIM filter string (e.g., 'displayName co "john"').
        max_results: Maximum number of users to return.

    Returns:
        List of user dicts with id, user_name, display_name, active.
    """
    a = get_account_client(cloud=cloud, profile=profile)
    kwargs: Dict[str, Any] = {}
    if filter_str:
        kwargs["filter"] = filter_str
    users = []
    for u in a.users.list(**kwargs):
        users.append({
            "id": u.id,
            "user_name": u.user_name,
            "display_name": u.display_name,
            "active": u.active,
        })
        if len(users) >= max_results:
            break
    return users


def create_account_user(
    user_name: str,
    display_name: Optional[str] = None,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Create a user in the Databricks account.

    Args:
        user_name: Email address for the user.
        display_name: Display name (defaults to user_name).
        cloud: Cloud provider.
        profile: Credential profile name.

    Returns:
        Dict with created user info.
    """
    a = get_account_client(cloud=cloud, profile=profile)
    user = a.users.create(
        user_name=user_name,
        display_name=display_name or user_name,
    )
    return {
        "id": user.id,
        "user_name": user.user_name,
        "display_name": user.display_name,
        "active": user.active,
    }


def get_account_user(
    user_id: str,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Get a user by ID."""
    a = get_account_client(cloud=cloud, profile=profile)
    user = a.users.get(id=user_id)
    return {
        "id": user.id,
        "user_name": user.user_name,
        "display_name": user.display_name,
        "active": user.active,
        "groups": [
            {"display": g.display, "value": g.value}
            for g in (user.groups or [])
        ],
    }


def delete_account_user(
    user_id: str,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Delete a user from the Databricks account."""
    a = get_account_client(cloud=cloud, profile=profile)
    a.users.delete(id=user_id)
    return {"status": "deleted", "user_id": user_id}


# =============================================================================
# Account Identity: Groups
# =============================================================================


def list_account_groups(
    cloud: Optional[str] = None,
    profile: str = "default",
    filter_str: Optional[str] = None,
    max_results: int = 100,
) -> List[Dict[str, Any]]:
    """List groups in the Databricks account."""
    a = get_account_client(cloud=cloud, profile=profile)
    kwargs: Dict[str, Any] = {}
    if filter_str:
        kwargs["filter"] = filter_str
    groups = []
    for g in a.groups.list(**kwargs):
        groups.append({
            "id": g.id,
            "display_name": g.display_name,
            "member_count": len(g.members) if g.members else 0,
        })
        if len(groups) >= max_results:
            break
    return groups


def create_account_group(
    display_name: str,
    member_ids: Optional[List[str]] = None,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Create a group in the Databricks account.

    Args:
        display_name: Group name.
        member_ids: Optional list of user/SP IDs to add as members.
        cloud: Cloud provider.
        profile: Credential profile name.

    Returns:
        Dict with created group info.
    """
    from databricks.sdk.service.iam import ComplexValue

    a = get_account_client(cloud=cloud, profile=profile)
    members = None
    if member_ids:
        members = [ComplexValue(value=mid) for mid in member_ids]
    group = a.groups.create(display_name=display_name, members=members)
    return {
        "id": group.id,
        "display_name": group.display_name,
        "member_count": len(group.members) if group.members else 0,
    }


def get_account_group(
    group_id: str,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Get a group by ID with its members."""
    a = get_account_client(cloud=cloud, profile=profile)
    group = a.groups.get(id=group_id)
    return {
        "id": group.id,
        "display_name": group.display_name,
        "members": [
            {"value": m.value, "display": m.display}
            for m in (group.members or [])
        ],
    }


def delete_account_group(
    group_id: str,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Delete a group from the Databricks account."""
    a = get_account_client(cloud=cloud, profile=profile)
    a.groups.delete(id=group_id)
    return {"status": "deleted", "group_id": group_id}


def add_group_member(
    group_id: str,
    member_id: str,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Add a user or service principal to a group.

    Uses SCIM PATCH to add a member without replacing existing members.
    """
    from databricks.sdk.service.iam import (
        Group,
        GroupSchema,
        PatchOp,
        PatchSchema,
    )

    a = get_account_client(cloud=cloud, profile=profile)
    a.groups.patch(
        id=group_id,
        operations=[
            PatchOp(
                op=PatchSchema.ADD,
                path="members",
                value=[{"value": member_id}],
            )
        ],
        schemas=[GroupSchema.PATCH_OP],
    )
    return {"status": "added", "group_id": group_id, "member_id": member_id}


def remove_group_member(
    group_id: str,
    member_id: str,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Remove a user or service principal from a group."""
    from databricks.sdk.service.iam import (
        GroupSchema,
        PatchOp,
        PatchSchema,
    )

    a = get_account_client(cloud=cloud, profile=profile)
    a.groups.patch(
        id=group_id,
        operations=[
            PatchOp(
                op=PatchSchema.REMOVE,
                path=f'members[value eq "{member_id}"]',
            )
        ],
        schemas=[GroupSchema.PATCH_OP],
    )
    return {"status": "removed", "group_id": group_id, "member_id": member_id}


# =============================================================================
# Account Identity: Service Principals
# =============================================================================


def list_account_service_principals(
    cloud: Optional[str] = None,
    profile: str = "default",
    filter_str: Optional[str] = None,
    max_results: int = 100,
) -> List[Dict[str, Any]]:
    """List service principals in the Databricks account."""
    a = get_account_client(cloud=cloud, profile=profile)
    kwargs: Dict[str, Any] = {}
    if filter_str:
        kwargs["filter"] = filter_str
    sps = []
    for sp in a.service_principals.list(**kwargs):
        sps.append({
            "id": sp.id,
            "application_id": sp.application_id,
            "display_name": sp.display_name,
            "active": sp.active,
        })
        if len(sps) >= max_results:
            break
    return sps


def create_account_service_principal(
    display_name: str,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Create a service principal in the Databricks account.

    Args:
        display_name: Display name for the SP.
        cloud: Cloud provider.
        profile: Credential profile name.

    Returns:
        Dict with SP info including application_id.
    """
    a = get_account_client(cloud=cloud, profile=profile)
    sp = a.service_principals.create(display_name=display_name, active=True)
    return {
        "id": sp.id,
        "application_id": sp.application_id,
        "display_name": sp.display_name,
        "active": sp.active,
    }


def get_account_service_principal(
    sp_id: str,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Get a service principal by ID."""
    a = get_account_client(cloud=cloud, profile=profile)
    sp = a.service_principals.get(id=sp_id)
    return {
        "id": sp.id,
        "application_id": sp.application_id,
        "display_name": sp.display_name,
        "active": sp.active,
        "groups": [
            {"display": g.display, "value": g.value}
            for g in (sp.groups or [])
        ],
    }


def delete_account_service_principal(
    sp_id: str,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Delete a service principal from the Databricks account."""
    a = get_account_client(cloud=cloud, profile=profile)
    a.service_principals.delete(id=sp_id)
    return {"status": "deleted", "service_principal_id": sp_id}


# =============================================================================
# Workspace Assignments
# =============================================================================


def list_workspace_assignments(
    workspace_id: int,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> List[Dict[str, Any]]:
    """List permission assignments for a workspace."""
    a = get_account_client(cloud=cloud, profile=profile)
    assignments = a.workspace_assignment.list(workspace_id=workspace_id)
    return [
        {
            "principal_id": pa.principal.principal_id,
            "display_name": pa.principal.display_name,
            "user_name": pa.principal.user_name,
            "group_name": pa.principal.group_name,
            "service_principal_name": pa.principal.service_principal_name,
            "permissions": [p.value for p in (pa.permissions or [])],
        }
        for pa in assignments
    ]


def assign_workspace_permissions(
    workspace_id: int,
    principal_id: int,
    permissions: List[str],
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Assign permissions to a principal on a workspace.

    Args:
        workspace_id: Databricks workspace ID (numeric).
        principal_id: User, group, or SP ID to assign.
        permissions: List of permission levels, e.g. ["USER"] or ["ADMIN"].
        cloud: Cloud provider.
        profile: Credential profile name.

    Returns:
        Dict with assignment result.
    """
    from databricks.sdk.service.iam import WorkspacePermission

    a = get_account_client(cloud=cloud, profile=profile)
    perms = [WorkspacePermission(p.upper()) for p in permissions]
    a.workspace_assignment.update(
        workspace_id=workspace_id,
        principal_id=principal_id,
        permissions=perms,
    )
    return {
        "status": "assigned",
        "workspace_id": workspace_id,
        "principal_id": principal_id,
        "permissions": permissions,
    }


def unassign_workspace_permissions(
    workspace_id: int,
    principal_id: int,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Remove a principal's permissions from a workspace."""
    a = get_account_client(cloud=cloud, profile=profile)
    a.workspace_assignment.delete(
        workspace_id=workspace_id,
        principal_id=principal_id,
    )
    return {
        "status": "unassigned",
        "workspace_id": workspace_id,
        "principal_id": principal_id,
    }


# =============================================================================
# Account: Metastore Operations
# =============================================================================


def list_account_metastores(
    cloud: Optional[str] = None,
    profile: str = "default",
) -> List[Dict[str, Any]]:
    """List all metastores in the account."""
    a = get_account_client(cloud=cloud, profile=profile)
    metastores = a.metastores.list()
    return [_obj_to_dict(m) for m in metastores]


def assign_metastore_to_workspace(
    workspace_id: int,
    metastore_id: str,
    default_catalog_name: str = "main",
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Assign a Unity Catalog metastore to a workspace."""
    a = get_account_client(cloud=cloud, profile=profile)
    a.metastore_assignments.create(
        workspace_id=workspace_id,
        metastore_id=metastore_id,
        default_catalog_name=default_catalog_name,
    )
    return {
        "status": "assigned",
        "workspace_id": workspace_id,
        "metastore_id": metastore_id,
        "default_catalog_name": default_catalog_name,
    }


def get_account_metastore(
    metastore_id: str,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Get details of a specific metastore."""
    a = get_account_client(cloud=cloud, profile=profile)
    metastore = a.metastores.get(metastore_id)
    return _obj_to_dict(metastore)


def create_metastore(
    name: str,
    storage_root: str,
    region: Optional[str] = None,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Create a new Unity Catalog metastore."""
    a = get_account_client(cloud=cloud, profile=profile)
    info = CreateAccountsMetastore(
        name=name,
        storage_root=storage_root,
        region=region,
    )
    result = a.metastores.create(metastore_info=info)
    return _obj_to_dict(result)


def create_metastore_data_access(
    metastore_id: str,
    name: str,
    role_arn: str = None,
    access_connector_id: str = None,
    is_default: bool = True,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Create a data access credential for a metastore.

    AWS: pass role_arn (IAM role ARN).
    Azure: pass access_connector_id (Azure Access Connector resource ID).
    Exactly one of role_arn or access_connector_id must be provided.

    NOTE for Azure: This uses the account-level storage_credentials API.
    If the account API returns 303 or fails, use the workspace-level approach:
      1. POST {workspace_url}/api/2.1/unity-catalog/storage-credentials
      2. databricks metastores update <id> --json '{"storage_root_credential_id":"<uuid>"}'
    """
    if not role_arn and not access_connector_id:
        raise ValueError("Provide either role_arn (AWS) or access_connector_id (Azure)")

    a = get_account_client(cloud=cloud, profile=profile)

    if access_connector_id:
        cred_info = CreateAccountsStorageCredential(
            name=name,
            azure_managed_identity=AzureManagedIdentityRequest(
                access_connector_id=access_connector_id,
            ),
        )
    else:
        cred_info = CreateAccountsStorageCredential(
            name=name,
            aws_iam_role=AwsIamRoleRequest(role_arn=role_arn),
        )

    result = a.storage_credentials.create(
        metastore_id=metastore_id,
        credential_info=cred_info,
    )
    if is_default:
        # Extract credential ID from result and set as metastore root credential
        cred_dict = _obj_to_dict(result)
        cred_id = cred_dict.get("credential_info", {}).get("id") or cred_dict.get("id")
        if cred_id:
            a.metastores.update(
                metastore_id,
                metastore_info=UpdateAccountsMetastore(
                    storage_root_credential_id=cred_id,
                ),
            )
    return _obj_to_dict(result)


def delete_metastore(
    metastore_id: str,
    force: bool = False,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Delete a metastore. Use force=True to unassign from all workspaces first."""
    a = get_account_client(cloud=cloud, profile=profile)
    a.metastores.delete(metastore_id, force=force)
    return {"status": "deleted", "metastore_id": metastore_id}


def update_metastore(
    metastore_id: str,
    new_owner: Optional[str] = None,
    cloud: Optional[str] = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """Update metastore properties (currently supports owner transfer)."""
    a = get_account_client(cloud=cloud, profile=profile)
    info = UpdateAccountsMetastore()
    if new_owner is not None:
        info.owner = new_owner
    result = a.metastores.update(metastore_id, metastore_info=info)
    return _obj_to_dict(result)


# =============================================================================
# Workspace Configuration: IP Access Lists
# =============================================================================


def list_ip_access_lists() -> List[Dict[str, Any]]:
    """List IP access lists for the workspace."""
    w = get_workspace_client()
    result = w.ip_access_lists.list()
    return [_obj_to_dict(item) for item in result]


def create_ip_access_list(
    label: str,
    list_type: str,
    ip_addresses: List[str],
) -> Dict[str, Any]:
    """Create an IP access list.

    Args:
        label: Name of the IP access list.
        list_type: "ALLOW" or "BLOCK".
        ip_addresses: List of IP addresses or CIDR ranges.

    Returns:
        Dict with created IP access list info.
    """
    from databricks.sdk.service.settings import IpAccessListType

    w = get_workspace_client()
    lt = IpAccessListType(list_type.upper())
    result = w.ip_access_lists.create(
        label=label,
        list_type=lt,
        ip_addresses=ip_addresses,
    )
    return _obj_to_dict(result)


def delete_ip_access_list(ip_access_list_id: str) -> Dict[str, Any]:
    """Delete an IP access list."""
    w = get_workspace_client()
    w.ip_access_lists.delete(ip_access_list_id=ip_access_list_id)
    return {"status": "deleted", "ip_access_list_id": ip_access_list_id}


# =============================================================================
# Workspace Configuration: Secret Scopes
# =============================================================================


def list_secret_scopes() -> List[Dict[str, Any]]:
    """List secret scopes in the workspace."""
    w = get_workspace_client()
    scopes = w.secrets.list_scopes()
    return [_obj_to_dict(s) for s in scopes]


def create_secret_scope(
    scope: str,
    initial_manage_principal: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a Databricks-backed secret scope.

    Args:
        scope: Name of the secret scope.
        initial_manage_principal: Principal that can manage the scope
                                  (default: creator only). Use "users"
                                  to allow all workspace users.
    """
    w = get_workspace_client()
    from databricks.sdk.service.workspace import CreateScope

    kwargs: Dict[str, Any] = {"scope": scope}
    if initial_manage_principal is not None:
        kwargs["initial_manage_principal"] = initial_manage_principal
    w.secrets.create_scope(**kwargs)
    return {"status": "created", "scope": scope}


def put_secret(
    scope: str,
    key: str,
    string_value: str,
) -> Dict[str, Any]:
    """Store a secret in a scope.

    Args:
        scope: Secret scope name.
        key: Secret key name.
        string_value: The secret value (stored encrypted).
    """
    w = get_workspace_client()
    w.secrets.put_secret(scope=scope, key=key, string_value=string_value)
    return {"status": "stored", "scope": scope, "key": key}


def list_secrets(scope: str) -> List[Dict[str, Any]]:
    """List secrets in a scope (returns metadata only, not values)."""
    w = get_workspace_client()
    secrets = w.secrets.list_secrets(scope=scope)
    return [{"key": s.key, "last_updated_timestamp": s.last_updated_timestamp} for s in secrets]


def delete_secret(scope: str, key: str) -> Dict[str, Any]:
    """Delete a secret from a scope."""
    w = get_workspace_client()
    w.secrets.delete_secret(scope=scope, key=key)
    return {"status": "deleted", "scope": scope, "key": key}


def delete_secret_scope(scope: str) -> Dict[str, Any]:
    """Delete a secret scope and all its secrets."""
    w = get_workspace_client()
    w.secrets.delete_scope(scope=scope)
    return {"status": "deleted", "scope": scope}


# =============================================================================
# Workspace Configuration: Cluster Policies
# =============================================================================


def list_cluster_policies() -> List[Dict[str, Any]]:
    """List cluster policies in the workspace."""
    w = get_workspace_client()
    policies = w.cluster_policies.list()
    return [
        {
            "policy_id": p.policy_id,
            "name": p.name,
            "description": p.description,
            "is_default": p.is_default,
            "creator_user_name": p.creator_user_name,
        }
        for p in policies
    ]


def create_cluster_policy(
    name: str,
    definition: Dict[str, Any],
    description: Optional[str] = None,
    max_clusters_per_user: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a cluster policy.

    Args:
        name: Policy name.
        definition: Policy definition as a dict (will be JSON-encoded).
                    Example: {"spark_version": {"type": "fixed", "value": "13.3.x-scala2.12"}}
        description: Optional description.
        max_clusters_per_user: Max clusters a user can create with this policy.

    Returns:
        Dict with created policy info.
    """
    w = get_workspace_client()
    kwargs: Dict[str, Any] = {
        "name": name,
        "definition": json.dumps(definition),
    }
    if description is not None:
        kwargs["description"] = description
    if max_clusters_per_user is not None:
        kwargs["max_clusters_per_user"] = max_clusters_per_user
    policy = w.cluster_policies.create(**kwargs)
    return {
        "policy_id": policy.policy_id,
        "name": policy.name,
        "status": "created",
    }


def get_cluster_policy(policy_id: str) -> Dict[str, Any]:
    """Get a cluster policy by ID."""
    w = get_workspace_client()
    policy = w.cluster_policies.get(policy_id=policy_id)
    return _obj_to_dict(policy)


def delete_cluster_policy(policy_id: str) -> Dict[str, Any]:
    """Delete a cluster policy."""
    w = get_workspace_client()
    w.cluster_policies.delete(policy_id=policy_id)
    return {"status": "deleted", "policy_id": policy_id}


# =============================================================================
# Workspace Configuration: SQL Warehouses
# =============================================================================


def list_sql_warehouses() -> List[Dict[str, Any]]:
    """List SQL warehouses in the workspace."""
    w = get_workspace_client()
    warehouses = w.warehouses.list()
    return [
        {
            "id": wh.id,
            "name": wh.name,
            "cluster_size": wh.cluster_size,
            "state": wh.state.value if wh.state else None,
            "num_clusters": wh.num_clusters,
            "auto_stop_mins": wh.auto_stop_mins,
            "warehouse_type": wh.warehouse_type.value if wh.warehouse_type else None,
            "creator_name": wh.creator_name,
        }
        for wh in warehouses
    ]


def create_sql_warehouse(
    name: str,
    cluster_size: str = "2X-Small",
    auto_stop_mins: int = 15,
    min_num_clusters: int = 1,
    max_num_clusters: int = 1,
    warehouse_type: str = "PRO",
    enable_serverless: bool = False,
) -> Dict[str, Any]:
    """Create a SQL warehouse.

    Args:
        name: Warehouse name.
        cluster_size: Size (2X-Small, X-Small, Small, Medium, Large, etc.).
        auto_stop_mins: Minutes before auto-stop (0 = no auto-stop).
        min_num_clusters: Min clusters for scaling.
        max_num_clusters: Max clusters for scaling.
        warehouse_type: "PRO", "CLASSIC", or "TYPE_UNSPECIFIED".
        enable_serverless: Whether to use serverless compute.

    Returns:
        Dict with created warehouse info.
    """
    from databricks.sdk.service.sql import (
        CreateWarehouseRequestWarehouseType,
        EndpointConfPair,
    )

    w = get_workspace_client()
    wh_type = CreateWarehouseRequestWarehouseType(warehouse_type.upper())
    result = w.warehouses.create_and_wait(
        name=name,
        cluster_size=cluster_size,
        auto_stop_mins=auto_stop_mins,
        min_num_clusters=min_num_clusters,
        max_num_clusters=max_num_clusters,
        warehouse_type=wh_type,
        enable_serverless_compute=enable_serverless,
    )
    return {
        "id": result.id,
        "name": result.name,
        "state": result.state.value if result.state else None,
        "status": "created",
    }


def get_sql_warehouse(warehouse_id: str) -> Dict[str, Any]:
    """Get a SQL warehouse by ID."""
    w = get_workspace_client()
    wh = w.warehouses.get(id=warehouse_id)
    return _obj_to_dict(wh)


def delete_sql_warehouse(warehouse_id: str) -> Dict[str, Any]:
    """Delete a SQL warehouse."""
    w = get_workspace_client()
    w.warehouses.delete(id=warehouse_id)
    return {"status": "deleted", "warehouse_id": warehouse_id}


def start_sql_warehouse(warehouse_id: str) -> Dict[str, Any]:
    """Start a stopped SQL warehouse."""
    w = get_workspace_client()
    w.warehouses.start(id=warehouse_id)
    return {"status": "starting", "warehouse_id": warehouse_id}


def stop_sql_warehouse(warehouse_id: str) -> Dict[str, Any]:
    """Stop a running SQL warehouse."""
    w = get_workspace_client()
    w.warehouses.stop(id=warehouse_id)
    return {"status": "stopping", "warehouse_id": warehouse_id}


# =============================================================================
# Workspace Configuration: Token Management
# =============================================================================


def list_tokens() -> List[Dict[str, Any]]:
    """List personal access tokens for the current user."""
    w = get_workspace_client()
    tokens = w.tokens.list()
    return [
        {
            "token_id": t.token_id,
            "comment": t.comment,
            "creation_time": t.creation_time,
            "expiry_time": t.expiry_time,
        }
        for t in tokens
    ]


def create_token(
    comment: str = "Created by databricks-platform-kit",
    lifetime_seconds: int = 7776000,
) -> Dict[str, Any]:
    """Create a personal access token.

    Args:
        comment: Description of the token's purpose.
        lifetime_seconds: Token lifetime in seconds (default: 90 days).

    Returns:
        Dict with token_value (only shown once) and token_info.
    """
    w = get_workspace_client()
    result = w.tokens.create(
        comment=comment,
        lifetime_seconds=lifetime_seconds,
    )
    return {
        "token_value": result.token_value,
        "token_info": {
            "token_id": result.token_info.token_id if result.token_info else None,
            "comment": comment,
            "expiry_time": result.token_info.expiry_time if result.token_info else None,
        },
        "warning": "Save the token_value now — it cannot be retrieved later.",
    }


def revoke_token(token_id: str) -> Dict[str, Any]:
    """Revoke (delete) a personal access token."""
    w = get_workspace_client()
    w.tokens.delete(token_id=token_id)
    return {"status": "revoked", "token_id": token_id}


# =============================================================================
# Workspace Configuration: Workspace Settings
# =============================================================================


def get_workspace_config(keys: List[str]) -> Dict[str, str]:
    """Get workspace configuration values.

    Args:
        keys: List of config keys, e.g. ["enableTokensConfig", "maxTokenLifetimeDays"].

    Returns:
        Dict mapping keys to their current values.
    """
    w = get_workspace_client()
    return dict(w.workspace_conf.get_status(keys=",".join(keys)))


def set_workspace_config(config: Dict[str, str]) -> Dict[str, Any]:
    """Set workspace configuration values.

    Args:
        config: Dict of key-value pairs to set.
                Common keys: enableTokensConfig, maxTokenLifetimeDays,
                enableIpAccessLists, enableResultsDownloading.

    Returns:
        Status dict.
    """
    w = get_workspace_client()
    w.workspace_conf.set_status(config)
    return {"status": "updated", "keys": list(config.keys())}

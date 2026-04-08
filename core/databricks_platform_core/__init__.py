"""
Databricks Platform Core - Workspace provisioning and account management.

This module provides functions for:
- Provisioning Databricks workspaces using bundled Terraform templates
- Managing account-level identity (users, groups, service principals)
- Configuring workspace settings (IP access lists, secrets, policies, warehouses)

Supports Azure, AWS, and GCP.

Core Operations:
- Terraform: run_terraform, terraform_destroy, list_runs
- Credentials: store/retrieve cloud credentials securely
- Templates: list and locate bundled Terraform templates
- Account API: manage users, groups, SPs, workspace assignments
- Workspace Config: IP access lists, secrets, cluster policies, SQL warehouses

Example Usage:
    >>> from databricks_platform_core import (
    ...     list_templates, run_terraform, store_azure_credentials,
    ...     get_account_client, list_account_users, create_account_group,
    ... )
"""

from .terraform_runner import (
    run_terraform,
    terraform_destroy,
    list_runs,
    get_run_outputs,
    TerraformError,
)

from .credentials import (
    store_azure_credentials,
    get_azure_credentials,
    store_databricks_account_credentials,
    get_databricks_account_credentials,
    store_gcp_credentials,
    get_gcp_credentials,
    list_credential_profiles,
    delete_credentials,
)

from .templates import (
    list_templates,
    get_template_path,
    get_templates_dir,
)

from .account_api import (
    # Account client
    get_account_client,
    # Users
    list_account_users,
    create_account_user,
    get_account_user,
    delete_account_user,
    # Groups
    list_account_groups,
    create_account_group,
    get_account_group,
    delete_account_group,
    add_group_member,
    remove_group_member,
    # Service principals
    list_account_service_principals,
    create_account_service_principal,
    get_account_service_principal,
    delete_account_service_principal,
    # Workspace assignments
    list_workspace_assignments,
    assign_workspace_permissions,
    unassign_workspace_permissions,
    # Metastore operations
    list_account_metastores,
    assign_metastore_to_workspace,
    get_account_metastore,
    create_metastore,
    create_metastore_data_access,
    delete_metastore,
    update_metastore,
    # IP access lists
    list_ip_access_lists,
    create_ip_access_list,
    delete_ip_access_list,
    # Secret scopes
    list_secret_scopes,
    create_secret_scope,
    put_secret,
    list_secrets,
    delete_secret,
    delete_secret_scope,
    # Cluster policies
    list_cluster_policies,
    create_cluster_policy,
    get_cluster_policy,
    delete_cluster_policy,
    # SQL warehouses
    list_sql_warehouses,
    create_sql_warehouse,
    get_sql_warehouse,
    delete_sql_warehouse,
    start_sql_warehouse,
    stop_sql_warehouse,
    # Token management
    list_tokens,
    create_token,
    revoke_token,
    # Workspace config
    get_workspace_config,
    set_workspace_config,
)

__all__ = [
    # Terraform runner
    "run_terraform",
    "terraform_destroy",
    "list_runs",
    "get_run_outputs",
    "TerraformError",
    # Credentials
    "store_azure_credentials",
    "get_azure_credentials",
    "store_databricks_account_credentials",
    "get_databricks_account_credentials",
    "store_gcp_credentials",
    "get_gcp_credentials",
    "list_credential_profiles",
    "delete_credentials",
    # Templates
    "list_templates",
    "get_template_path",
    "get_templates_dir",
    # Account client
    "get_account_client",
    # Account identity - users
    "list_account_users",
    "create_account_user",
    "get_account_user",
    "delete_account_user",
    # Account identity - groups
    "list_account_groups",
    "create_account_group",
    "get_account_group",
    "delete_account_group",
    "add_group_member",
    "remove_group_member",
    # Account identity - service principals
    "list_account_service_principals",
    "create_account_service_principal",
    "get_account_service_principal",
    "delete_account_service_principal",
    # Workspace assignments
    "list_workspace_assignments",
    "assign_workspace_permissions",
    "unassign_workspace_permissions",
    # Account metastore operations
    "list_account_metastores",
    "assign_metastore_to_workspace",
    "get_account_metastore",
    "create_metastore",
    "create_metastore_data_access",
    "delete_metastore",
    "update_metastore",
    # IP access lists
    "list_ip_access_lists",
    "create_ip_access_list",
    "delete_ip_access_list",
    # Secret scopes
    "list_secret_scopes",
    "create_secret_scope",
    "put_secret",
    "list_secrets",
    "delete_secret",
    "delete_secret_scope",
    # Cluster policies
    "list_cluster_policies",
    "create_cluster_policy",
    "get_cluster_policy",
    "delete_cluster_policy",
    # SQL warehouses
    "list_sql_warehouses",
    "create_sql_warehouse",
    "get_sql_warehouse",
    "delete_sql_warehouse",
    "start_sql_warehouse",
    "stop_sql_warehouse",
    # Token management
    "list_tokens",
    "create_token",
    "revoke_token",
    # Workspace config
    "get_workspace_config",
    "set_workspace_config",
]

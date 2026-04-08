"""
Provisioning MCP Tools

Databricks workspace provisioning and account management.
6 tools covering: credential management, template discovery,
workspace provisioning, run management, account identity, and workspace config.
"""

import logging
from typing import Any, Dict, List

from databricks_platform_core import (
    store_azure_credentials as _store_azure_credentials,
    get_azure_credentials as _get_azure_credentials,
    store_databricks_account_credentials as _store_databricks_account_credentials,
    get_databricks_account_credentials as _get_databricks_account_credentials,
    store_gcp_credentials as _store_gcp_credentials,
    get_gcp_credentials as _get_gcp_credentials,
    list_credential_profiles as _list_credential_profiles,
    delete_credentials as _delete_credentials,
    list_templates as _list_templates,
    run_terraform as _run_terraform,
    terraform_destroy as _terraform_destroy,
    list_runs as _list_runs,
    get_run_outputs as _get_run_outputs,
    TerraformError,
    # Account identity
    list_account_users as _list_account_users,
    create_account_user as _create_account_user,
    get_account_user as _get_account_user,
    delete_account_user as _delete_account_user,
    list_account_groups as _list_account_groups,
    create_account_group as _create_account_group,
    get_account_group as _get_account_group,
    delete_account_group as _delete_account_group,
    add_group_member as _add_group_member,
    remove_group_member as _remove_group_member,
    list_account_service_principals as _list_account_service_principals,
    create_account_service_principal as _create_account_service_principal,
    get_account_service_principal as _get_account_service_principal,
    delete_account_service_principal as _delete_account_service_principal,
    list_workspace_assignments as _list_workspace_assignments,
    assign_workspace_permissions as _assign_workspace_permissions,
    unassign_workspace_permissions as _unassign_workspace_permissions,
    list_account_metastores as _list_account_metastores,
    assign_metastore_to_workspace as _assign_metastore_to_workspace,
    get_account_metastore as _get_account_metastore,
    create_metastore as _create_metastore,
    create_metastore_data_access as _create_metastore_data_access,
    delete_metastore as _delete_metastore,
    update_metastore as _update_metastore,
    # Workspace config
    list_ip_access_lists as _list_ip_access_lists,
    create_ip_access_list as _create_ip_access_list,
    delete_ip_access_list as _delete_ip_access_list,
    list_secret_scopes as _list_secret_scopes,
    create_secret_scope as _create_secret_scope,
    put_secret as _put_secret,
    list_secrets as _list_secrets,
    delete_secret as _delete_secret,
    delete_secret_scope as _delete_secret_scope,
    list_cluster_policies as _list_cluster_policies,
    create_cluster_policy as _create_cluster_policy,
    get_cluster_policy as _get_cluster_policy,
    delete_cluster_policy as _delete_cluster_policy,
    list_sql_warehouses as _list_sql_warehouses,
    create_sql_warehouse as _create_sql_warehouse,
    get_sql_warehouse as _get_sql_warehouse,
    delete_sql_warehouse as _delete_sql_warehouse,
    start_sql_warehouse as _start_sql_warehouse,
    stop_sql_warehouse as _stop_sql_warehouse,
    list_tokens as _list_tokens,
    create_token as _create_token,
    revoke_token as _revoke_token,
    get_workspace_config as _get_workspace_config,
    set_workspace_config as _set_workspace_config,
)

logger = logging.getLogger(__name__)

from ..server import mcp


# =============================================================================
# Tool 1: manage_credentials
# =============================================================================


@mcp.tool
def manage_credentials(
    action: str,
    subscription_id: str = None,
    tenant_id: str = None,
    client_id: str = None,
    client_secret: str = None,
    account_id: str = None,
    token: str = None,
    google_project: str = None,
    google_service_account: str = None,
    google_region: str = None,
    profile: str = "default",
) -> Dict[str, Any]:
    """
    Manage cloud credentials for Terraform-based workspace provisioning.

    Credentials are stored securely in the macOS Keychain — never written to disk
    in plaintext. On non-macOS platforms, environment variables are used as fallback.

    IMPORTANT: Always call this tool to store credentials BEFORE calling
    provision_workspace. The user must provide their cloud and Databricks account
    credentials.

    Actions:
    - store_azure: Store Azure Service Principal credentials (requires
      subscription_id, tenant_id, client_id, client_secret).
    - store_databricks_account: Store Databricks account-level credentials.
      Supports two auth modes:
        OAuth M2M (recommended): account_id + client_id + client_secret
        PAT token (legacy): account_id + token
    - store_gcp: Store GCP credentials (requires google_project,
      google_service_account; optional google_region).
    - get_azure: Retrieve stored Azure credentials for a profile.
    - get_databricks_account: Retrieve stored Databricks account credentials.
    - get_gcp: Retrieve stored GCP credentials for a profile.
    - list: List all stored credential profiles.
    - delete: Delete all credentials for a profile.

    Args:
        action: "store_azure", "store_databricks_account", "store_gcp",
                "get_azure", "get_databricks_account", "get_gcp", "list", or "delete"
        subscription_id: Azure subscription ID (for store_azure)
        tenant_id: Azure AD tenant ID (for store_azure)
        client_id: Azure SP client ID (for store_azure) or Databricks SP
                   application ID (for store_databricks_account OAuth M2M)
        client_secret: Azure SP client secret (for store_azure) or Databricks SP
                       secret (for store_databricks_account OAuth M2M)
        account_id: Databricks account ID (for store_databricks_account)
        token: Databricks account API token (for store_databricks_account, legacy)
        google_project: GCP project ID (for store_gcp)
        google_service_account: GCP service account email (for store_gcp)
        google_region: GCP region, e.g. "us-central1" (for store_gcp, optional)
        profile: Credential profile name (default: "default"). Use different
                 profiles to manage multiple cloud accounts.

    Returns:
        Dictionary with action result. For store actions, confirms storage
        in Keychain. For get actions, returns credential values. For list,
        returns profile names.
    """
    act = action.lower()

    if act == "store_azure":
        if not all([subscription_id, tenant_id, client_id, client_secret]):
            return {
                "error": "Missing required fields for store_azure",
                "hint": "Provide subscription_id, tenant_id, client_id, and client_secret. "
                        "Create a Service Principal with: "
                        "az ad sp create-for-rbac --name 'databricks-provisioner' "
                        "--role Contributor --scopes /subscriptions/<subscription_id>",
            }
        return _store_azure_credentials(
            subscription_id=subscription_id,
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            profile=profile,
        )

    elif act == "store_databricks_account":
        if not account_id:
            return {
                "error": "Missing account_id for store_databricks_account",
                "hint": "Find your account ID at "
                        "https://accounts.azuredatabricks.net (Azure), "
                        "https://accounts.cloud.databricks.com (AWS), or "
                        "https://accounts.gcp.databricks.com (GCP).",
            }
        # Support both OAuth M2M (client_id + client_secret) and PAT (token)
        if not client_id and not token:
            return {
                "error": "Provide either client_id+client_secret (OAuth M2M, recommended) "
                         "or token (PAT, legacy)",
                "hint": "For OAuth M2M, create a service principal in your Databricks "
                        "account console and provide its client_id and client_secret. "
                        "For PAT, generate a token from Account Settings > API tokens.",
            }
        return _store_databricks_account_credentials(
            account_id=account_id,
            client_id=client_id,
            client_secret=client_secret,
            token=token,
            profile=profile,
        )

    elif act == "store_gcp":
        if not all([google_project, google_service_account]):
            return {
                "error": "Missing required fields for store_gcp",
                "hint": "Provide google_project and google_service_account. "
                        "The service account must have appropriate IAM roles on the project.",
            }
        return _store_gcp_credentials(
            google_project=google_project,
            google_service_account=google_service_account,
            google_region=google_region or "us-central1",
            profile=profile,
        )

    elif act == "get_azure":
        return _get_azure_credentials(profile=profile)

    elif act == "get_databricks_account":
        return _get_databricks_account_credentials(profile=profile)

    elif act == "get_gcp":
        return _get_gcp_credentials(profile=profile)

    elif act == "list":
        profiles = _list_credential_profiles()
        return {"profiles": profiles, "count": len(profiles)}

    elif act == "delete":
        return _delete_credentials(profile=profile)

    else:
        return {
            "error": f"Unknown action: {action}",
            "hint": "Valid actions: store_azure, store_databricks_account, store_gcp, "
                    "get_azure, get_databricks_account, get_gcp, list, delete",
        }


# =============================================================================
# Tool 2: list_terraform_templates
# =============================================================================


@mcp.tool
def list_terraform_templates() -> List[Dict[str, Any]]:
    """
    List all available Terraform templates for workspace provisioning.

    ALWAYS call this tool first when a user asks to create or provision a
    Databricks workspace. It returns the list of bundled templates with their
    required variables, so you know exactly what to ask the user for.

    Each template includes:
    - name: Template identifier (pass this to provision_workspace)
    - cloud: "azure", "aws", or "gcp"
    - description: What the template provisions
    - required_vars: Variables that MUST be provided
    - optional_vars: Variables with sensible defaults
    - outputs: What values are returned after provisioning

    Available templates (11 total):

    Azure (5 templates):
    - azure-workspace-basic: Simplest — RG + ADLS Gen2 + workspace with managed VNet
    - azure-workspace-vnet-injection: Custom VNet with public/private subnets, NSG, Secure Cluster Connectivity
    - azure-workspace-privatelink: Full private link — VNet injection + 2 private endpoints + private DNS (no public access)
    - azure-unity-catalog: For existing workspaces — adds metastore, access connector, catalog, schemas
    - azure-workspace-full: Complete — VNet injection + Unity Catalog in one deployment

    AWS (3 templates):
    - aws-workspace-basic: VPC + IAM cross-account role + S3 + MWS workspace
    - aws-unity-catalog: For existing workspaces — adds metastore, IAM role, catalog, schemas
    - aws-workspace-full: Complete — workspace + Unity Catalog + admin user

    GCP (3 templates):
    - gcp-workspace-basic: GCS bucket + workspace with GCP-managed VPC
    - gcp-workspace-byovpc: Custom VPC + subnet + Cloud NAT + MWS workspace
    - gcp-unity-catalog: For existing workspaces — adds metastore, GCS bucket, catalog, schemas

    Returns:
        List of template metadata dictionaries.
    """
    try:
        return _list_templates()
    except FileNotFoundError as e:
        return [{"error": str(e)}]


# =============================================================================
# Tool 3: provision_workspace
# =============================================================================


@mcp.tool
def provision_workspace(
    template_name: str,
    workspace_name: str,
    variables: Dict[str, Any] = None,
    credentials_profile: str = "default",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Provision a Databricks workspace using Terraform.

    This is the main provisioning tool. It runs Terraform locally to create
    cloud infrastructure and a Databricks workspace end-to-end.

    IMPORTANT WORKFLOW — always follow these steps in order:
    1. Call list_terraform_templates() to see available templates
    2. Call manage_credentials(action="list") to check if credentials are stored
    3. If no credentials, store them first with the appropriate manage_credentials action
    4. Do a DRY RUN first: provision_workspace(..., dry_run=True)
    5. Show the plan to the user and get explicit confirmation
    6. Only then call provision_workspace(..., dry_run=False)

    NEVER skip the dry_run step. ALWAYS show the plan and get user approval
    before applying infrastructure changes.

    Prerequisites:
    - Terraform must be installed (brew install terraform)
    - For Azure: either az login (recommended) or SP creds via manage_credentials
    - For AWS: Databricks account service principal (OAuth M2M)
    - For GCP: GCP service account with appropriate IAM roles

    The tool automatically merges stored credentials into the Terraform
    variables, so the user does NOT need to pass secrets explicitly. Only
    pass non-secret variables (workspace_name, location/region, tags, etc.).

    Template-specific variables (beyond auto-injected credentials):

    AZURE TEMPLATES (all support az login — SP creds optional):
      azure-workspace-basic:
        Required: subscription_id, tenant_id (auto-injected if stored)
        Optional: location (default: "westeurope"), resource_group_name, tags

      azure-workspace-vnet-injection:
        Required: subscription_id, tenant_id
        Optional: location, resource_group_name, cidr (default: "10.179.0.0/20"),
                  no_public_ip (default: true), tags

      azure-workspace-privatelink:
        Required: subscription_id, tenant_id
        Optional: location, resource_group_name, cidr, public_network_access_enabled
                  (default: false), tags

      azure-unity-catalog (for existing workspace):
        Required: workspace_url, workspace_id, location, resource_group_name, metastore_name,
                  grant_principal (human admin email)
        Optional: catalog_name (default: "main"), create_schemas (default: true), tags

      azure-workspace-full:
        Required: metastore_name
        Optional: location, resource_group_name, cidr, no_public_ip,
                  catalog_name (default: "dev", avoid "main"), create_metastore, create_schemas, tags

    AWS TEMPLATES:
      aws-workspace-basic:
        Optional: region (default: "us-east-1"), vpc_cidr, public_subnets_cidr,
                  private_subnets_cidr, tags

      aws-unity-catalog (for existing workspace):
        Required: aws_account_id, workspace_url, workspace_ids (list), metastore_name, metastore_owner
        Optional: region, catalog_name (default: "dev", avoid "main"), tags

      aws-workspace-full:
        Required: metastore_name, admin_user (email)
        Optional: region, vpc_cidr, public_subnets_cidr, private_subnets_cidr,
                  catalog_name (default: "dev", avoid "main"), create_metastore, create_catalog, tags

    GCP TEMPLATES:
      gcp-workspace-basic:
        Required: prefix
        Optional: google_region (default: "us-central1"), delegate_from, tags

      gcp-workspace-byovpc:
        Required: prefix
        Optional: google_region, delegate_from, subnet_ip_cidr_range,
                  pod_ip_cidr_range, svc_ip_cidr_range, tags

      gcp-unity-catalog (for existing workspace):
        Required: workspace_id, workspace_url, metastore_name
        Optional: catalog_name, tags

    Args:
        template_name: Template to use (from list_terraform_templates)
        workspace_name: Name for the new workspace (or label for UC-only templates)
        variables: Template-specific variables (region, tags, etc.).
                   Do NOT include credentials — they are injected automatically.
        credentials_profile: Which stored credential profile to use (default: "default")
        dry_run: If True, runs terraform plan only (shows what would be created).
                 ALWAYS do a dry run first.

    Returns:
        Dictionary with:
        - status: "success", "plan_complete", "failed"
        - log: Full Terraform output log
        - outputs: Terraform outputs (workspace_url, workspace_id, etc.)
        - run_id: Unique run identifier (use for destroy/status)
        - run_dir: Local directory with Terraform state
    """
    if variables is None:
        variables = {}

    # Inject workspace_name only for templates that declare it
    # UC-only templates (aws-unity-catalog, azure-unity-catalog, gcp-unity-catalog) don't have this variable
    _uc_only_templates = {"aws-unity-catalog", "azure-unity-catalog", "gcp-unity-catalog"}
    if template_name not in _uc_only_templates:
        variables["workspace_name"] = workspace_name

    # Determine cloud from template name and inject credentials
    if template_name.startswith("azure"):
        azure_creds = _get_azure_credentials(profile=credentials_profile)
        if "error" in azure_creds:
            # Azure SP creds are optional — all Azure templates support az login.
            # Only subscription_id and tenant_id are truly required; the user can
            # pass them via the variables dict or they'll be prompted by Terraform.
            pass
        else:
            variables.update(azure_creds)

        # Templates that need account-level operations (UC/metastore) require
        # databricks_account_id. Simple workspace templates don't.
        _needs_account_id = {
            "azure-workspace-full", "azure-unity-catalog",
        }
        if template_name in _needs_account_id:
            db_creds = _get_databricks_account_credentials(profile=credentials_profile)
            if "error" in db_creds:
                return {
                    "error": db_creds["error"],
                    "hint": "Store Databricks account credentials: "
                            "manage_credentials(action='store_databricks_account', ...)",
                }
            variables["databricks_account_id"] = db_creds["account_id"]

    elif template_name.startswith("aws"):
        db_creds = _get_databricks_account_credentials(profile=credentials_profile)
        if "error" in db_creds:
            return {
                "error": db_creds["error"],
                "hint": "Store Databricks account credentials: "
                        "manage_credentials(action='store_databricks_account', ...)",
            }
        variables["databricks_account_id"] = db_creds["account_id"]
        # AWS templates use OAuth M2M (client_id/client_secret)
        if db_creds.get("auth_type") == "oauth-m2m":
            variables["databricks_client_id"] = db_creds["client_id"]
            variables["databricks_client_secret"] = db_creds["client_secret"]
        elif db_creds.get("token"):
            # Legacy PAT fallback
            variables["databricks_client_id"] = ""
            variables["databricks_client_secret"] = db_creds["token"]

    elif template_name.startswith("gcp"):
        gcp_creds = _get_gcp_credentials(profile=credentials_profile)
        if "error" in gcp_creds:
            return {
                "error": gcp_creds["error"],
                "hint": "Store GCP credentials first: "
                        "manage_credentials(action='store_gcp', ...)",
            }
        variables["google_project"] = gcp_creds["google_project"]
        variables["google_service_account"] = gcp_creds["google_service_account"]
        if "google_region" in gcp_creds:
            variables.setdefault("google_region", gcp_creds["google_region"])

        db_creds = _get_databricks_account_credentials(profile=credentials_profile)
        if "error" in db_creds:
            return {
                "error": db_creds["error"],
                "hint": "Store Databricks account credentials: "
                        "manage_credentials(action='store_databricks_account', ...)",
            }
        variables["databricks_account_id"] = db_creds["account_id"]

    try:
        result = _run_terraform(
            template_name=template_name,
            variables=variables,
            dry_run=dry_run,
        )
        return result
    except TerraformError as e:
        return {
            "error": str(e),
            "log": e.log,
            "hint": _get_error_hint(str(e)),
        }


def _get_error_hint(error_msg: str) -> str:
    """Return a helpful hint based on common Terraform error messages."""
    lower = error_msg.lower()
    if "insufficient" in lower or "authorization" in lower or "permission" in lower:
        return (
            "The Service Principal needs Contributor and User Access Administrator "
            "roles on the Azure subscription. For AWS, check IAM permissions. "
            "For GCP, check service account IAM roles."
        )
    if "already exists" in lower or "conflict" in lower or "taken" in lower:
        return (
            "The workspace or resource name may already be in use. "
            "Try a different workspace_name."
        )
    if "more than one authorization method" in lower:
        return (
            "Auth conflict: DATABRICKS_* env vars conflict with Terraform provider config. "
            "The runner now strips these automatically, but if you see this, check that "
            "~/.databrickscfg DEFAULT profile doesn't have OAuth M2M creds that clash "
            "with az-cli auth. Templates use explicit auth_type to avoid this."
        )
    if "m2m authentication" in lower or "cannot get access token" in lower:
        return (
            "The Databricks Terraform provider is falling back to the DEFAULT "
            ".databrickscfg profile which has OAuth M2M creds. The CLI refuses to "
            "generate tokens from M2M. Fix: ensure the template's accounts provider "
            "has auth_type = 'azure-cli' when no SP creds are provided."
        )
    if "catalog" in lower and "already exists" in lower:
        return (
            "A catalog named 'main' is auto-created when a metastore is assigned. "
            "Use catalog_name='dev' or another non-conflicting name."
        )
    if "concurrentupdateerror" in lower or "updated by another process" in lower:
        return (
            "Two resources tried to update the workspace simultaneously. "
            "For private endpoints, they must be serialized with depends_on. "
            "If partially created, use 'terraform import' to bring it into state."
        )
    if "terraform" in lower and "not found" in lower:
        return "Install Terraform: brew install terraform (macOS)"
    if "quota" in lower:
        return (
            "Cloud resource quota exceeded. Request a quota increase in your "
            "cloud provider's console."
        )
    if "owner tag" in lower or "required tag" in lower:
        return (
            "Azure policy requires tags on resources. Pass "
            "tags={\"owner\": \"you@company.com\"} in the variables."
        )
    if "network_check_control_plane_failure" in lower:
        return (
            "Classic cluster can't reach the Databricks control plane. "
            "Check: (1) CIDR doesn't overlap with other workspaces in the same "
            "account/region, (2) NSG allows outbound to AzureDatabricks service tag "
            "on port 443, (3) VNet has proper routing."
        )
    if "dns" in lower and ("already exists" in lower or "conflict" in lower):
        return (
            "The private DNS zone 'privatelink.azuredatabricks.net' already exists "
            "in this resource group. Deploy each private link workspace to its own "
            "resource group to avoid DNS zone name collisions."
        )
    if "connection attempt failed" in lower:
        return (
            "Serverless can't reach the external database. If using NCC Private Link: "
            "(1) Verify NCC PE rule domain matches UC connection host EXACTLY, "
            "(2) Use a CUSTOM domain (e.g., mydb.internal.com), NOT Azure public DNS "
            "names like *.cloudapp.azure.com — public DNS names bypass NCC interception, "
            "(3) Check LB health probes are healthy (NSG must allow AzureLoadBalancer), "
            "(4) Restart the SQL warehouse after NCC changes, wait 10 min. "
            "If NOT using NCC: open NSG port to AzureCloud service tag (not Internet)."
        )
    return "Check the log output above for details."


# =============================================================================
# Tool 4: manage_terraform_runs
# =============================================================================


@mcp.tool
def manage_terraform_runs(
    action: str,
    run_id: str = None,
) -> Dict[str, Any]:
    """
    Manage Terraform provisioning runs: list past runs, get outputs, or destroy.

    Actions:
    - list: List all provisioning runs with their status, template, and timestamp.
      Shows runs in reverse chronological order (newest first).
    - outputs: Get the Terraform outputs (workspace_url, etc.) for a specific run.
      Requires run_id.
    - destroy: Destroy all infrastructure from a previous run. This is IRREVERSIBLE
      and will delete the workspace and all associated resources. Requires run_id.
      ALWAYS ask the user for explicit confirmation before destroying.

    Args:
        action: "list", "outputs", or "destroy"
        run_id: Run ID (required for "outputs" and "destroy" actions).
                Get run IDs from the "list" action.

    Returns:
        Dictionary with action results. For list: array of run metadata.
        For outputs: the Terraform outputs. For destroy: destruction status.
    """
    act = action.lower()

    if act == "list":
        runs = _list_runs()
        return {"runs": runs, "count": len(runs)}

    elif act == "outputs":
        if not run_id:
            return {"error": "run_id is required for 'outputs' action"}
        return _get_run_outputs(run_id)

    elif act == "destroy":
        if not run_id:
            return {"error": "run_id is required for 'destroy' action"}
        try:
            return _terraform_destroy(run_id)
        except TerraformError as e:
            return {"error": str(e), "log": e.log}

    else:
        return {
            "error": f"Unknown action: {action}",
            "hint": "Valid actions: list, outputs, destroy",
        }


# =============================================================================
# Tool 5: manage_account_identity
# =============================================================================


@mcp.tool
def manage_account_identity(
    object_type: str,
    action: str,
    # Common identifiers
    id: str = None,
    name: str = None,
    display_name: str = None,
    # Group membership
    member_id: str = None,
    member_ids: List[str] = None,
    # Workspace assignments
    workspace_id: int = None,
    principal_id: int = None,
    permissions: List[str] = None,
    # Metastore
    metastore_id: str = None,
    default_catalog_name: str = "dev",
    storage_root: str = None,
    region: str = None,
    role_arn: str = None,
    access_connector_id: str = None,
    is_default: bool = True,
    new_owner: str = None,
    force: bool = False,
    # Filtering
    filter_str: str = None,
    max_results: int = 100,
    # Cloud / profile
    cloud: str = None,
    credentials_profile: str = "default",
) -> Dict[str, Any]:
    """
    Manage Databricks account-level identity and governance.

    This tool uses the Databricks Account API (not Terraform) to manage
    users, groups, service principals, workspace assignments, and metastores.

    PREREQUISITE: Account credentials must be stored via manage_credentials
    (action="store_databricks_account") before using this tool.

    Object types and their actions:

    user:
      - list: List all account users. Optional: filter_str, max_results.
      - create: Create a user. Required: name (email). Optional: display_name.
      - get: Get user details. Required: id.
      - delete: Remove a user. Required: id.

    group:
      - list: List all account groups. Optional: filter_str, max_results.
      - create: Create a group. Required: display_name. Optional: member_ids.
        IMPORTANT: These are ACCOUNT-LEVEL groups. Only account-level groups
        can be used as Unity Catalog grant principals. Workspace-local groups
        (created via workspace SCIM API) are invisible to UC.
      - get: Get group with members. Required: id.
      - delete: Delete a group. Required: id.
      - add_member: Add user/SP to group. Required: id (group), member_id.
      - remove_member: Remove from group. Required: id (group), member_id.

    service_principal:
      - list: List all service principals. Optional: filter_str, max_results.
      - create: Create a SP. Required: display_name.
      - get: Get SP details. Required: id.
      - delete: Delete a SP. Required: id.

    workspace_assignment:
      - list: List workspace permissions. Required: workspace_id.
      - assign: Grant workspace access. Required: workspace_id, principal_id,
        permissions (e.g. ["USER"] or ["ADMIN"]).
      - unassign: Revoke workspace access. Required: workspace_id, principal_id.

    metastore:
      - list: List all account metastores.
      - get: Get metastore details. Required: metastore_id.
      - create: Create a new metastore. Required: name, storage_root. Optional: region.
      - create_data_access: Create data access credential for metastore.
        AWS: Required: metastore_id, name, role_arn. Optional: is_default (default True).
        Azure: Use workspace-level storage-credentials API instead (not this tool).
          See azure-unity-catalog template or databricks CLI:
          databricks storage-credentials create --json '{"name":"...","azure_managed_identity":{"access_connector_id":"..."}}'
          Then: databricks metastores update <id> --json '{"storage_root_credential_id":"<uuid>"}'
      - assign: Assign metastore to workspace. Required: workspace_id, metastore_id.
        Optional: default_catalog_name (avoid "main" — it auto-exists on new workspaces).
        NOTE: Assigning a metastore also auto-enables serverless compute.
      - update: Update metastore (transfer ownership). Required: metastore_id. Optional: new_owner.
      - delete: Delete a metastore. Required: metastore_id. Optional: force (default
        False — set True to unassign from all workspaces first).

    Args:
        object_type: "user", "group", "service_principal", "workspace_assignment",
                     or "metastore"
        action: Action to perform (see above per object_type)
        id: Object ID (for get/delete/membership operations)
        name: User email (for user create)
        display_name: Display name (for create operations)
        member_id: User/SP ID to add/remove from group
        member_ids: List of user/SP IDs (for group create with initial members)
        workspace_id: Databricks workspace ID (numeric)
        principal_id: User/group/SP ID (for workspace assignment)
        permissions: Permission levels, e.g. ["USER"] or ["ADMIN"]
        metastore_id: Metastore ID (for metastore operations)
        default_catalog_name: Default catalog when assigning metastore
        storage_root: S3 URI for metastore root (e.g. s3://bucket/prefix)
        region: AWS region for new metastore (optional, inferred if omitted)
        role_arn: IAM role ARN for metastore data access credential (AWS)
        access_connector_id: Azure Access Connector resource ID (Azure)
        is_default: Whether to set new data access config as the metastore default
        new_owner: New owner (email/SP) when updating a metastore
        force: Force-delete metastore even if assigned to workspaces
        filter_str: SCIM filter string for list operations
        max_results: Max items to return for list operations
        cloud: Cloud provider ("azure", "aws", "gcp"). Auto-detected if omitted.
        credentials_profile: Stored credential profile name

    Returns:
        Dictionary with operation results.
    """
    otype = object_type.lower().replace("-", "_").replace(" ", "_")
    act = action.lower()

    try:
        # ---- Users ----
        if otype == "user":
            if act == "list":
                items = _list_account_users(
                    cloud=cloud, profile=credentials_profile,
                    filter_str=filter_str, max_results=max_results,
                )
                return {"items": items, "count": len(items)}
            elif act == "create":
                if not name:
                    return {"error": "name (email) is required to create a user"}
                return _create_account_user(
                    user_name=name, display_name=display_name,
                    cloud=cloud, profile=credentials_profile,
                )
            elif act == "get":
                if not id:
                    return {"error": "id is required to get a user"}
                return _get_account_user(
                    user_id=id, cloud=cloud, profile=credentials_profile,
                )
            elif act == "delete":
                if not id:
                    return {"error": "id is required to delete a user"}
                return _delete_account_user(
                    user_id=id, cloud=cloud, profile=credentials_profile,
                )

        # ---- Groups ----
        elif otype == "group":
            if act == "list":
                items = _list_account_groups(
                    cloud=cloud, profile=credentials_profile,
                    filter_str=filter_str, max_results=max_results,
                )
                return {"items": items, "count": len(items)}
            elif act == "create":
                if not display_name:
                    return {"error": "display_name is required to create a group"}
                return _create_account_group(
                    display_name=display_name, member_ids=member_ids,
                    cloud=cloud, profile=credentials_profile,
                )
            elif act == "get":
                if not id:
                    return {"error": "id is required to get a group"}
                return _get_account_group(
                    group_id=id, cloud=cloud, profile=credentials_profile,
                )
            elif act == "delete":
                if not id:
                    return {"error": "id is required to delete a group"}
                return _delete_account_group(
                    group_id=id, cloud=cloud, profile=credentials_profile,
                )
            elif act == "add_member":
                if not id or not member_id:
                    return {"error": "id (group) and member_id are required"}
                return _add_group_member(
                    group_id=id, member_id=member_id,
                    cloud=cloud, profile=credentials_profile,
                )
            elif act == "remove_member":
                if not id or not member_id:
                    return {"error": "id (group) and member_id are required"}
                return _remove_group_member(
                    group_id=id, member_id=member_id,
                    cloud=cloud, profile=credentials_profile,
                )

        # ---- Service Principals ----
        elif otype == "service_principal":
            if act == "list":
                items = _list_account_service_principals(
                    cloud=cloud, profile=credentials_profile,
                    filter_str=filter_str, max_results=max_results,
                )
                return {"items": items, "count": len(items)}
            elif act == "create":
                if not display_name:
                    return {"error": "display_name is required to create a service principal"}
                return _create_account_service_principal(
                    display_name=display_name,
                    cloud=cloud, profile=credentials_profile,
                )
            elif act == "get":
                if not id:
                    return {"error": "id is required to get a service principal"}
                return _get_account_service_principal(
                    sp_id=id, cloud=cloud, profile=credentials_profile,
                )
            elif act == "delete":
                if not id:
                    return {"error": "id is required to delete a service principal"}
                return _delete_account_service_principal(
                    sp_id=id, cloud=cloud, profile=credentials_profile,
                )

        # ---- Workspace Assignments ----
        elif otype in ("workspace_assignment", "workspace"):
            if act == "list":
                if not workspace_id:
                    return {"error": "workspace_id is required to list assignments"}
                items = _list_workspace_assignments(
                    workspace_id=workspace_id,
                    cloud=cloud, profile=credentials_profile,
                )
                return {"items": items, "count": len(items)}
            elif act == "assign":
                if not workspace_id or not principal_id or not permissions:
                    return {
                        "error": "workspace_id, principal_id, and permissions are required",
                        "hint": 'permissions should be ["USER"] or ["ADMIN"]',
                    }
                return _assign_workspace_permissions(
                    workspace_id=workspace_id, principal_id=principal_id,
                    permissions=permissions,
                    cloud=cloud, profile=credentials_profile,
                )
            elif act == "unassign":
                if not workspace_id or not principal_id:
                    return {"error": "workspace_id and principal_id are required"}
                return _unassign_workspace_permissions(
                    workspace_id=workspace_id, principal_id=principal_id,
                    cloud=cloud, profile=credentials_profile,
                )

        # ---- Metastores ----
        elif otype == "metastore":
            if act == "list":
                items = _list_account_metastores(
                    cloud=cloud, profile=credentials_profile,
                )
                return {"items": items, "count": len(items)}
            elif act == "get":
                if not metastore_id:
                    return {"error": "metastore_id is required"}
                return _get_account_metastore(
                    metastore_id=metastore_id,
                    cloud=cloud, profile=credentials_profile,
                )
            elif act == "create":
                if not name or not storage_root:
                    return {"error": "name and storage_root are required to create a metastore"}
                return _create_metastore(
                    name=name, storage_root=storage_root, region=region,
                    cloud=cloud, profile=credentials_profile,
                )
            elif act == "create_data_access":
                if not metastore_id or not name:
                    return {"error": "metastore_id and name are required"}
                if not role_arn and not access_connector_id:
                    return {"error": "Provide role_arn (AWS) or access_connector_id (Azure)"}
                return _create_metastore_data_access(
                    metastore_id=metastore_id, name=name,
                    role_arn=role_arn,
                    access_connector_id=access_connector_id,
                    is_default=is_default,
                    cloud=cloud, profile=credentials_profile,
                )
            elif act == "assign":
                if not workspace_id or not metastore_id:
                    return {"error": "workspace_id and metastore_id are required"}
                return _assign_metastore_to_workspace(
                    workspace_id=workspace_id, metastore_id=metastore_id,
                    default_catalog_name=default_catalog_name,
                    cloud=cloud, profile=credentials_profile,
                )
            elif act == "update":
                if not metastore_id:
                    return {"error": "metastore_id is required"}
                return _update_metastore(
                    metastore_id=metastore_id, new_owner=new_owner,
                    cloud=cloud, profile=credentials_profile,
                )
            elif act == "delete":
                if not metastore_id:
                    return {"error": "metastore_id is required"}
                return _delete_metastore(
                    metastore_id=metastore_id, force=force,
                    cloud=cloud, profile=credentials_profile,
                )

        else:
            return {
                "error": f"Unknown object_type: {object_type}",
                "hint": "Valid types: user, group, service_principal, "
                        "workspace_assignment, metastore",
            }

        return {
            "error": f"Unknown action '{action}' for {object_type}",
            "hint": f"See tool description for valid actions per object_type",
        }

    except ValueError as e:
        return {"error": str(e), "hint": "Check your credentials with manage_credentials(action='list')"}
    except Exception as e:
        logger.exception("manage_account_identity failed")
        return {"error": str(e)}


# =============================================================================
# Tool 6: manage_workspace_config
# =============================================================================


@mcp.tool
def manage_workspace_config(
    config_type: str,
    action: str,
    # Common identifiers
    id: str = None,
    name: str = None,
    # IP access lists
    label: str = None,
    list_type: str = None,
    ip_addresses: List[str] = None,
    # Secrets
    scope: str = None,
    key: str = None,
    string_value: str = None,
    initial_manage_principal: str = None,
    # Cluster policies
    definition: Dict[str, Any] = None,
    description: str = None,
    max_clusters_per_user: int = None,
    # SQL warehouses
    cluster_size: str = "2X-Small",
    auto_stop_mins: int = 15,
    min_num_clusters: int = 1,
    max_num_clusters: int = 1,
    warehouse_type: str = "PRO",
    enable_serverless: bool = False,
    # Tokens
    comment: str = None,
    lifetime_seconds: int = 7776000,
    # Workspace config
    config_keys: List[str] = None,
    config_values: Dict[str, str] = None,
) -> Dict[str, Any]:
    """
    Manage workspace-level configuration: IP access lists, secrets, cluster
    policies, SQL warehouses, tokens, and workspace settings.

    This tool operates on the CURRENT workspace (connected via auth).
    For account-level operations, use manage_account_identity instead.

    Config types and their actions:

    ip_access_list:
      - list: List all IP access lists.
      - create: Create an IP access list. Required: label, list_type ("ALLOW"
        or "BLOCK"), ip_addresses (list of IPs/CIDRs).
      - delete: Delete an IP access list. Required: id.

    secret:
      - list_scopes: List all secret scopes.
      - create_scope: Create a scope. Required: scope. Optional:
        initial_manage_principal ("users" for all users).
      - list: List secrets in a scope (metadata only). Required: scope.
      - put: Store a secret. Required: scope, key, string_value.
      - delete: Delete a secret. Required: scope, key.
      - delete_scope: Delete entire scope. Required: scope.

    cluster_policy:
      - list: List all cluster policies.
      - create: Create a policy. Required: name, definition (JSON dict).
        Optional: description, max_clusters_per_user.
      - get: Get policy details. Required: id.
      - delete: Delete a policy. Required: id.

    sql_warehouse:
      - list: List all SQL warehouses.
      - create: Create a warehouse. Required: name. Optional: cluster_size,
        auto_stop_mins, min/max_num_clusters, warehouse_type, enable_serverless.
      - get: Get warehouse details. Required: id.
      - delete: Delete a warehouse. Required: id.
      - start: Start a stopped warehouse. Required: id.
      - stop: Stop a running warehouse. Required: id.

    token:
      - list: List personal access tokens.
      - create: Create a PAT. Optional: comment, lifetime_seconds.
      - revoke: Revoke a token. Required: id.

    workspace_settings:
      - get: Get config values. Required: config_keys (list of key names).
      - set: Set config values. Required: config_values (dict of key=value).

    Args:
        config_type: "ip_access_list", "secret", "cluster_policy",
                     "sql_warehouse", "token", or "workspace_settings"
        action: Action to perform (see above per config_type)
        id: Resource ID (for get/delete/start/stop/revoke)
        name: Name (for create operations)
        label: IP access list label
        list_type: "ALLOW" or "BLOCK" (for ip_access_list create)
        ip_addresses: List of IP addresses or CIDRs
        scope: Secret scope name
        key: Secret key name
        string_value: Secret value to store
        initial_manage_principal: Who can manage the scope ("users" = all)
        definition: Cluster policy definition as JSON dict
        description: Description for cluster policy
        max_clusters_per_user: Max clusters per user for policy
        cluster_size: SQL warehouse size (default: "2X-Small")
        auto_stop_mins: Auto-stop timeout in minutes (default: 15)
        min_num_clusters: Min clusters for warehouse scaling
        max_num_clusters: Max clusters for warehouse scaling
        warehouse_type: "PRO", "CLASSIC" (default: "PRO")
        enable_serverless: Use serverless compute for warehouse
        comment: Token comment/description
        lifetime_seconds: Token lifetime (default: 90 days)
        config_keys: Workspace config keys to read
        config_values: Workspace config key-value pairs to set

    Returns:
        Dictionary with operation results.
    """
    ctype = config_type.lower().replace("-", "_").replace(" ", "_")
    act = action.lower()

    try:
        # ---- IP Access Lists ----
        if ctype == "ip_access_list":
            if act == "list":
                items = _list_ip_access_lists()
                return {"items": items, "count": len(items)}
            elif act == "create":
                if not label or not list_type or not ip_addresses:
                    return {
                        "error": "label, list_type, and ip_addresses are required",
                        "hint": 'list_type should be "ALLOW" or "BLOCK". '
                                'ip_addresses is a list of IPs or CIDRs.',
                    }
                return _create_ip_access_list(
                    label=label, list_type=list_type, ip_addresses=ip_addresses,
                )
            elif act == "delete":
                if not id:
                    return {"error": "id is required to delete an IP access list"}
                return _delete_ip_access_list(ip_access_list_id=id)

        # ---- Secrets ----
        elif ctype == "secret":
            if act == "list_scopes":
                items = _list_secret_scopes()
                return {"items": items, "count": len(items)}
            elif act == "create_scope":
                if not scope:
                    return {"error": "scope name is required"}
                return _create_secret_scope(
                    scope=scope,
                    initial_manage_principal=initial_manage_principal,
                )
            elif act == "list":
                if not scope:
                    return {"error": "scope is required to list secrets"}
                items = _list_secrets(scope=scope)
                return {"items": items, "count": len(items)}
            elif act == "put":
                if not scope or not key or not string_value:
                    return {"error": "scope, key, and string_value are required"}
                return _put_secret(scope=scope, key=key, string_value=string_value)
            elif act == "delete":
                if not scope or not key:
                    return {"error": "scope and key are required to delete a secret"}
                return _delete_secret(scope=scope, key=key)
            elif act == "delete_scope":
                if not scope:
                    return {"error": "scope is required to delete a scope"}
                return _delete_secret_scope(scope=scope)

        # ---- Cluster Policies ----
        elif ctype == "cluster_policy":
            if act == "list":
                items = _list_cluster_policies()
                return {"items": items, "count": len(items)}
            elif act == "create":
                if not name or not definition:
                    return {
                        "error": "name and definition are required",
                        "hint": "definition is a JSON dict, e.g. "
                                '{"spark_version": {"type": "fixed", "value": "13.3.x-scala2.12"}}',
                    }
                return _create_cluster_policy(
                    name=name, definition=definition,
                    description=description,
                    max_clusters_per_user=max_clusters_per_user,
                )
            elif act == "get":
                if not id:
                    return {"error": "id is required to get a cluster policy"}
                return _get_cluster_policy(policy_id=id)
            elif act == "delete":
                if not id:
                    return {"error": "id is required to delete a cluster policy"}
                return _delete_cluster_policy(policy_id=id)

        # ---- SQL Warehouses ----
        elif ctype == "sql_warehouse":
            if act == "list":
                items = _list_sql_warehouses()
                return {"items": items, "count": len(items)}
            elif act == "create":
                if not name:
                    return {"error": "name is required to create a SQL warehouse"}
                return _create_sql_warehouse(
                    name=name, cluster_size=cluster_size,
                    auto_stop_mins=auto_stop_mins,
                    min_num_clusters=min_num_clusters,
                    max_num_clusters=max_num_clusters,
                    warehouse_type=warehouse_type,
                    enable_serverless=enable_serverless,
                )
            elif act == "get":
                if not id:
                    return {"error": "id is required to get a SQL warehouse"}
                return _get_sql_warehouse(warehouse_id=id)
            elif act == "delete":
                if not id:
                    return {"error": "id is required to delete a SQL warehouse"}
                return _delete_sql_warehouse(warehouse_id=id)
            elif act == "start":
                if not id:
                    return {"error": "id is required to start a SQL warehouse"}
                return _start_sql_warehouse(warehouse_id=id)
            elif act == "stop":
                if not id:
                    return {"error": "id is required to stop a SQL warehouse"}
                return _stop_sql_warehouse(warehouse_id=id)

        # ---- Tokens ----
        elif ctype == "token":
            if act == "list":
                items = _list_tokens()
                return {"items": items, "count": len(items)}
            elif act == "create":
                return _create_token(
                    comment=comment or "Created by databricks-platform-kit",
                    lifetime_seconds=lifetime_seconds,
                )
            elif act == "revoke":
                if not id:
                    return {"error": "id (token_id) is required to revoke a token"}
                return _revoke_token(token_id=id)

        # ---- Workspace Settings ----
        elif ctype in ("workspace_settings", "workspace_config"):
            if act == "get":
                if not config_keys:
                    return {
                        "error": "config_keys is required",
                        "hint": "Common keys: enableTokensConfig, maxTokenLifetimeDays, "
                                "enableIpAccessLists, enableResultsDownloading",
                    }
                return _get_workspace_config(keys=config_keys)
            elif act == "set":
                if not config_values:
                    return {"error": "config_values dict is required"}
                return _set_workspace_config(config=config_values)

        else:
            return {
                "error": f"Unknown config_type: {config_type}",
                "hint": "Valid types: ip_access_list, secret, cluster_policy, "
                        "sql_warehouse, token, workspace_settings",
            }

        return {
            "error": f"Unknown action '{action}' for {config_type}",
            "hint": "See tool description for valid actions per config_type",
        }

    except Exception as e:
        logger.exception("manage_workspace_config failed")
        return {"error": str(e)}

# Azure Platform Provisioning

Cloud-specific guidance for provisioning Databricks workspaces on Azure.

## Authentication

### Check current auth state

```bash
az account show  # subscription ID, tenant ID, logged-in user
env | grep -i DATABRICKS  # check for conflicting env vars
cat ~/.databrickscfg 2>/dev/null  # check for DEFAULT profile conflicts
```

### Required credentials

- **Azure CLI session**: `az login` (or `az login --use-device-code` for headless). All templates support az-cli auth -- service principal credentials are optional.
- **Databricks Account ID**: From the Databricks accounts console (accounts.azuredatabricks.net). Ask the customer if not known.
- **Subscription ID and Tenant ID**: From `az account show`. If the customer has multiple tenants, confirm which one hosts the Databricks account.

### Provider configuration

All Azure templates use two providers:

```hcl
provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

provider "databricks" {
  host      = "https://accounts.azuredatabricks.net"
  account_id = var.databricks_account_id
  auth_type  = "azure-cli"
  azure_tenant_id = var.tenant_id  # CRITICAL -- see tenant mismatch gotcha
}
```

After workspace creation, a second Databricks provider block targets the workspace:

```hcl
provider "databricks" {
  alias     = "workspace"
  host      = azurerm_databricks_workspace.this.workspace_url
  auth_type = "azure-cli"
  azure_tenant_id = var.tenant_id  # CRITICAL -- must be on EVERY provider block
}
```

**GOTCHA: Always set `auth_type = "azure-cli"` explicitly.** Without it, the provider may pick up OAuth M2M credentials from `~/.databrickscfg` DEFAULT profile, causing auth failures or targeting the wrong account.

## Gotchas

### Tenant mismatch

Always set `azure_tenant_id` on ALL Databricks provider blocks -- both account-level and workspace-level. Without it, the provider fetches the management token from the user's home tenant, not the Databricks account tenant. This causes `IncorrectClaimException: Expected iss claim to be...` errors. Even if the user only has one tenant today, set it explicitly for safety.

### Databricks lowercases all names

Storage credentials, catalogs, external locations, schemas -- the Databricks API lowercases everything. Always use `lower()` in Terraform for any Databricks resource name to avoid "Provider produced inconsistent final plan" errors.

### databricks_mws_permission_assignment does NOT work on Azure

This resource is AWS/GCP only. On Azure, account-level groups are visible in workspaces via UC identity federation -- no explicit workspace permission assignment is needed.

### Storage container names must be lowercase

Azure storage container names reject uppercase characters. Use `lower()` when the naming prefix might contain uppercase.

### DNS zone collision for multiple workspaces

The private DNS zone `privatelink.azuredatabricks.net` is hardcoded. Without a hub-spoke pattern, multiple workspaces with private link MUST use separate resource groups. With hub-spoke, a single shared zone in the transit resource group avoids collisions.

### CIDR overlap

Each workspace's VNet CIDR must be unique across all workspaces in the same account and region. Overlapping CIDRs cause `NETWORK_CHECK_CONTROL_PLANE_FAILURE` on classic clusters. Auto-generate non-overlapping CIDRs (e.g., 10.1.0.0/16, 10.2.0.0/16, 10.3.0.0/16 for dev/stg/prod).

### Two-phase deploy for Private Link + Unity Catalog

Terraform provider configs cannot reference resource attributes for `host`. When deploying private link workspaces with UC:
- **Phase 1**: Create workspaces, networking, private endpoints
- **Phase 2**: Set workspace URLs in tfvars, apply again for catalogs, schemas, grants

### Catalog isolation_mode cannot be set during creation

Attempting to set `isolation_mode` during `CREATE CATALOG` returns `INVALID_PARAMETER_VALUE`. Create the catalog first, then update isolation_mode via a separate PATCH call.

### Azure Policy / owner tag requirement

Many enterprise subscriptions enforce an `owner` tag on all resources. Ask the customer about required tags early. All templates propagate tags to all resources via `local.tags`.

### DNS zone VNet link deletion is extremely slow

Azure DNS zone VNet link deletions take 30-60+ minutes. This is an Azure API limitation. Combined with token expiry, this can cause Terraform failures during refactors or destroys. Warn the customer before running `terraform destroy` on private link deployments.

### Azure CLI token expiry (~60 min)

`az login` tokens expire after approximately 60 minutes. Long Terraform applies (workspace creation + DNS operations) can exceed this. If apply fails with `ExpiredAuthenticationToken`, re-run `az login` and `terraform apply` -- Terraform resumes from where it left off.

### .databrickscfg DEFAULT profile conflict

If `~/.databrickscfg` has a DEFAULT profile with OAuth M2M credentials, the Databricks Terraform provider may use those instead of az-cli auth. The templates set `auth_type = "azure-cli"` explicitly to prevent this.

## Default Network Posture

Recommend VNet injection with Secure Cluster Connectivity (SCC) as the default:
- Custom VNet with public and private subnets
- NSG delegated to Databricks
- `no_public_ip = true` (SCC enabled)
- No private link unless explicitly requested

## Azure Template Patterns

| Pattern | When to Use |
|---------|-------------|
| `azure-workspace-basic` | Quick start, dev/test, managed VNet is acceptable |
| `azure-workspace-vnet-injection` | Default for production — VNet injection + SCC |
| `azure-workspace-full` | Production with UC in a single deploy |
| `azure-workspace-privatelink` | Customer requires no public access to UI/API |
| `azure-multi-workspace-privatelink` | Enterprise multi-env (dev/stg/prod) with private link |
| `azure-unity-catalog` | Adding UC to an existing workspace |

## Reference Repos

Fetch from these at runtime for Azure Terraform patterns:
- `https://github.com/databricks/terraform-databricks-sra` — Azure section for SRA-compliant patterns (VNet injection, CMK, log delivery, exfil protection)
- `https://github.com/databricks/terraform-databricks-examples` — Azure examples for workspaces, UC, networking, private link

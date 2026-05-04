# Azure — Gotchas & Error Handling

Read this when you hit an error during apply, or as a sanity-check pass before applying. Most entries are tied to a specific error message — search by that.

## Azure SKU is always "premium" in Terraform

The `azurerm_databricks_workspace` resource only accepts `sku` values of `standard`, `premium`, or `trial`. There is NO `enterprise` SKU value. "Enterprise tier" in Databricks refers to account-level licensing (enabling Private Link, CMK, ESC, IP ACLs), not a Terraform parameter. Always use `sku = "premium"` — even for workspaces that need Enterprise features. The SRA production template uses `sku = "premium"` with full CMK and Private Link.

## Customer-says-`tier=PREMIUM` vs Terraform's `sku="premium"` (intake-time call-out)

The customer will often say "we need Premium tier" or "we need Enterprise tier". Always translate at intake time:

- Customer "Standard tier" → `sku = "standard"`
- Customer "Premium tier" → `sku = "premium"`
- Customer "Enterprise tier" → `sku = "premium"` (Enterprise is account-level licensing, not a `sku` value)

Confirm with the customer in turn 1 of the conversation: "Just to confirm — by 'Enterprise' you mean the Enterprise account licensing for PrivateLink/CMK/IP-ACL, right? On Azure that maps to `sku = premium` at the workspace resource level."

## Avoid hyphens in Unity Catalog object names

Catalog, schema, and table names with hyphens (`fraud-poc`, `my-catalog`) require backtick escaping in every SQL query, confuse BI tools, and break hive_metastore compatibility. Use underscores: `fraud_poc` not `fraud-poc`. When deriving names from a prefix that contains hyphens, replace them: `lower(replace(var.prefix, "-", "_"))`. The SRA AWS templates do this explicitly.

## Databricks lowercases all names

Storage credentials, catalogs, external locations, schemas — the Databricks API lowercases everything. Always use `lower()` in Terraform for any Databricks resource name to avoid "Provider produced inconsistent final plan" errors.

## `databricks_mws_permission_assignment` does NOT work on Azure

This resource is AWS/GCP only. On Azure, account-level groups are visible in workspaces via UC identity federation — no explicit workspace permission assignment is needed.

## Storage container names must be lowercase

Azure storage container names reject uppercase characters. Use `lower()` when the naming prefix might contain uppercase.

## DNS zone collision for multiple workspaces

The private DNS zone `privatelink.azuredatabricks.net` is hardcoded. Without a hub-spoke pattern, multiple workspaces with private link MUST use separate resource groups. With hub-spoke, a single shared zone in the transit resource group avoids collisions.

## CIDR overlap

Each workspace's VNet CIDR must be unique across all workspaces in the same account and region. Overlapping CIDRs cause `NETWORK_CHECK_CONTROL_PLANE_FAILURE` on classic clusters. Auto-generate non-overlapping CIDRs (e.g., 10.1.0.0/16, 10.2.0.0/16, 10.3.0.0/16 for dev/stg/prod).

## Two-phase deploy for Private Link + Unity Catalog

Terraform provider configs cannot reference resource attributes for `host`. When deploying private link workspaces with UC:
- **Phase 1**: Create workspaces, networking, private endpoints
- **Phase 2**: Set workspace URLs in tfvars, apply again for catalogs, schemas, grants

## Key Vault `network_acls.default_action = "Deny"` blocks Terraform-driven CMK creation

When you lock down a customer-managed Key Vault with `network_acls.default_action = "Deny"`, Terraform's `azurerm_key_vault_key` create step (run from your local IP) fails with `ForbiddenByFirewall: Client address is not authorized` even when `network_acls.virtual_network_subnet_ids` includes the Databricks subnets. Reason: the Databricks subnets aren't where the deployer is calling from — your laptop / CI runner is. Putting the Databricks subnets in `virtual_network_subnet_ids` doesn't help the deployer's request.

**Two acceptable fixes:**

1. **Recommended for prod:** keep `default_action = "Allow"` until after the apply, OR add `network_acls.bypass = "AzureServices"` AND your deployer IP to `network_acls.ip_rules` for the duration of the apply, then PATCH to `Deny` after.
2. **For SRA-style deploys:** rely on access policies + private endpoint to the KV; don't set `network_acls` at all in the SRA template (it's permissive by default for the deployer; private endpoint provides the network restriction at runtime).

Either way: do NOT set `default_action = "Deny"` without adding the deployer's egress IP. The SRA reference template omits `network_acls` for exactly this reason.

## CMK for managed disks — DES Key Vault access

When enabling CMK for managed disks (`managed_disk_cmk_key_vault_key_id`), Azure creates a Disk Encryption Set (DES) in the managed resource group. The DES has a managed identity that needs Key Vault access — but this identity only exists AFTER workspace creation. Pattern from the SRA:

```hcl
resource "azurerm_key_vault_access_policy" "managed_disk" {
  key_vault_id = azurerm_key_vault.this.id
  tenant_id    = azurerm_databricks_workspace.this.managed_disk_identity[0].tenant_id
  object_id    = azurerm_databricks_workspace.this.managed_disk_identity[0].principal_id
  key_permissions = ["Get", "UnwrapKey", "WrapKey"]
}
```

Without this, classic clusters fail with "Azure key vault key is not found to unwrap the encryption key." Serverless is unaffected. Use access policies (not RBAC) on the Key Vault — do NOT set `enable_rbac_authorization = true` if using access policies for the DES identity. Do the same for `storage_account_identity` if using DBFS CMK.

## Catalog `isolation_mode` cannot be set during creation

Attempting to set `isolation_mode` during `CREATE CATALOG` returns `INVALID_PARAMETER_VALUE`. Create the catalog first, then update isolation_mode via a separate PATCH call.

## Azure Policy / owner tag requirement

Many enterprise subscriptions enforce an `owner` tag on all resources. Ask the customer about required tags early. All templates propagate tags to all resources via `local.tags`.

## UDR/firewall — never hardcode firewall IPs

When creating UDR routes to send traffic through Azure Firewall, always reference the firewall resource's IP directly in Terraform (`azurerm_firewall.this.ip_configuration[0].private_ip_address`). Never hardcode a firewall IP. If the customer specifies a firewall that doesn't exist in the current subscription (e.g., test environment), use conditional creation (`count = var.firewall_enabled ? 1 : 0`) and skip the UDR subnet association. A UDR pointing to a non-existent appliance creates a traffic blackhole — all outbound connectivity is lost and clusters cannot start. The SRA uses this exact pattern in `modules/hub/firewall.tf`.

## DNS zone VNet link deletion is extremely slow

Azure DNS zone VNet link deletions take 30-60+ minutes. This is an Azure API limitation. Combined with token expiry, this can cause Terraform failures during refactors or destroys. Warn the customer before running `terraform destroy` on private link deployments.

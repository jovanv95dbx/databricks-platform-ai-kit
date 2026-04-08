---
name: databricks-identity-governance
description: "Manage Databricks identity and governance. Use when the user asks to create groups, users, service principals, set up RBAC, manage permissions, workspace assignments, or configure access control."
---

# Databricks Identity & Governance

## How to interact with the customer

Apply LIGHT pushback on identity decisions, with hard rules on UC identity requirements.

- **One admin group proposed** -- suggest once that tiered groups (platform-admins, data-engineers, data-analysts, etc.) are better for least-privilege. If the customer insists on a flat structure, do it.
- **Specific group structure requested** -- just do it. Do not second-guess naming or hierarchy.
- **Individual user grants** -- suggest once that group-only grants are best practice (easier to audit, rotate, onboard). If they insist on user-level grants, do it.
- **Workspace-local groups** -- hard no. Account-level SCIM groups are mandatory for Unity Catalog. Workspace-local groups are invisible to UC and will silently fail on grants.
- **Jobs running as user identity** -- suggest once that service principals are the correct pattern. User identities cause failures when the user leaves or their token expires.
- **Everyone gets admin** -- warn once that least-privilege is strongly recommended. Only the platform team should have ADMIN.

## Hard rules (always enforce)

These are not suggestions. Violating them causes silent failures or security gaps.

1. **ONLY account-level SCIM groups.** Workspace-local groups are invisible to Unity Catalog. Every grant, every assignment must use account-level groups created via the Account SCIM API.
2. **Group-only grants.** Never grant catalog/schema/table permissions to individual users. Always grant to groups. This is the only auditable, maintainable pattern.
3. **Service principals for all automated jobs.** CI/CD pipelines, scheduled jobs, and orchestration must use service principals, not user identities. User tokens expire, users leave the org, and user-based jobs break silently.
4. **Least-privilege admin model.** Only the platform team gets ADMIN on workspaces. Everyone else gets USER. Data access is controlled through UC grants, not workspace roles.
5. **Pre-existing groups: check before creating.** Account-level groups persist across deployments and workspace deletions. Always list existing groups before creating new ones to avoid SCIM conflict errors.

## Recommended group structure

This is the default recommendation for multi-environment deployments. Adjust based on customer needs.

| Group | Dev | Stg | Prod |
|-------|-----|-----|------|
| platform-admins | ADMIN, ALL_PRIVILEGES | ADMIN, ALL_PRIVILEGES | ADMIN, ALL_PRIVILEGES |
| data-engineers | USER, full CRUD | USER, full CRUD | USER, full CRUD |
| data-analysts | -- | USER, read silver/gold | USER, read silver/gold |
| data-scientists | USER, full CRUD | USER, read only | -- |
| ml-ops | USER, read+write | USER, read | USER, read |

- **platform-admins**: workspace ADMIN + ALL_PRIVILEGES on catalogs. Owns metastore, manages infra.
- **data-engineers**: workspace USER + USE_CATALOG, USE_SCHEMA, CREATE_TABLE, CREATE_FUNCTION, SELECT, MODIFY on all schemas.
- **data-analysts**: workspace USER + USE_CATALOG, USE_SCHEMA, SELECT on silver and gold schemas only. No dev access.
- **data-scientists**: workspace USER + full CRUD in dev, read-only in staging for validation. No prod access.
- **ml-ops**: workspace USER + read/write in dev (experiment tracking), read in staging/prod.

## Workflow: Create groups and users

### Step 1: Create account-level groups via Account SCIM API

Create groups at the account level. These are visible across all UC-enabled workspaces automatically.

Account console URLs by cloud:
- **Azure:** accounts.azuredatabricks.net
- **AWS:** accounts.cloud.databricks.com
- **GCP:** accounts.gcp.databricks.com

Before creating, list existing groups to avoid conflicts. Account-level groups persist even after workspaces are deleted.

### Step 2: Create users

Create users at the account level via SCIM. Users need a valid email (userName) and displayName.

### Step 3: Add users to groups

Add users as members of the appropriate groups. A user can belong to multiple groups. Group membership determines all access -- workspace assignment, catalog grants, schema permissions.

## Workflow: Service principals

### Per-environment service principals

Create one SP per environment for CI/CD pipelines:
- `{prefix}-cicd-dev`
- `{prefix}-cicd-stg`
- `{prefix}-cicd-prod`

Each SP gets added to the appropriate groups for its environment (e.g., cicd-dev joins data-engineers in dev workspace).

### Platform admin service principal

Create a single platform admin SP for infrastructure automation:
- `{prefix}-platform-admin-sp`

Add this SP to the platform-admins group. It manages metastores, workspace config, and cross-environment operations.

## Workflow: Workspace assignments

Assign groups and users to specific workspaces with a permission level (USER or ADMIN).

- **List** existing assignments to see who has access.
- **Assign** a principal (group or user) with USER or ADMIN permission.
- **Unassign** to revoke workspace access.

On Azure with UC identity federation, `databricks_mws_permission_assignment` does not work. Account-level groups are visible in workspaces automatically via identity federation -- no explicit assignment needed. This Terraform resource is AWS/GCP only.

## Workflow: UC grants

Grant permissions at the catalog and schema level to groups. Never to individual users.

### Tiered grant pattern

- **Engineers** get full CRUD: USE_CATALOG, USE_SCHEMA, CREATE_TABLE, CREATE_FUNCTION, CREATE_SCHEMA, SELECT, MODIFY
- **Analysts** get read on silver/gold: USE_CATALOG, USE_SCHEMA, SELECT (scoped to silver and gold schemas)
- **Platform admins** get ALL_PRIVILEGES on catalogs

Use modern privilege names only. Legacy names (e.g., USAGE instead of USE_CATALOG) cause confusing errors.

## Error handling

- **"SCIM conflict"** -- the user or group already exists at the account level. List first, then update the existing object instead of creating a new one.
- **"Group with name X already exists"** -- account-level groups persist across deployments. Use Terraform data sources to reference existing groups, or run `terraform import` to bring them into state.
- **"permissions are [...] but have to be [...]"** -- you used a legacy privilege name. Switch to modern names: USE_CATALOG, USE_SCHEMA, CREATE_TABLE, CREATE_FUNCTION, CREATE_SCHEMA, SELECT, MODIFY.

## Cross-links

- For workspace creation, see **platform-provisioning**.
- For Unity Catalog metastore and catalog setup, see **unity-catalog-setup**.

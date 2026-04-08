---
name: databricks-unity-catalog-setup
description: "Set up Unity Catalog on Databricks workspaces. Use when the user asks to configure Unity Catalog, create a metastore, set up catalogs, schemas, external locations, storage credentials, or configure data governance. Covers Azure, AWS, and GCP."
---

# Unity Catalog Setup

Configure Unity Catalog end-to-end: metastores, storage credentials, external locations, catalogs, schemas, and grants.

## How to Interact with the Customer

Apply MODERATE pushback. Ask clarifying questions when the request is ambiguous, but execute immediately when requirements are clear.

**Must-ask if not specified:**
- No storage strategy mentioned --> ask: "Do you want a self-managed metastore with your own storage, or are you using the Databricks-managed (vending machine) metastore?" Then recommend self-managed.
- No environment strategy mentioned --> ask: "Single catalog or per-environment catalogs (dev/stg/prod)?"

**Strong warnings (state once, then proceed if they insist):**
- Wants vending machine metastore for production --> warn: "Vending machine default storage is serverless-only. Classic compute cannot read it. I strongly recommend deploying a self-managed metastore with your own bucket/container."

**Hard stops (do not proceed):**
- Per-env catalogs sharing a single storage account/bucket --> refuse: "Each catalog must have its own dedicated storage account/bucket. Shared storage breaks blast-radius isolation and enables cross-environment data leakage. Create one storage account per catalog."
- DBFS for production data --> refuse: "DBFS is deprecated for production. Use external locations with UC-managed storage credentials."
- Workspace-local groups as UC grant principals --> refuse: "Unity Catalog requires account-level SCIM groups. Workspace-local groups are invisible to UC. Create account-level groups first."

**Clear request with storage strategy --> just do it.** No unnecessary questions.

## Opinionated Defaults

These are the recommended production design. Apply them unless the user explicitly requests otherwise.

- **Single metastore per region** -- shared across all workspaces in that region. Never create multiple metastores in the same region.
- **Self-managed metastore with own storage** -- deploy your own S3 bucket / ADLS container / GCS bucket. Never rely on vending machine for production.
- **Per-environment catalogs with dedicated storage accounts/buckets** (MUST for multi-env). Each catalog (dev/stg/prod) gets its own storage account (ADLS) / S3 bucket / GCS bucket. This is not optional for production — it isolates blast radius, enables independent RBAC, and prevents cross-environment data leakage. Never share a single storage account across catalogs.
- **Workspace binding** -- prod catalog only visible in prod workspace. Set `isolation_mode = "ISOLATED"` on the catalog, then bind with `databricks_workspace_binding`:
  ```hcl
  resource "databricks_workspace_binding" "prod_catalog" {
    securable_name = databricks_catalog.prod.name
    securable_type = "catalog"
    workspace_id   = var.prod_workspace_id
    binding_type   = "BINDING_TYPE_READ_WRITE"
  }
  ```
  Do NOT use raw API calls or `null_resource` with `local-exec` — the Terraform resource manages state and lifecycle correctly. Also works for `storage_credential` and `external_location` securable types. Dev and stg catalogs can remain `OPEN`.
- **External locations over managed storage** -- own your data paths, control your storage layout. Use `MANAGED LOCATION` on catalogs pointing to external locations.
- **DBFS is deprecated** -- never store production data in DBFS. All new data goes through external locations.
- **Medallion schemas** -- bronze/silver/gold per catalog. This is the standard. Create them by default.
- **Underscores in all names** — catalog, schema, and table names must use underscores, not hyphens (`fraud_poc` not `fraud-poc`). Hyphens require backtick escaping in SQL, confuse BI tools, and break hive_metastore compatibility. When deriving names from prefixes, use `replace(name, "-", "_")`.
- **Account-level SCIM groups for all grants** -- no individual user grants, no workspace-local groups.
- **Service principals for jobs** -- not user identities. Per-env SPs for CI/CD pipelines.
- **Group-only grants** -- every UC permission goes to a group, never a user. Easier to audit, easier to rotate.
- **Modern privilege names** -- USE_CATALOG (not USAGE), USE_SCHEMA (not USAGE), CREATE_TABLE (not CREATE). Old names are rejected by the API.

## Workflow: UC via Terraform

**For new workspaces:** UC is part of the full workspace template (`*-workspace-full`). The workspace and UC deploy together.

**For existing workspaces:** Use the UC-only templates:
- `azure-unity-catalog` -- access connector + ADLS + metastore + catalog + schemas
- `aws-unity-catalog` -- IAM UC role + S3 + metastore + catalog + schemas
- `gcp-unity-catalog` -- GCS + metastore + auto-generated SA + catalog + schemas

Fetch reference patterns from the official Databricks Terraform repos before writing any Terraform:
- `https://github.com/databricks/terraform-databricks-sra` — SRA-compliant UC patterns
- `https://github.com/databricks/terraform-databricks-examples` — UC examples per cloud

**IMPORTANT:** Once you know the cloud, read the cloud-specific file for this skill:
- Azure --> read `AZURE.md` in this skill directory
- AWS --> read `AWS.md` in this skill directory
- GCP --> read `GCP.md` in this skill directory

## Workflow: UC via SDK/API (No Terraform)

For existing workspaces where Terraform is not managing the infrastructure.

**Step 1: Create metastore (account API)**
One metastore per region. Check if one already exists first.
```
PUT /api/2.1/accounts/{account_id}/metastores
{"name": "...", "storage_root": "s3://... or abfss://... or gs://...", "region": "..."}
```

**Step 2: Configure data access (cloud-specific)**
Read the cloud-specific file (AZURE.md / AWS.md / GCP.md) for the exact setup: IAM roles, access connectors, or GCP service accounts.

**Step 3: Assign metastore to workspace**
```
PUT /api/2.1/accounts/{account_id}/workspaces/{workspace_id}/metastore
{"metastore_id": "..."}
```

**Step 4: Create catalogs + schemas (workspace API)**
Databricks auto-creates a `main` catalog on metastore assignment. Use a different name for your catalogs.
```sql
CREATE CATALOG dev MANAGED LOCATION 's3://myproject-catalog-dev/';
CREATE SCHEMA dev.bronze;
CREATE SCHEMA dev.silver;
CREATE SCHEMA dev.gold;
```

**Step 5: Grant access (workspace API)**
```sql
GRANT USE_CATALOG ON CATALOG dev TO `data-engineers`;
GRANT USE_SCHEMA, CREATE_TABLE, CREATE_FUNCTION ON SCHEMA dev.bronze TO `data-engineers`;
GRANT USE_SCHEMA, SELECT ON SCHEMA dev.gold TO `data-analysts`;
```

## External Location Hygiene

- **One storage account/bucket per environment.** `myproject-catalog-dev`, `myproject-catalog-stg`, `myproject-catalog-prod`.
- **One storage credential per cloud identity.** Reuse the same credential across catalogs where the same IAM role / access connector / SA has access to all buckets.
- **External locations: one per bucket/container.** Each maps to a single storage path.
- **Use `CREATE CATALOG ... MANAGED LOCATION` (SQL)** -- NOT `storage_root` in the REST API. `MANAGED LOCATION` correctly ties the catalog to the external location path. `storage_root` bypasses the binding.
- **Grant `account users` USE_CATALOG + USE_SCHEMA + SELECT** on each catalog for basic read access. Without this, catalogs do not appear in the UI even with `isolation_mode = OPEN`.

## Post-UC Checklist

After deploying Unity Catalog, verify every item:

1. Metastore attached to workspace(s)
2. Storage credentials created and marked as default
3. External locations created (one per bucket/container)
4. Per-env catalogs created with `MANAGED LOCATION` pointing to external locations
5. Medallion schemas created (bronze/silver/gold) in each catalog
6. UC permissions granted to account-level groups (not users, not workspace-local groups)
7. Verify with test query on BOTH classic compute (1+ workers) AND serverless SQL
   - Classic: `spark.sql("SELECT * FROM dev.bronze.test_table")`
   - Serverless: run same query in SQL warehouse
   - If classic fails with "Databricks Default Storage cannot be accessed using Classic Compute" --> you are on vending machine storage, deploy self-managed metastore

## Cross-Links

- For workspace creation --> see `platform-provisioning` skill
- For groups, users, service principals, and RBAC --> see `identity-governance` skill
- For private networking --> see `private-networking` skill

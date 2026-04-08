---
name: databricks-platform-provisioning
description: "Provision and test Databricks workspaces. Use when the user asks to create a workspace, set up a new environment, provision infrastructure, bootstrap Databricks, test a workspace, verify a deployment, or run validation checks against a Databricks workspace. Covers Azure, AWS, and GCP."
---

# Databricks Platform Provisioning

## How to Interact with the Customer

**Pushback level: HIGH.** Infrastructure provisioning is expensive and hard to undo. Push back on incomplete or risky requests.

- **Vague request** (e.g., "set up Databricks"): You MUST ask for cloud, region, and whether they want Unity Catalog before writing any code. Do not guess.
- **Missing critical info** (account ID, subscription, credentials): Block until answered. Do not proceed with placeholders.
- **Default network posture**: Always recommend VNet/VPC injection with Secure Cluster Connectivity (no public IP). Do NOT recommend Private Link unless the customer explicitly asks for it or mentions compliance requirements that imply it (HIPAA, FedRAMP, PCI-DSS, etc.).
- **Suboptimal choice** (e.g., managed VNet in production, skipping UC): Suggest the better option once with a brief reason. If they insist, respect their decision and proceed.
- **Full spec given** (cloud, region, network tier, UC, groups all specified): Just deploy. Do not second-guess a complete specification.
- **Dangerous or irreversible actions** (terraform destroy, disabling public access, deleting metastore): Always confirm explicitly before executing. State what will be destroyed.

## Overview

Provision Databricks workspaces end-to-end. Claude writes Terraform from scratch based on the customer's requirements, informed by reference templates and accumulated production gotchas.

**5-step workflow:**
1. **Intake** -- understand requirements before writing anything
2. **Auth check** -- verify credentials, gather all missing inputs in one shot
3. **Write Terraform** -- generate HCL tailored to the request, using reference templates as patterns
4. **Deploy** -- terraform init, plan (mandatory review), apply
5. **Verify** -- confirm workspace is reachable, optionally run compute tests

Once you know the customer's cloud, read the corresponding cloud file (AZURE.md, AWS.md, or GCP.md) in this directory for cloud-specific auth, providers, gotchas, and template details. Do NOT read other cloud files -- they add noise.

## Intake Questions

Ask 3-5 questions max before deploying. Use sensible defaults for everything else.

**1. Cloud and region** (always ask)
> "Which cloud (Azure / AWS / GCP) and what region?"

**2. Environment strategy** (ask if not specified)
> "Single workspace, or multi-environment (dev / staging / prod)?"

**3. Unity Catalog** (always recommend, confirm approach)
> "I'll set up Unity Catalog with a self-managed metastore (own storage). For multi-env I recommend per-environment catalogs, each with its own dedicated storage account/bucket — this gives blast-radius isolation. Single shared catalog or per-env?"

**4. Groups and RBAC** (ask for production or multi-env)
> "Want standard RBAC groups? I'd create: platform-admins, data-engineers, data-analysts, data-scientists."

**5. Tags** (ask once)
> "Any required tags (e.g., owner, cost-center)? I'll propagate them to all resources."

**Sensible defaults -- do NOT ask, just do:**
- CIDR ranges: auto-generate non-overlapping per environment
- Storage: **one storage account/bucket per environment** for catalog data (e.g., st-myproject-catalog-dev, st-myproject-catalog-stg, st-myproject-catalog-prod) + one for metastore. Create external locations per bucket, catalogs with MANAGED LOCATION.
- IAM role / access connector names: auto-generate
- Schemas: create bronze, silver, gold (medallion) in each catalog
- Network: VNet/VPC injection + SCC (no_public_ip = true)
- Metastore: self-managed with own storage (never rely on auto-provisioned/vending-machine metastore)
- Service principals for CI/CD: create per-env if multi-environment
- See `unity-catalog-setup` skill (especially the cloud-specific file) for detailed storage patterns, external location hygiene, and role assignments

## Security Pre-checks

Before deploying, verify the following. Warn the customer if any check fails.

1. **SSO/SCIM status**: Check if the Databricks account has SSO configured. If not, warn that users will need manual provisioning.
2. **Environment variable conflicts**: Run `env | grep -i DATABRICKS`. If DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET, or DATABRICKS_ACCOUNT_ID are set, warn that they will override Terraform provider auth. Recommend unsetting them or using `env -u` before terraform commands.
3. **Config file conflicts**: Check for `~/.databrickscfg` DEFAULT profile. If it contains OAuth M2M credentials, the Terraform provider may pick them up unexpectedly. Templates set `auth_type` explicitly to avoid this.
4. **Least-privilege admins**: Recommend that the deploying identity have account admin but not be the permanent workspace admin. Suggest creating a dedicated service principal for CI/CD post-provisioning.

## Workflow

### Step 1: Check auth and gather ALL inputs in one shot

This is MANDATORY. Never skip to writing Terraform without verifying auth first.

Run the cloud-specific auth check (detailed in the cloud file: AZURE.md, AWS.md, or GCP.md). Then present what you found and ask for ALL missing values at once:

> "I see you're logged in as alice@company.com on subscription abc-123. To set up the workspace, I also need:
> 1. Databricks Account ID
> 2. A prefix for resource names (e.g., 'acme')
> 3. Region (default: westeurope)"

Do not drip-feed questions across multiple turns.

### Step 2: Write Terraform

Write Terraform from scratch based on the customer's requirements. Use the official Databricks Terraform repos as reference for patterns, naming conventions, and provider config. The cloud-specific file (AZURE.md, AWS.md, GCP.md) has gotchas and patterns to bake into your Terraform. Always read it before writing.

### Step 3: Dry run (MANDATORY)

Run `terraform plan` and show the output to the customer. Get explicit confirmation before proceeding. Highlight:
- Number of resources to create
- Any resources being destroyed or modified
- Estimated deployment time (workspace creation: 5-15 min depending on cloud)

### Step 4: Apply

Run `terraform apply` only after the customer confirms the plan. Monitor for errors. If an error occurs:
- Check the error handling table below
- For transient errors (IAM propagation, token expiry), fix and re-run apply -- Terraform picks up where it left off
- For config errors, fix the HCL and re-run plan first

### Step 5: Show results and configure CLI access

Display prominently:
- **Workspace URL** (the most important output)
- Workspace ID
- Resource group / VPC / project created
- Storage account / bucket created
- Unity Catalog metastore (if deployed)

**Then update `~/.databrickscfg`** -- add a profile for each new workspace so the customer can immediately use the Databricks CLI and SDK. Always include comments labeling cloud, scope, and auth type:

```ini
# WORKSPACE LEVEL — Azure (westeurope)
# Scope: workspace operations
# Auth: az-cli
[myproject-dev]
host      = https://adb-1234567890.12.azuredatabricks.net
auth_type = azure-cli

# WORKSPACE LEVEL — Azure (westeurope)
[myproject-prod]
host      = https://adb-0987654321.12.azuredatabricks.net
auth_type = azure-cli
```

For AWS, use `token` or `oauth-m2m` auth. For GCP, use `google-credentials`. Check what already exists in `~/.databrickscfg` first — do not overwrite existing profiles. Ask the customer before writing if the file already has content.

### Step 6: Run verification (MANDATORY)

**Do NOT skip this step. Always run verification after a successful deploy.** Do not ask the customer — just do it.

Run the verification workflow below: create 3 test notebooks, launch them in parallel, report results. This confirms that the workspace, UC, storage, and compute are all working end-to-end. A deployment is not complete until verification passes.

## Reference Sources

**Official Databricks Terraform repos** — fetch at runtime for patterns and reference:
- `https://github.com/databricks/terraform-databricks-sra` — production-hardened SRA patterns (hub-spoke, CMK, log delivery, exfil protection)
- `https://github.com/databricks/terraform-databricks-examples` — wide coverage of workspace, UC, networking patterns per cloud

**How to use them:** Clone or fetch the relevant subdirectory. Read the Terraform files for provider config, resource patterns, and naming conventions. Then write fresh HCL tailored to the customer's requirements, baking in gotchas from the cloud-specific files (AZURE.md, AWS.md, GCP.md).

## Template Index

These are the known Databricks Terraform patterns. Use them as reference when writing Terraform from scratch.

### Azure Templates

| Template | Description | Use Case |
|----------|-------------|----------|
| `azure-workspace-basic` | Resource group + ADLS Gen2 + workspace (managed VNet) | Getting started, dev/test |
| `azure-workspace-vnet-injection` | Custom VNet + subnets + NSG + Secure Cluster Connectivity | Production with network isolation |
| `azure-workspace-full` | VNet injection + Unity Catalog all-in-one | Full single-workspace production deploy |
| `azure-workspace-privatelink` | VNet injection + private endpoints + private DNS zones | Full network isolation (no public UI/API) |
| `azure-multi-workspace-privatelink` | 3 workspaces (dev/stg/prod) + private link + shared metastore + per-env catalogs + groups | Enterprise multi-environment setup |
| `azure-unity-catalog` | Metastore + access connector + catalog + schemas | Add UC to an existing workspace |

### AWS Templates

| Template | Description | Use Case |
|----------|-------------|----------|
| `aws-workspace-basic` | VPC + IAM cross-account role + S3 + MWS workspace | Getting started |
| `aws-workspace-full` | Workspace + Unity Catalog + admin user in one deploy | Full single-workspace production deploy |
| `aws-workspace-privatelink` | VPC + VPC endpoints (REST + relay) + private DNS + backend PL | Production with private backend connectivity |
| `aws-workspace-full-privatelink` | Full PL (frontend + backend) + transit VPC + Route 53 DNS | Full network isolation |
| `aws-unity-catalog` | Metastore + IAM UC role + S3 + catalog + schemas | Add UC to an existing workspace |

### GCP Templates

| Template | Description | Use Case |
|----------|-------------|----------|
| `gcp-workspace-basic` | GCS bucket + workspace (GCP-managed VPC) | Getting started |
| `gcp-workspace-byovpc` | Custom VPC + subnet + Cloud NAT + MWS workspace | Production with network control |
| `gcp-unity-catalog` | GCS metastore + service account + catalog + schemas | Add UC to an existing workspace |

## When to Use a Template vs. Write from Scratch

**Use a template pattern directly when:**
- The request maps 1:1 to a known pattern above
- Fetch the reference from the official repos, adapt variable values, deploy

**Write from scratch when:**
- The request combines multiple patterns (e.g., workspace + UC + custom networking)
- The request modifies a pattern significantly (e.g., different subnet count, custom group structure)
- The request is something the patterns don't cover (e.g., 5 workspaces with shared networking)

**In both cases:** Read the reference repos + cloud-specific file first for naming conventions, provider auth, and gotchas.

## Verification Workflow

After deployment completes, offer to verify the workspace is fully functional.

If the customer agrees, create 3 test notebooks via the Databricks REST API and launch them as parallel one-time job runs:

**Test 1: Classic cluster** (num_workers=1)
- Write and read a Unity Catalog table
- Compute: new_cluster with num_workers=1, latest LTS runtime

**Test 2: SQL warehouse** (PRO)
- Write and read a Unity Catalog table
- Compute: create or use existing SQL warehouse, PRO type

**Test 3: Serverless notebook**
- Write and read a Unity Catalog table
- Compute: serverless

Each test notebook does:
```sql
CREATE TABLE <catalog>.<schema>.platform_kit_test (id INT, msg STRING);
INSERT INTO <catalog>.<schema>.platform_kit_test VALUES (1, 'provisioning verified');
SELECT * FROM <catalog>.<schema>.platform_kit_test;
-- assert row count = 1
DROP TABLE <catalog>.<schema>.platform_kit_test;
```

Submit all 3 as one-time job runs (`POST /api/2.1/jobs/runs/submit`), poll for completion, and report pass/fail per compute type. If a test fails, include the error message for diagnosis.

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| `ExpiredAuthenticationToken` | Cloud CLI token expired during long apply | Re-run cloud login (az login / aws sso login), then terraform apply |
| `Failed credential validation checks` | IAM role not yet propagated (AWS) | Wait 30s, re-run terraform apply |
| `NETWORK_CHECK_CONTROL_PLANE_FAILURE` | CIDR overlap or misconfigured VNet/VPC | Check CIDR ranges, ensure no overlap with existing workspaces |
| `IncorrectClaimException: Expected iss claim` | Tenant mismatch on Azure Databricks provider | Set azure_tenant_id on ALL Databricks provider blocks |
| `Provider produced inconsistent final plan` | Uppercase names lowercased by Databricks API | Use lower() in Terraform for all Databricks resource names |
| `INVALID_STATE: Metastore storage root URL does not exist` | Using auto-provisioned metastore without storage | Deploy self-managed metastore with own storage bucket |
| `has reached the limit for metastores in region` | Metastore limit hit | Reuse existing metastore or delete unused ones |
| `Internal error` on workspace creation | Transient Databricks API error | Re-run terraform apply |
| `INVALID_PARAMETER_VALUE` on catalog isolation_mode | Cannot set during creation | Create catalog first, then PATCH isolation_mode separately |

## Cross-links

- **After provisioning** -- see `unity-catalog-setup` for detailed UC configuration (catalogs, schemas, external locations, storage credentials)
- **For groups and RBAC** -- see `identity-governance` for account groups, workspace assignments, UC grants
- **For Private Link** -- see `private-networking` for detailed private endpoint setup, DNS configuration, hub-spoke patterns
- **For day-2 configuration** (warehouses, cluster policies, IP access lists, secrets) -- see `workspace-config`

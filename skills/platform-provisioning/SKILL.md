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

Ask these questions before deploying. Use plain language — the customer may not know Databricks-specific terms. Keep it conversational, not a checklist dump. Ask in logical groups, not all at once.

**Round 1: Basics** (always ask)

**1. Cloud and region**
> "Which cloud are you on (Azure / AWS / GCP) and what region should the workspace go in?"

**2. New or existing Databricks account?**
> "Do you already have a Databricks account, or do we need to set one up from scratch?"
- If new: note that they'll need marketplace subscription permissions (AWS) or resource provider registration (Azure)
- If existing: ask for the Account ID and confirm they have account admin access

**3. Environment strategy**
> "Is this a single workspace (e.g., for a POC or a small team), or do you need separate environments like dev, staging, and production?"

**4. What's the purpose?**
> "Is this for a quick proof-of-concept, or a production setup that needs to be hardened?"
- POC/evaluation → simpler setup, can use managed networking, skip some hardening
- Production → VNet/VPC injection, proper IAM, encryption, monitoring

**Round 2: Security and networking** (ask for production; skip or use defaults for POC)

**5. Network isolation level** (use plain language, not Databricks terms)
> "How locked down does the network need to be?"
> - **Standard** (recommended default): Your workspace runs in your own network (VPC/VNet), compute nodes have no public IPs, all outbound traffic goes through NAT. Data stays in your network.
> - **Private backend**: Same as standard, plus the communication between your compute and the Databricks control plane also stays private (no public internet). The web UI and API are still publicly accessible.
> - **Fully private**: Everything is private — web UI, API, and backend. You'll need VPN or ExpressRoute/DirectConnect to access the workspace at all.
> - **Fully private + data exfiltration protection**: Maximum lockdown. Prevents any data from leaving through the Databricks control plane. Requires Enterprise tier.

**6. Encryption requirements**
> "Do you need to manage your own encryption keys for data at rest? (If you're not sure, the default Databricks-managed encryption is fine for most use cases.)"
- Yes → need Customer Managed Keys (CMK), requires Enterprise tier
- No / not sure → use default encryption

**7. IP restrictions**
> "Do you want to restrict who can access the Databricks API and UI by IP address? For example, only allowing access from your corporate network?"
- Account-level (applies to all workspaces)
- Workspace-level (per-workspace)
- Not needed

**8. Compliance requirements**
> "Are there any compliance frameworks you need to meet — like HIPAA, PCI-DSS, FedRAMP, or internal security policies? This affects which features and tier we need."
- Yes → may need Enterprise tier, Enhanced Security and Compliance (ESC), specific network setup
- No → standard setup

**Round 3: Data governance** (always ask)

**9. Unity Catalog**
> "I'll set up Unity Catalog for data governance — this gives you access control, lineage tracking, and data discovery. For multi-env setups I'll create separate catalogs (dev/stg/prod), each with its own dedicated storage — this isolates environments so a mistake in dev can't affect production data. Sound good?"

**10. Groups and RBAC** (ask for production or multi-env)
> "Want me to set up standard access groups? I'd create: platform-admins (full control), data-engineers (build pipelines), data-analysts (read data), data-scientists (experiments). You can add users to these groups later."

**11. Tags** (ask once)
> "Any required tags for your cloud resources (e.g., owner, cost-center, environment)? I'll apply them to everything."

**Pricing tier logic — determine automatically, don't ask directly:**
- Need private link, CMK, IP ACLs, or compliance (ESC)? → **Enterprise** tier required (note: on Azure, the Terraform `sku` is still `"premium"` — "Enterprise" is an account-level licensing concept, not a Terraform SKU value. See AZURE.md.)
- Otherwise → **Premium** is sufficient (still includes Unity Catalog)
- Tell the customer: "Based on your requirements, you'll need Enterprise/Premium tier" — don't make them figure it out

**Permissions pre-check — verify after intake, before deploying:**
Once you know the cloud (read the cloud-specific file AWS.md/AZURE.md/GCP.md), verify the customer has the required permissions for their chosen deployment type. If they don't, tell them exactly what's missing before proceeding.

**Sensible defaults -- do NOT ask, just do:**
- CIDR ranges: auto-generate non-overlapping per environment
- Storage: **one storage account/bucket per environment** for catalog data (e.g., st-myproject-catalog-dev, st-myproject-catalog-stg, st-myproject-catalog-prod) + one for metastore. Create external locations per bucket, catalogs with MANAGED LOCATION.
- IAM role / access connector names: auto-generate
- Schemas: create bronze, silver, gold (medallion) in each catalog
- Network: VNet/VPC injection + no public IP (Secure Cluster Connectivity) as the default
- Metastore: self-managed with own storage (never rely on auto-provisioned/vending-machine metastore)
- Service principals for CI/CD: create per-env if multi-environment
- IaC: always use Terraform (recommend this as the deployment method)
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

**Official Databricks Terraform repos** — you MUST clone these before writing any Terraform:
- `https://github.com/databricks/terraform-databricks-sra` — production-hardened SRA patterns (Enterprise features: CMK, Private Link, ESC, hub-spoke, log delivery, exfil protection)
- `https://github.com/databricks/terraform-databricks-examples` — broad coverage of workspace types, UC, networking, VNet injection, Private Link, lakehouse patterns per cloud

**How to use them:**

1. Clone both repos:
   ```bash
   git clone --depth 1 https://github.com/databricks/terraform-databricks-sra /tmp/tf-sra
   git clone --depth 1 https://github.com/databricks/terraform-databricks-examples /tmp/tf-examples
   ```
2. Find the closest matching template(s) from the Template Index below
3. Read the actual .tf files — pay attention to resource dependencies, access policies, provider config, and conditional logic
4. Adapt the template to the customer's requirements — change variables, add/remove resources, adjust naming
5. When combining features from multiple templates (e.g., VNet injection from examples + CMK from SRA), pull the specific resource blocks and merge them
6. Bake in gotchas from the cloud-specific files (AZURE.md, AWS.md, GCP.md)

**Why this is mandatory:** The SRA and examples repos contain production-tested patterns that handle edge cases (CMK DES access policies, NSG delegation, two-phase deploys, conditional firewall routing) that are easy to miss when writing from scratch. In stress testing, agents that skipped template fetching had a 3x higher failure rate than those that started from templates.

Do NOT write Terraform from memory. Always start from reference code.

## Template Index

These are the known Databricks Terraform patterns across both official repos. Always check the closest match before writing Terraform.

### Azure Templates — Examples Repo (`terraform-databricks-examples`)

| Template | Path | Description | Use Case |
|----------|------|-------------|----------|
| `adb-vnet-injection` | `examples/adb-vnet-injection/` | Custom VNet + subnets + NSG + SCC | **Default for production** — start here for most deployments |
| `adb-lakehouse` | `examples/adb-lakehouse/` + `modules/adb-lakehouse/` | VNet injection + Key Vault + UC + storage + network | Full lakehouse with CMK pattern |
| `adb-unity-catalog-basic-demo` | `examples/adb-unity-catalog-basic-demo/` | Metastore + access connector + catalog + schemas | UC-only setup for existing workspace |
| `adb-private-links` | `examples/adb-private-links/` | VNet injection + private endpoints + private DNS | Full network isolation |
| `adb-with-private-link-standard` | `examples/adb-with-private-link-standard/` | Standard Private Link pattern | Simpler PL without exfil protection |
| `adb-exfiltration-protection` | `examples/adb-exfiltration-protection/` | VNet + PL + NSG lockdown + UC | Maximum security lockdown |
| `adb-data-storage-vnet-ncc-private-endpoint` | `examples/adb-data-storage-vnet-ncc-*` | NCC + private endpoint to storage | Serverless private connectivity to data |

### Azure Modules — SRA Repo (`terraform-databricks-sra`) — Enterprise/Compliance

Use these when the customer needs Enterprise features (CMK, Private Link, ESC, compliance profiles).

| Customer Need | SRA File | What It Contains |
|--------------|----------|-----------------|
| Workspace + VNet injection + SCC | `azure/tf/modules/workspace/main.tf` | Workspace resource with full custom_parameters, NSG rules, SCC |
| CMK — Key Vault + keys | `azure/tf/modules/hub/keyvault.tf` | Key Vault (premium, purge-protected) + RSA-2048 keys for managed services and managed disks |
| CMK — DES access policy | `azure/tf/modules/workspace/main.tf` (lines 114-140) | Post-workspace access policies for `storage_account_identity` and `managed_disk_identity` — **critical for managed disk CMK** |
| Private Link endpoints | `azure/tf/modules/workspace/main.tf` | Private endpoints (ui_api + browser_auth) + DNS zone links |
| Private DNS zones | `azure/tf/modules/hub/main.tf` | Shared DNS zone in hub resource group |
| Hub-spoke VNet peering | `azure/tf/spoke.tf` | VNet peering between hub and spoke |
| Unity Catalog metastore | `azure/tf/modules/hub/unitycatalog.tf` | Metastore + access connector + storage + role assignments |
| Compliance Security Profile | `azure/tf/modules/workspace/main.tf` | `enhanced_security_compliance` block with CSP + ESM |
| Firewall / UDR | `azure/tf/modules/hub/firewall.tf` | Conditional firewall creation + route table + UDR |
| Account groups | `azure/tf/modules/hub/unitycatalog.tf` | `databricks_group` resources |
| Log delivery | `azure/tf/modules/hub/log_delivery.tf` | Diagnostic settings + storage |

### AWS Templates — Examples Repo

| Template | Path | Description | Use Case |
|----------|------|-------------|----------|
| `aws-workspace-basic` | `examples/aws-workspace-basic/` | VPC + IAM + S3 + workspace | Getting started |
| `aws-databricks-modular-privatelink` | `examples/aws-databricks-modular-privatelink/` | Modular VPC + Private Link | Production with PL |
| `aws-databricks-uc` | `examples/aws-databricks-uc/` | UC setup for AWS | Add UC to existing workspace |
| `aws-workspace-config` | `examples/aws-workspace-config/` | Cluster policies + IP ACLs | Day-2 workspace config |
| `aws-exfiltration-protection` | `examples/aws-exfiltration-protection/` | VPC + firewall + PL | Maximum lockdown |

### GCP Templates — Examples Repo

| Template | Path | Description | Use Case |
|----------|------|-------------|----------|
| `gcp-basic` | `examples/gcp-basic/` | GCS + workspace (managed VPC) | Getting started |
| `gcp-byovpc` | `examples/gcp-byovpc/` | Custom VPC + subnet + Cloud NAT | Production with network control |

## When to Use a Template vs. Combine Templates

**ALWAYS clone both repos first**, regardless of approach.

**Adapt a single template when:**
- The request maps 1:1 to a known pattern above
- Example: simple VNet injection → use `adb-vnet-injection` directly

**Combine templates when:**
- The request needs features from multiple patterns
- Example: VNet injection + CMK + UC → start from `adb-lakehouse` (examples repo), add DES access policy pattern from SRA `modules/workspace/main.tf`
- Example: Private Link + compliance → start from `adb-private-links` (examples repo), add ESC block from SRA `modules/workspace/main.tf`

**Matching guide:**

| Customer Need | Start From | Add From |
|--------------|------------|----------|
| Simple POC | `adb-vnet-injection` (examples) | — |
| Production with UC | `adb-lakehouse` (examples) | — |
| CMK encryption | `adb-lakehouse` (examples) | SRA `keyvault.tf` + `workspace/main.tf` DES policy |
| Private Link | `adb-private-links` (examples) | SRA `workspace/main.tf` for PE patterns |
| HIPAA / FedRAMP | SRA `azure/tf/` (full stack) | — |
| Multi-env enterprise | SRA `azure/tf/` (full stack) | Examples `aws-workspace-config` for day-2 |
| Exfiltration protection | `adb-exfiltration-protection` (examples) | SRA firewall patterns |

**Write from scratch ONLY when:**
- The request is something no template covers at all
- Even then, reference both repos for provider config, naming conventions, and access policy patterns

## Verification Workflow

**This is MANDATORY after every deployment. Do not skip. Do not ask — just run it.**

Create 3 test notebooks via the Databricks REST API and launch them as parallel one-time job runs:

**Test 1: Classic cluster** (num_workers=1)
- Write and read a Unity Catalog table
- Compute: new_cluster with num_workers=1, latest LTS runtime, data_security_mode="USER_ISOLATION" (or "SINGLE_USER")
- CRITICAL: data_security_mode is REQUIRED for classic clusters to access Unity Catalog. Without it, the cluster starts but all UC queries fail with `[UC_NOT_ENABLED]`.
- **AWS:** Some node types (m5.large, etc.) require `ebs_volume_count >= 1`. Include EBS config in the cluster spec.
- **Note:** First classic cluster on a brand-new workspace may take 10-15 min to start (JVM warmup + UC metadata resolution). If it hangs >30 min with USER_ISOLATION, cancel and retry with SINGLE_USER — this is a known transient issue on fresh workspaces.

**Test 2: SQL warehouse** (PRO)
- Write and read a Unity Catalog table
- Compute: create or use existing SQL warehouse, PRO type
- **Alternative:** Use the Statement Execution API (`POST /api/2.0/sql/statements`) directly against a running warehouse. Faster and avoids notebook creation overhead.

**Test 3: Serverless notebook**
- Write and read a Unity Catalog table
- Compute: serverless
- **AWS:** Serverless job submission requires the multi-task `tasks` array format with `environment_key`, not the single-task format.

Each test notebook does:
```sql
CREATE TABLE `<catalog>`.`<schema>`.platform_kit_test (id INT, msg STRING);
INSERT INTO `<catalog>`.`<schema>`.platform_kit_test VALUES (1, 'provisioning verified');
SELECT * FROM `<catalog>`.`<schema>`.platform_kit_test;
-- assert row count = 1
DROP TABLE `<catalog>`.`<schema>`.platform_kit_test;
-- NOTE: backtick quoting handles catalog/schema names with hyphens.
-- Best practice: use underscores in names to avoid quoting issues entirely.
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
| `PARSE_SYNTAX_ERROR` on catalog/schema reference | Catalog or schema name contains hyphens | Use underscores instead of hyphens. Wrap existing hyphenated names in backticks: \`my-catalog\` |
| Classic cluster cannot see UC catalogs / `PERMISSION_DENIED` on UC table | Cluster running without data_security_mode | Set `data_security_mode = "USER_ISOLATION"` or `"SINGLE_USER"` on the cluster |
| `Azure key vault key is not found to unwrap the encryption key` | Managed disk DES identity lacks Key Vault access | Grant `Get`, `UnwrapKey`, `WrapKey` to `managed_disk_identity` — see CMK section in AZURE.md |
| `Failed storage configuration validation checks: Access Denied` (AWS) | S3 bucket missing policy for Databricks E2 account | Add bucket policy granting `arn:aws:iam::414351767826:root` S3 access + set `BucketOwnerPreferred` |
| `Authentication failed` on workspace token creation (AWS) | U2M auth cannot create PATs via MWS API | Remove `token {}` block, use profile-based workspace auth |
| `invalid_client` on Databricks OAuth (AWS) | SP secret obfuscated (`dose` prefix) or expired | Use U2M auth (`databricks auth login`) or original non-obfuscated SP secret |
| `APIs not available` on permission assignment (AWS) | Identity federation enabled on workspace | Remove `databricks_mws_permission_assignment` — groups auto-sync |
| Terraform state lock (`Error acquiring the state lock`) | Concurrent terraform process or stale lock | Wait for other process, or delete `.terraform.tfstate.lock.info` if stale |

## Cross-links

- **After provisioning** -- see `unity-catalog-setup` for detailed UC configuration (catalogs, schemas, external locations, storage credentials)
- **For groups and RBAC** -- see `identity-governance` for account groups, workspace assignments, UC grants
- **For Private Link** -- see `private-networking` for detailed private endpoint setup, DNS configuration, hub-spoke patterns
- **For day-2 configuration** (warehouses, cluster policies, IP access lists, secrets) -- see `workspace-config`

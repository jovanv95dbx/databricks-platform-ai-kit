# AWS Platform Provisioning

Cloud-specific guidance for provisioning Databricks workspaces on AWS.

## AWS Deployment Options

Map the customer's answers from the intake questions to these deployment types:

| Customer says... | Deployment type | Tier needed | Key resources |
|-----------------|----------------|-------------|---------------|
| "Quick POC, don't want to manage infrastructure" | Serverless workspace (no customer VPC) | Premium | No cloud resources needed — fully managed |
| "POC but in our own account" | Classic with automated config | Premium | Databricks provisions VPC, S3, IAM in customer's account |
| "Production, we want control over networking" | **Customer-managed VPC (BYOVPC)** — this is the default | Premium | Customer creates VPC, subnets, S3, IAM cross-account role |
| "Production, backend traffic must stay private" | Backend Private Link | **Enterprise** | BYOVPC + VPC endpoints (REST API + relay) |
| "Everything must be private, no public access at all" | Full Private Link | **Enterprise** | BYOVPC + VPC endpoints + transit VPC + Route 53 private zone |
| "Maximum lockdown, prevent data exfiltration" | Full PL + data exfil protection | **Enterprise** | Full PL + restrictive firewall rules + SCC |

**Default recommendation: Customer-managed VPC (BYOVPC)** with Secure Cluster Connectivity. This is the standard production setup. Escalate to private link only if the customer's answers indicate they need it.

## AWS Permissions Pre-check

Verify the customer has these permissions BEFORE writing any Terraform. If they don't, tell them exactly what's missing.

**For new Databricks account:**
- AWS Marketplace subscription permission (`AWSMarketplaceManageSubscriptions` policy minimum) — needed to subscribe to Databricks
- Plus one of:
  - AWS Admin privilege (simplest), OR
  - S3 creation + VPC/networking creation + IAM creation privileges (least-privilege)

**For existing Databricks account:**
- Databricks Account Admin role (check at accounts.cloud.databricks.com)
- Plus one of:
  - AWS Admin privilege, OR
  - S3 creation + VPC/networking creation + IAM creation privileges

**For Private Link (in addition to above):**
- VPC endpoint creation privileges
- Route 53 hosted zone management (for full PL)
- Enterprise tier on the Databricks account

**For CMK (Customer Managed Keys):**
- KMS key creation and management privileges
- Enterprise tier on the Databricks account

Ask: "Can you confirm you have admin access to both the AWS account and the Databricks account? If not, what access do you have — I'll tell you exactly what permissions are needed."

## Authentication

### Check current auth state

```bash
aws sts get-caller-identity  # account ID, IAM user/role ARN
env | grep -i DATABRICKS  # check for conflicting env vars
databricks auth profiles 2>/dev/null  # list profiles + DEFAULT, never echoes secret values
```

### Required credentials

- **AWS CLI session**: IAM user credentials (`aws configure`), SSO session (`aws sso login`), or exported environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN).
- **Databricks Account ID**: From the Databricks accounts console (accounts.cloud.databricks.com). Ask the customer if not known.
- **Databricks account-level credentials**: Either a Databricks account admin user (email/password) or a service principal with account admin role. Needed for the Databricks provider to create MWS workspaces.

### CRITICAL: Environment variable overrides

Run `env | grep -i DATABRICKS` BEFORE any terraform command. If `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`, or `DATABRICKS_ACCOUNT_ID` are set, they **silently override** all Terraform provider config (profile, host, account_id). This is the #1 cause of "wrong account" or "invalid_client" errors on machines that also have Azure Databricks configured. **Fix:** Prefix every terraform command with `env -u DATABRICKS_CLIENT_ID -u DATABRICKS_CLIENT_SECRET -u DATABRICKS_ACCOUNT_ID` or unset them in your shell.

### CRITICAL: Databricks CLI obfuscated secrets (`dose` prefix)

The Databricks CLI v2 obfuscates M2M OAuth secrets in `~/.databrickscfg` with a `dose` prefix. These obfuscated values **cannot be used by the Terraform provider**. If you see `client_secret = dose...` in the config, do NOT copy it into Terraform variables. For account-level provider, use a U2M profile (`databricks auth login --host https://accounts.cloud.databricks.com --account-id <id>`). For workspace-level provider, use M2M with the **original** (non-obfuscated) client_id/client_secret via explicit env vars, or run `databricks auth login --host <workspace-url>` for U2M.

### CRITICAL: Do NOT use `token {}` block in `databricks_mws_workspaces`

The `token {}` block that auto-generates a PAT after workspace creation only works with M2M OAuth auth. It fails with U2M auth ("Authentication failed"). Instead, create the workspace WITHOUT `token {}` and use a separate workspace provider with profile-based auth via `databricks auth login --host <workspace-url>`.

### Provider configuration

AWS templates use two providers:

```hcl
provider "aws" {
  region = var.region
}

provider "databricks" {
  alias      = "mws"
  host       = "https://accounts.cloud.databricks.com"
  account_id = var.databricks_account_id
}
```

After workspace creation, a second Databricks provider targets the workspace. Do NOT use the `token {}` pattern — use profile-based auth instead:

```hcl
provider "databricks" {
  alias   = "workspace"
  host    = databricks_mws_workspaces.this.workspace_url
  profile = "${var.prefix}-workspace"  # created via: databricks auth login --host <url>
}
```

**GOTCHA: Azure SP credentials do NOT work on AWS.** Azure (accounts.azuredatabricks.net) and AWS (accounts.cloud.databricks.com) are completely separate account consoles with separate service principals. Always verify which account console credentials are being used.

## Gotchas

### CRITICAL: S3 bucket policy for Databricks E2 control plane

The workspace root S3 bucket MUST have a bucket policy granting the Databricks E2 control plane account (`414351767826`) direct access. The cross-account IAM role alone is NOT sufficient. Without this, workspace creation fails with: `Failed storage configuration validation checks: List, Put, PutWithBucketOwnerFullControl, Delete -- Access Denied`

```hcl
resource "aws_s3_bucket_policy" "root" {
  bucket = aws_s3_bucket.root.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DatabricksE2Access"
      Effect    = "Allow"
      Principal = { AWS = "arn:aws:iam::414351767826:root" }
      Action    = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject",
                   "s3:ListBucket", "s3:GetBucketLocation", "s3:PutObjectAcl"]
      Resource  = [aws_s3_bucket.root.arn, "${aws_s3_bucket.root.arn}/*"]
    }]
  })
}
```

### CRITICAL: S3 bucket ownership must be BucketOwnerPreferred

New S3 buckets default to `BucketOwnerEnforced` (no ACLs). Databricks validation tests `PutWithBucketOwnerFullControl`, which requires ACLs. Set `object_ownership = "BucketOwnerPreferred"` on ALL S3 buckets (root, metastore, catalog).

### Supported AWS regions

Not all AWS regions are supported by Databricks. Notable unsupported: **eu-north-1 (Stockholm)**. If requested, recommend **eu-west-1 (Ireland)** as closest supported EU region. Always verify region support before writing Terraform.

### KMS key policy for EC2/EBS encryption

If using KMS CMK for workspace encryption, the key policy must also grant EC2/EBS permissions for cluster volume encryption. Add a statement allowing the account root principal `kms:CreateGrant`, `kms:Decrypt`, `kms:DescribeKey`, `kms:Encrypt`, `kms:GenerateDataKey*`, `kms:ReEncrypt*` with condition `kms:CallerAccount` = your account ID.

### Workspace import limitation

`databricks_mws_workspaces` cannot be imported after creation if Terraform state is lost. If the workspace exists but is missing from state, reference it by URL/ID in locals. Use `terraform state rm` to clean up stale references.

### Identity federation disables permission assignment API

Workspaces with identity federation enabled do NOT support `databricks_mws_permission_assignment`. Account-level groups auto-sync — no explicit assignment needed. If you get "APIs not available", remove the permission assignment resources.

### IAM propagation delay

Cross-account IAM roles take 10-30 seconds to propagate after creation. If apply fails with "Failed credential validation checks", wait 30 seconds and re-run `terraform apply` -- the role will be propagated by then. Templates include a `time_sleep` resource, but it is sometimes insufficient.

### Catalog 'main' auto-created on metastore assignment

Databricks auto-creates a `main` catalog when a metastore is assigned to a workspace. Use a different name for custom catalogs to avoid conflicts. If you need to manage the `main` catalog, import it into Terraform state.

### AWS session token expiry

AWS STS session tokens (from SSO or AssumeRole) expire after 1-12 hours depending on the role's max session duration. Unlike Azure CLI which auto-refreshes, expired AWS tokens cause immediate Terraform failures. Re-export fresh credentials before long Terraform runs.

### SP workspace permissions for classic clusters

After creating a workspace, assign the deploying service principal as workspace ADMIN via `PUT /api/2.0/accounts/{id}/workspaces/{ws_id}/permissionassignments/principals/{sp_id}` with `["ADMIN"]`. Without this, the SP can create clusters but may not execute commands on them.

### Classic clusters need at least 1 worker for reliable testing

Single-node clusters (num_workers=0) cause command execution timeouts via the Commands API -- JVM warmup combined with UC metadata resolution on zero workers is unreliable. Always use num_workers=1 minimum for verification testing.

### Workspace creation transient errors

Workspace creation can occasionally return an internal error from the Databricks API. This is transient. Re-run `terraform apply` and it will either resume creation or detect the workspace was actually created.

### Vending machine (auto-provisioned) metastores

Many AWS accounts have auto-provisioned metastores with no storage root URL. Critical limitations:
- `CREATE CATALOG` fails with `INVALID_STATE: Metastore storage root URL does not exist` unless you provide `MANAGED LOCATION` pointing to an external location.
- Default storage is **serverless-only**. Data stored in the auto-provisioned metastore's default storage CANNOT be read by classic clusters. You get: `Databricks Default Storage cannot be accessed using Classic Compute.`
- **Always deploy a self-managed metastore** with the `aws-unity-catalog` template for production.

### Using someone else's metastore requires storage access

Attaching to an existing metastore you do not own causes `403 Forbidden from cloud storage provider` on `CREATE TABLE` because the metastore's IAM role does not grant access to your data. Deploy your own metastore for full control.

### SP needs explicit metastore permissions

If you assign a metastore that someone else owns, the SP needs `CREATE_CATALOG`, `CREATE_EXTERNAL_LOCATION`, and `CREATE_STORAGE_CREDENTIAL` grants on the metastore before it can create catalogs.

### Full Private Link: Route 53 scoping

Route 53 private hosted zones must be scoped to the workspace FQDN only (e.g., `dbc-xxx.cloud.databricks.com`), NOT the entire `cloud.databricks.com` domain. Otherwise, OAuth token requests to `accounts.cloud.databricks.com` get intercepted and auth breaks.

### Full Private Link: PAS immutability

Private Access Settings (PAS) cannot be modified after creation. To change `public_access_enabled`, create a new PAS and update the workspace to use it. Workspace re-provisioning takes 1-2 minutes when switching PAS.

## Default Network Posture

Recommend a custom VPC with Secure Cluster Connectivity as the default:
- VPC with 2 private subnets (one per AZ)
- NAT gateway for outbound internet
- S3 VPC gateway endpoint
- Security group allowing internal traffic only
- No public IP on cluster nodes

## AWS Template Patterns

| Pattern | When to Use |
|---------|-------------|
| `aws-workspace-basic` | Getting started — VPC + IAM + S3 + workspace |
| `aws-workspace-full` | Production with UC in a single deploy |
| `aws-workspace-privatelink` | Backend private link (cluster-to-control-plane stays private) |
| `aws-workspace-full-privatelink` | Full private link (frontend + backend), transit VPC, Route 53 |
| `aws-unity-catalog` | Adding UC to an existing workspace |

## Reference Repos

Fetch from these at runtime for AWS Terraform patterns:
- `https://github.com/databricks/terraform-databricks-sra` — AWS section for SRA-compliant patterns (VPC, IAM, CMK, log delivery)
- `https://github.com/databricks/terraform-databricks-examples` — AWS examples for workspaces, UC, private link, networking

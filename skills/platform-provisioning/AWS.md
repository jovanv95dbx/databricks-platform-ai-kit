# AWS Platform Provisioning

Cloud-specific guidance for provisioning Databricks workspaces on AWS.

## Authentication

### Check current auth state

```bash
aws sts get-caller-identity  # account ID, IAM user/role ARN
env | grep -i DATABRICKS  # check for conflicting env vars
cat ~/.databrickscfg 2>/dev/null  # check for DEFAULT profile conflicts
```

### Required credentials

- **AWS CLI session**: IAM user credentials (`aws configure`), SSO session (`aws sso login`), or exported environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN).
- **Databricks Account ID**: From the Databricks accounts console (accounts.cloud.databricks.com). Ask the customer if not known.
- **Databricks account-level credentials**: Either a Databricks account admin user (email/password) or a service principal with account admin role. Needed for the Databricks provider to create MWS workspaces.

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

After workspace creation, a second Databricks provider targets the workspace:

```hcl
provider "databricks" {
  alias = "workspace"
  host  = databricks_mws_workspaces.this.workspace_url
  token = databricks_mws_workspaces.this.token[0].token_value
}
```

**GOTCHA: Azure SP credentials do NOT work on AWS.** Azure (accounts.azuredatabricks.net) and AWS (accounts.cloud.databricks.com) are completely separate account consoles with separate service principals. Always verify which account console credentials are being used.

## Gotchas

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

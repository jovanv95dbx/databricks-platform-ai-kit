# GCP Platform Provisioning

Cloud-specific guidance for provisioning Databricks workspaces on GCP.

## Authentication

### Check current auth state

```bash
gcloud auth list  # active account
gcloud config get-value project  # active project
gcloud auth application-default print-access-token >/dev/null 2>&1 && echo "ADC configured" || echo "No ADC"
env | grep -i DATABRICKS  # check for conflicting env vars
```

### Required credentials

- **Google Cloud CLI session**: `gcloud auth login` for user auth, or `gcloud auth application-default login` for Application Default Credentials (ADC). Terraform uses ADC.
- **GCP project**: The project where Databricks resources will be created. Verify with `gcloud config get-value project`.
- **Databricks Account ID**: From the Databricks accounts console (accounts.gcp.databricks.com). Ask the customer if not known.
- **Databricks account-level credentials**: Account admin user or service principal for the Databricks provider to create MWS workspaces.

### Service account setup (for CI/CD or non-interactive use)

```bash
# Create service account
gcloud iam service-accounts create databricks-deployer \
  --display-name="Databricks Terraform Deployer"

# Grant required roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:databricks-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/owner"

# Create and download key
gcloud iam service-accounts keys create key.json \
  --iam-account=databricks-deployer@$PROJECT_ID.iam.gserviceaccount.com

export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/key.json"
```

### Provider configuration

GCP templates use two providers:

```hcl
provider "google" {
  project = var.google_project
  region  = var.region
}

provider "databricks" {
  alias      = "mws"
  host       = "https://accounts.gcp.databricks.com"
  account_id = var.databricks_account_id
}
```

After workspace creation:

```hcl
provider "databricks" {
  alias = "workspace"
  host  = databricks_mws_workspaces.this.workspace_url
}
```

## Gotchas

### GKE-based architecture

Databricks on GCP runs on GKE (Google Kubernetes Engine), not raw VMs like Azure/AWS. This means:
- Workspace creation provisions a GKE cluster, which takes 10-15 minutes
- Node pools are managed by Databricks, but network configuration affects GKE networking
- Firewall rules must account for GKE master-to-node communication

### Pod and service CIDR requirements for BYOVPC

When using Bring Your Own VPC, you must provide secondary IP ranges for GKE pods and services:
- **Pod CIDR**: /16 recommended (e.g., 10.100.0.0/16) -- must be large enough for cluster autoscaling
- **Service CIDR**: /20 recommended (e.g., 10.200.0.0/20)
- These are configured as secondary ranges on the subnet, not as separate subnets
- The primary subnet range is for GKE nodes

### Private Google Access

The subnet used for Databricks must have Private Google Access enabled. Without it, nodes cannot reach Google APIs and workspace creation fails.

### API enablement

The following APIs must be enabled on the GCP project before deploying:
- `compute.googleapis.com`
- `container.googleapis.com`
- `storage.googleapis.com`
- `iam.googleapis.com`

Check with: `gcloud services list --enabled --filter="NAME:(compute OR container OR storage OR iam)"`

## Default Network Posture

Recommend GCP-managed VPC as the default for getting started. For production, recommend BYOVPC with:
- Custom VPC with a single subnet
- Secondary IP ranges for pods and services
- Cloud NAT for outbound internet access
- Private Google Access enabled on the subnet
- Firewall rules restricting ingress

This corresponds to the `gcp-workspace-byovpc` template.

## GCP Template Patterns

| Pattern | When to Use |
|---------|-------------|
| `gcp-workspace-basic` | Getting started — GCS bucket + workspace with GCP-managed VPC |
| `gcp-workspace-byovpc` | Production — custom VPC + Cloud NAT + subnet control |
| `gcp-unity-catalog` | Adding UC to an existing workspace |

## Reference Repos

Fetch from these at runtime for GCP Terraform patterns:
- `https://github.com/databricks/terraform-databricks-examples` — GCP examples for workspaces, UC, BYOVPC

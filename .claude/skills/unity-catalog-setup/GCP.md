# Unity Catalog on GCP

GCP-specific patterns, resources, and gotchas for Unity Catalog setup.

## GCS Bucket Setup

One GCS bucket for the metastore root storage, plus one per environment for per-env catalogs.

```hcl
resource "google_storage_bucket" "metastore" {
  name          = "${var.prefix}-uc-metastore"
  project       = var.google_project
  location      = var.google_region
  force_destroy = true
}
```

**Metastore storage root format:**
```
gs://<bucket-name>
```

**Per-env catalog storage:**
```
gs://<prefix>-catalog-dev/
gs://<prefix>-catalog-stg/
gs://<prefix>-catalog-prod/
```

## Auto-Generated Service Account

GCP UC uses a Databricks-managed service account that is auto-generated when you create the metastore data access credential. You do not create an IAM role manually -- Databricks provisions a GCP service account for you.

```hcl
resource "databricks_metastore_data_access" "this" {
  provider     = databricks.workspace
  metastore_id = databricks_metastore.this.id
  name         = "${var.prefix}-data-access"
  is_default   = true

  databricks_gcp_service_account {}
}
```

After creation, grant the auto-generated SA access to the metastore GCS bucket:

```hcl
resource "google_storage_bucket_iam_member" "metastore_admin" {
  bucket = google_storage_bucket.metastore.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${databricks_metastore_data_access.this.databricks_gcp_service_account[0].email}"
}

resource "google_storage_bucket_iam_member" "metastore_reader" {
  bucket = google_storage_bucket.metastore.name
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:${databricks_metastore_data_access.this.databricks_gcp_service_account[0].email}"
}
```

The auto-generated SA email is only available after the `databricks_metastore_data_access` resource is created, so the IAM bindings must depend on it.

## Storage Credential for External Catalogs

For per-env catalogs with dedicated storage, create a separate storage credential. This also auto-generates a GCP service account:

```hcl
resource "databricks_storage_credential" "this" {
  provider = databricks.workspace
  name     = "${var.prefix}-storage-credential"

  databricks_gcp_service_account {}
}
```

Grant this SA `roles/storage.objectAdmin` and `roles/storage.legacyBucketReader` on each catalog bucket, then create external locations and catalogs with `MANAGED LOCATION`.

## Per-Environment Catalog Pattern

```hcl
resource "google_storage_bucket" "catalog_dev" {
  name     = "${var.prefix}-catalog-dev"
  project  = var.google_project
  location = var.google_region
}

resource "google_storage_bucket_iam_member" "catalog_dev_admin" {
  bucket = google_storage_bucket.catalog_dev.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${databricks_storage_credential.this.databricks_gcp_service_account[0].email}"
}

resource "databricks_external_location" "dev" {
  provider        = databricks.workspace
  name            = "${var.prefix}-catalog-dev"
  url             = "gs://${google_storage_bucket.catalog_dev.name}/"
  credential_name = databricks_storage_credential.this.name
}

resource "databricks_catalog" "dev" {
  provider       = databricks.workspace
  name           = "dev"
  storage_root   = "gs://${google_storage_bucket.catalog_dev.name}/"
  isolation_mode = "OPEN"
}
```

## GCP Gotchas

**Metastore data access requires workspace provider.** Unlike Azure and AWS where metastore data access uses the account provider, GCP requires the workspace provider for `databricks_metastore_data_access` because of the auto-generated SA flow. The metastore must be assigned to a workspace first.

**Two service accounts are generated.** One for the metastore data access (default credential) and one for the storage credential (external locations). They are different SAs with different emails. Grant bucket access to the correct one.

**SA email not available until after creation.** The auto-generated SA email is an output of the resource, so IAM bindings on GCS buckets must use `depends_on` or reference the SA email attribute directly (Terraform handles the dependency automatically when you reference the attribute).

**Simpler than Azure/AWS.** No IAM role trust policies, no access connectors, no managed identity role assignments. The auto-generated SA pattern handles most of the complexity. The main manual step is granting GCS bucket IAM roles to the auto-generated SAs.

**Account-level groups.** Same as other clouds -- create groups via SCIM API at `accounts.gcp.databricks.com/api/2.0/accounts/{id}/scim/v2/Groups`. These are visible across all workspaces via UC identity federation.

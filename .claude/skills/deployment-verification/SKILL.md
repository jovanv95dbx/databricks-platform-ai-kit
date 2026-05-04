---
name: databricks-deployment-verification
description: "MANDATORY post-deployment verification. After any workspace + Unity Catalog deployment, you MUST run all THREE compute paths against a UC table — classic cluster, serverless SQL warehouse, serverless notebook job. Skipping any of the three is incomplete work. Use whenever a workspace + UC has been freshly deployed or modified."
---

# Deployment Verification — THE THREE PATHS RULE

> **STOP. Before declaring any workspace "deployed" or "verified", you MUST run all three of:**
>
> 1. **Classic cluster** with UC (`data_security_mode = "SINGLE_USER"`)
> 2. **Serverless SQL warehouse** (PRO)
> 3. **Serverless notebook job** (ephemeral job compute)
>
> Each must read AND write a UC table end-to-end (CREATE → INSERT → SELECT → DROP).
>
> One success on serverless does NOT count as verified. Classic must work too — that's where most real-world skill bugs live (cluster policies, init scripts, custom AMIs, SCC/PrivateLink port story, JVM warmup interactions with private storage, `data_security_mode` enforcement). If you only test serverless you're testing the easy path.

## Why this is its own skill

Deployment verification is the most-skipped step in every platform stress test. Agents reach for the cheapest path (serverless SQL) because it's the fastest and the cluster cold-start warning in `workspace-config` discourages classic. Result: skill gaps that only surface on classic clusters never get caught until a real customer hits them in prod. **This skill exists to make verification impossible to forget and impossible to half-do.**

## The Three Paths

### Path 1 — Classic cluster (UC-enabled)

The most informative test. Surfaces:
- Cluster policy correctness (`data_security_mode`, `single_user_name`, allowed instance types)
- IAM role / managed identity propagation to the cluster
- UC metastore + external location + storage credential resolution from worker nodes
- Init scripts and custom AMIs (if used by persona)
- SCC relay + private networking (workers reach control plane on TCP 443)
- Workspace-level secret scopes if used in Spark conf
- DBFS root encryption (CMK on managed disks for HIGH personas)

**Minimum cluster spec:**

```hcl
resource "databricks_cluster" "verify_classic" {
  cluster_name            = "verify-classic-${var.workspace_name}"
  spark_version           = data.databricks_spark_version.lts.id  # latest LTS
  node_type_id            = data.databricks_node_type.smallest.id  # cloud-specific
  num_workers             = 1   # NOT autoscaled — keep deterministic
  autotermination_minutes = 0   # CRITICAL: 0 = no auto-terminate during JVM warmup
                                # If you set 30, on a fresh workspace the cluster can
                                # reach RUNNING but stay in "Starting Spark" past the
                                # 30-min window → terminates before any job attaches →
                                # infinite restart loop. Set 0 for verify clusters and
                                # destroy them explicitly at end (cleanup section).
  data_security_mode      = "SINGLE_USER"   # required for UC table reads
  single_user_name        = var.verifier_principal  # for an SP, this is the SP's
                                                    # application_id (UUID) — NOT the
                                                    # numeric SP id. For a user, the
                                                    # email. For a group, the group name.

  # Tag so it can be identified + cleaned up
  custom_tags = {
    purpose = "deployment-verification"
    persona = var.persona_name
  }
}
```

**Expected timing:** 10–15 min cold-start on a brand-new workspace (JVM warmup + UC metadata cache + storage credential resolution). The skill warning about classic cold-start is REAL but it's not an excuse to skip the test — it's a reason to start the cluster early in your deploy and verify near the end.

**SQL test (run via `databricks api post /api/2.0/sql/statements` against the cluster, OR notebook task on the cluster):**

```sql
-- Replace catalog/schema with the catalog you just deployed
CREATE TABLE <catalog>.<schema>.verify_classic (id INT, msg STRING);
INSERT INTO <catalog>.<schema>.verify_classic VALUES (1, 'classic verified');
SELECT * FROM <catalog>.<schema>.verify_classic;
DROP TABLE <catalog>.<schema>.verify_classic;
```

**Pass criteria:** all four statements succeed. SELECT must return exactly the row inserted. If any fails: do NOT mark verified. Diagnose, fix, retry.

**Hard-failure modes to watch for:**

| Symptom | Likely root cause |
|---|---|
| Cluster stuck in "Pending" >20 min | IAM role propagation, instance profile attached but not yet readable |
| Cluster started but SQL fails with "credential not found" | UC IAM policy missing `s3:ListBucketMultipartUploads` family (AWS) or DES managed identity not granted Get/UnwrapKey on Key Vault (Azure CMK) |
| `data_security_mode=SINGLE_USER` rejected | Cluster policy is too restrictive; relax `data_security_mode` constraint |
| Cluster started but timed out fetching control-plane | SCC over PrivateLink misconfigured (AWS) or NSG/firewall rules wrong (Azure) — see private-networking skill |
| AWS only: workers can't reach S3 | Missing `s3:GetBucketTagging` or `s3:GetBucketAcl` on the UC IAM policy (often missing from older skill examples) |
| Azure only: spark fails reading UC managed table | DES (Disk Encryption Set) managed identity missing Key Vault access policy |

### Path 2 — Serverless SQL warehouse (PRO)

Fastest verification. Tests UC + serverless + storage credential resolution from the serverless plane (different from classic — different network egress, different identity).

**Minimum warehouse spec:**

```hcl
resource "databricks_sql_endpoint" "verify_serverless" {
  name                  = "verify-serverless"
  cluster_size          = "2X-Small"   # smallest serverless size
  enable_serverless_compute = true
  warehouse_type        = "PRO"        # PRO required for UC-aware features
  auto_stop_mins        = 10
  tags { custom_tags { key = "purpose" value = "deployment-verification" } }
}
```

**Pass criteria:** same four-statement CRUD as Path 1 succeeds. **CRITICAL:** the Statement Execution API (`/api/2.0/sql/statements`) does NOT accept multi-statement bodies — it returns `PARSE_SYNTAX_ERROR: Syntax error at or near 'CREATE': extra input 'CREATE'`. You MUST split into 4 separate calls:

```bash
WS_PROFILE=<workspace-profile>
WAREHOUSE_ID=<id>
TABLE="<catalog>.<schema>.verify_serverless"

for STMT in \
  "CREATE TABLE $TABLE (id INT, msg STRING)" \
  "INSERT INTO $TABLE VALUES (2, 'serverless verified')" \
  "SELECT * FROM $TABLE" \
  "DROP TABLE $TABLE" ; do
  databricks api post /api/2.0/sql/statements \
    --profile "$WS_PROFILE" \
    --json "{\"warehouse_id\": \"$WAREHOUSE_ID\", \"statement\": $(jq -Rs . <<< "$STMT"), \"wait_timeout\": \"30s\"}" \
    || { echo "FAIL on: $STMT"; exit 1; }
done
```

The third call (SELECT) must return one row containing `[2, "serverless verified"]`.

**Hard-failure modes:**

| Symptom | Likely root cause |
|---|---|
| Warehouse fails to start | Serverless not enabled on the workspace OR region doesn't support serverless |
| SQL fails with storage error | Storage account firewall (Azure) blocking serverless egress — needs trusted-services exception OR private endpoint to managed storage |
| Warehouse PROVISIONING but never STARTING | Account-level entitlement for serverless missing |

### Path 3 — Serverless notebook job (ephemeral job compute)

Tests the **third** compute plane: serverless job compute. This is structurally different from both Path 1 (classic) and Path 2 (serverless SQL) because:
- Different identity context (job runs as the runner / SP, not as cluster owner)
- Different egress (different network path than serverless SQL warehouse)
- Tests notebook → UC table flow (different code path than SQL warehouse → UC table)

**Minimum job spec — MUST be a Python notebook with `dbutils.notebook.exit(...)`.** SQL notebooks don't surface SELECT results through the run-output API, so the verifier can't programmatically confirm the row was returned.

```hcl
resource "databricks_notebook" "verify_notebook" {
  path     = "/Shared/verify_notebook"
  language = "PYTHON"
  content_base64 = base64encode(<<-EOT
    # Databricks notebook source
    catalog, schema = "<catalog>", "<schema>"
    table = f"{catalog}.{schema}.verify_notebook"
    spark.sql(f"CREATE TABLE {table} (id INT, msg STRING)")
    spark.sql(f"INSERT INTO {table} VALUES (3, 'notebook verified')")
    rows = [r.asDict() for r in spark.sql(f"SELECT * FROM {table}").collect()]
    spark.sql(f"DROP TABLE {table}")
    dbutils.notebook.exit(str(rows))   # surfaces in run-output as notebook_output.result
  EOT
  )
}

resource "databricks_job" "verify_notebook" {
  name = "verify-notebook"
  task {
    task_key = "verify"
    notebook_task { notebook_path = databricks_notebook.verify_notebook.path }
    # No cluster spec — uses serverless job compute by default
  }
}
```

Then trigger and wait. **CRITICAL:** when you submit a job via `runs/submit` or trigger one via `run-now`, the API returns the OUTER run id, but `runs/get-output` errors with `"Retrieving the output of runs with multiple tasks is not supported"` if you query the outer id directly — even when there's only one task. You must extract the task-level run id first:

```bash
WS_PROFILE=<workspace-profile>
JOB_ID=<job-id>

# 1. Trigger
RUN_ID=$(databricks jobs run-now --job-id "$JOB_ID" --profile "$WS_PROFILE" | jq -r '.run_id')

# 2. Wait for SUCCESS (poll runs/get every 10s until life_cycle_state == TERMINATED)
while :; do
  STATUS=$(databricks api get /api/2.1/jobs/runs/get --profile "$WS_PROFILE" --json "{\"run_id\": $RUN_ID}")
  LCS=$(echo "$STATUS" | jq -r '.state.life_cycle_state')
  RES=$(echo "$STATUS" | jq -r '.state.result_state')
  [ "$LCS" = "TERMINATED" ] && break
  sleep 10
done
[ "$RES" = "SUCCESS" ] || { echo "FAIL: $RES"; exit 1; }

# 3. Extract task-level run id (NOT the outer RUN_ID)
TASK_RUN_ID=$(echo "$STATUS" | jq -r '.tasks[0].run_id')

# 4. Get notebook output via the TASK run id
OUT=$(databricks api get /api/2.1/jobs/runs/get-output --profile "$WS_PROFILE" \
        --json "{\"run_id\": $TASK_RUN_ID}" | jq -r '.notebook_output.result')

# OUT should equal the str(rows) from dbutils.notebook.exit, e.g. "[{'id': 3, 'msg': 'notebook verified'}]"
echo "$OUT" | grep -q "notebook verified" || { echo "FAIL: output didn't match"; exit 1; }
```

**Pass criteria:** outer run state = TERMINATED/SUCCESS AND `notebook_output.result` from the task-level run id contains `notebook verified`.

**Hard-failure modes:**

| Symptom | Likely root cause |
|---|---|
| Job stuck in `PENDING_QUEUE` | Serverless compute capacity issue or workspace-level serverless not enabled |
| Job FAILED with permission error on UC | The job runs as the workspace creator (you) — but the catalog/schema may have been granted only to a group. Either run as SP that's in the group OR grant the runner directly. |
| Notebook fails on `CREATE TABLE` | Same UC IAM/identity issue as Path 1 — surface here means it's a write-path issue not a compute-path issue |

## The Verification Workflow (mandatory)

Run these phases at the END of every workspace + UC deployment, in this order:

```
1. Verify all three paths PASS         → workspace is verified
2. If any path FAILS                   → diagnose, fix, RE-RUN ALL THREE
3. Save verification artifacts         → see "What to save" below
4. Update transcript with PASS/FAIL    → per path
```

**What to save (in the deployment dir):**

- `verification.tf` — the three resources defined above (cluster, warehouse, notebook+job)
- `verification.log` — output of each SQL statement, exit codes, durations
- `verification.json` — structured pass/fail per path:
  ```json
  {
    "classic":    {"status": "PASS|FAIL", "duration_s": 720, "cluster_id": "0503-...", "error": null},
    "serverless": {"status": "PASS|FAIL", "duration_s": 8,   "warehouse_id": "...",    "error": null},
    "notebook":   {"status": "PASS|FAIL", "duration_s": 45,  "job_id": "...", "run_id": "...", "error": null}
  }
  ```

## When to skip (NARROW exceptions)

You may skip a path ONLY if:

- **Skip classic** — only when the customer **explicitly** requires no classic compute (regulated workloads, serverless-only mandate) or the workspace tier doesn't support classic (rare). Log the reason in `verification.json` with `"status": "SKIPPED-WITH-REASON"`. Do NOT skip classic just because cold-start is slow.
- **Skip serverless** — only when the customer explicitly forbids serverless (regulated FSI / banking with no serverless approval) AND the workspace genuinely does not have serverless enabled. Log the reason.
- **Skip notebook job** — only when serverless job compute is not available in the region. (Rare today.) Log the reason.

**Default: run all three.** "Took too long" / "use case is serverless-first" / "POC scope" are NOT valid reasons. The point of verification is to find configuration gaps, not to validate the customer's preferred path.

### What to do when verification surfaces a cloud-account problem (not a deploy bug)

If a verification path FAILS due to a customer-account constraint — service quota exhausted, regional capacity unavailable for the chosen node type, missing org-policy approval, etc. — do NOT mark it SKIPPED-WITH-REASON and move on. Treat it the same as any quota error during deploy:

1. Stop verification.
2. Identify the constraint precisely (which AWS/Azure quota, which org policy, which approval is missing).
3. Tell the customer: what's blocking, where to fix it (Service Quotas page, IT ticket, etc.), and that verification will resume once cleared.
4. Re-run all three paths once the customer has cleared it.

The verify cluster hanging in `Starting Spark` for 30+ minutes is almost always either a customer EC2/VM capacity issue OR the JVM-warmup-vs-autotermination race (see `platform-provisioning/AWS.md` and `AZURE.md`). Diagnose which before declaring verification "blocked".

## Cleanup

After PASS:

```bash
# Drop verify objects (idempotent — they were already DROPped per-path, but kill the resources)
terraform destroy -target=databricks_cluster.verify_classic
terraform destroy -target=databricks_sql_endpoint.verify_serverless
terraform destroy -target=databricks_job.verify_notebook
terraform destroy -target=databricks_notebook.verify_notebook
```

Or leave them in place if the customer wants the warehouses/clusters for ongoing work — but tag them clearly with `purpose=deployment-verification` so they can be found.

## How this skill is referenced from other skills

- `platform-provisioning/SKILL.md` — references this as the mandatory final step after workspace deployment.
- `workspace-config/SKILL.md` — references this when deploying or modifying SQL warehouses, cluster policies, or job compute.
- Stress-test spawn prompts — reference this skill explicitly. If a stress-test agent reports "verified" without all three paths, the run is incomplete.

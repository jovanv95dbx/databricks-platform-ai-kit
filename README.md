# Databricks Platform Kit v2

**AI-powered Databricks platform engineering.** Provision workspaces, configure Unity Catalog, set up networking, manage groups and permissions — all through natural language with Claude.

## What it does

Tell Claude what you need, and it handles the rest:

- **Workspace provisioning** — VNet injection, Secure Cluster Connectivity across Azure, AWS, GCP
- **Unity Catalog** — opinionated setup: self-managed metastore, per-env catalogs, external locations, medallion schemas
- **Identity & governance** — account-level SCIM groups, tiered RBAC, service principals for jobs
- **Workspace config** — SQL warehouses, cluster policies, secret scopes, IP access lists
- **Private networking** — private link, hub-spoke, NCC for serverless connectivity (when you need it)
- **Built-in verification** — 3 parallel test notebooks (classic cluster, SQL warehouse, serverless) confirm everything works

Claude writes the Terraform and SDK calls from scratch based on your specific requirements — no rigid templates to fill in.

## Architecture

```
skills/                              # 5 focused skills (the main product)
  platform-provisioning/             #   Workspace creation + deploy
    SKILL.md                         #     Shared workflow + interaction guidance
    AZURE.md / AWS.md / GCP.md       #     Cloud-specific patterns + gotchas
  unity-catalog-setup/               #   Metastore, catalogs, governance
    SKILL.md + AZURE.md / AWS.md / GCP.md
  identity-governance/               #   Groups, users, SPs, RBAC
    SKILL.md                         #     Cloud-agnostic
  workspace-config/                  #   SQL warehouses, policies, secrets
    SKILL.md                         #     Cloud-agnostic
  private-networking/                #   Private link, hub-spoke, NCC
    SKILL.md + AZURE.md / AWS.md

```

Claude uses `az login` / `aws configure` / `gcloud auth login` + `terraform` via shell. No Python dependencies, no MCP server — just skills.

## Install

```bash
./install.sh
```

### Prerequisites

- **Terraform** >= 1.9.0: `brew install terraform`
- **Cloud CLI**: `az login` (Azure), `aws configure` (AWS), or `gcloud auth login` (GCP)
- **Databricks account**: Account ID from the accounts console

## Usage

Just tell Claude what you want:

> "Set up 3 Databricks workspaces (dev/stg/prod) on Azure with Unity Catalog and proper groups"

Claude will:
1. Ask the right questions (cloud, region, environment strategy)
2. Check your auth and gather inputs
3. Write Terraform tailored to your request
4. Deploy end-to-end
5. Offer to verify with parallel test notebooks

## Skills

| Skill | What it does | When it loads |
|-------|-------------|---------------|
| **platform-provisioning** | Create workspaces, deploy infrastructure | "create a workspace", "provision", "deploy" |
| **unity-catalog-setup** | Metastore, catalogs, schemas, grants | "Unity Catalog", "metastore", "catalog" |
| **identity-governance** | Groups, users, SPs, RBAC | "groups", "permissions", "service principal" |
| **workspace-config** | SQL warehouses, policies, secrets, tokens | "SQL warehouse", "cluster policy", "secret" |
| **private-networking** | Private link, hub-spoke, NCC | "private link", "hub-spoke", "NCC" |

Each skill loads independently — Claude only reads what's relevant to your request. Cloud-specific files (AZURE.md, AWS.md, GCP.md) are loaded based on your target cloud to prevent cross-cloud confusion.

## Supported clouds

| Cloud | Workspaces | Unity Catalog | Private Link | Multi-env |
|-------|-----------|---------------|-------------|-----------|
| Azure | Yes | Yes | Yes | Yes |
| AWS   | Yes | Yes | Yes | Yes |
| GCP   | Yes | Yes | N/A | Planned |

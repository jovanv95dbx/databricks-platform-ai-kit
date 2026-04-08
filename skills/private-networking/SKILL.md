---
name: databricks-private-networking
description: "Set up private networking for Databricks. Use when the user asks about private link, hub-spoke architecture, NCC (Network Connectivity Configuration), serverless connectivity to private resources, VPC endpoints, or private endpoints."
---

# Databricks Private Networking

## How to interact with the customer

Apply MODERATE pushback -- private networking adds significant complexity and ongoing maintenance burden.

- **"I need private link" without scope** -- you must ask: "Backend-only (cluster traffic private, UI/API still public) or full private link (everything private, requires VPN/ExpressRoute/DirectConnect to access UI and API)?"
- **Full private link without VPN/private connectivity** -- warn once: "With full private link, the workspace UI and API are only accessible from inside the private network. You will need VPN, ExpressRoute, or DirectConnect to reach the workspace. Are you sure?"
- **Clear spec with backend-only or full PL and VPN confirmed** -- just do it. No further pushback.

## When do you need this?

Not every deployment needs private link. Match the solution to the actual requirement.

- **Default (VNet/VPC injection + SCC)** is sufficient for most workloads. Cluster nodes have no public IPs, traffic to the control plane goes through a secure tunnel. This is already production-grade for most compliance frameworks.
- **Private link** is needed when: compliance explicitly requires no public endpoints, the organization operates a zero-trust network, or security policy prohibits any traffic traversing the public internet.
- **NCC (Network Connectivity Configuration)** is needed when: serverless compute must connect to private or on-premises resources (private databases, internal APIs, storage behind firewalls). Classic clusters running in a VNet/VPC can reach VNet-peered or VPC-peered resources directly -- they do not need NCC.

## Network baselines per cloud

The minimum recommended baseline for any production deployment is VNet/VPC injection with Secure Cluster Connectivity (no_public_ip enabled). This gives you private compute nodes without the operational complexity of private link.

Once you know the customer's cloud, read the cloud-specific file for architecture patterns, step-by-step deployment guides, and gotchas:

- **Azure** -- read AZURE.md for private link patterns (single workspace, hub-spoke), NCC setup, and Azure-specific DNS and networking gotchas.
- **AWS** -- read AWS.md for VPC endpoint patterns (backend-only, full frontend+backend), NCC setup, and AWS-specific IAM and routing gotchas.
- **GCP** -- GCP does not have private link support yet. Use VPC injection with SCC as the maximum network isolation available.

## Cross-links

- For workspace creation and infrastructure provisioning, see **platform-provisioning**.
- For Unity Catalog setup after workspace is provisioned, see **unity-catalog-setup**.

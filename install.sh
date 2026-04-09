#!/usr/bin/env bash
set -euo pipefail

# Databricks Platform Kit v2 installer
# Installs skills for Claude Code

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Install Databricks Platform Kit v2 for Claude Code.

Options:
  --global         Install to global Claude Code settings (~/.claude/)
                   instead of project-level (.claude/ in current directory).
  --force          Overwrite existing installation without prompting.
  -h, --help       Show this help message.

Examples:
  ./install.sh                    # Install skills to current project
  ./install.sh --global           # Install globally for all projects
  ./install.sh --force            # Overwrite existing skills
EOF
  exit 0
}

GLOBAL=false
FORCE=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --global)      GLOBAL=true; shift ;;
    --force)       FORCE=true; shift ;;
    -h|--help)     usage ;;
    *)             error "Unknown option: $1" ;;
  esac
done

# Determine Claude Code settings directory
if $GLOBAL; then
  CLAUDE_DIR="$HOME/.claude"
else
  CLAUDE_DIR="$(pwd)/.claude"
fi

CLAUDE_SKILLS_DIR="$CLAUDE_DIR/skills"

# --- Skills Installation ---

info "Installing Platform Kit v2 skills..."
mkdir -p "$CLAUDE_SKILLS_DIR"

for skill_dir in "$SKILLS_DIR"/*/; do
  skill_name=$(basename "$skill_dir")
  target="$CLAUDE_SKILLS_DIR/$skill_name"

  if [[ -d "$target" ]] && ! $FORCE; then
    warn "Skill '$skill_name' already exists. Use --force to overwrite."
    continue
  fi

  rm -rf "$target"
  cp -r "$skill_dir" "$target"
  info "  Installed skill: $skill_name"
done

# --- Verify ---

info ""
info "Installation complete!"
info ""
info "Skills installed to: $CLAUDE_SKILLS_DIR"
info ""
info "  5 skills installed:"
info "    platform-provisioning  — Create workspaces + deploy infrastructure"
info "    unity-catalog-setup    — Metastore, catalogs, schemas, governance"
info "    identity-governance    — Groups, users, SPs, RBAC"
info "    workspace-config       — SQL warehouses, policies, secrets, tokens"
info "    private-networking     — Private link, hub-spoke, NCC patterns"
info ""
info "Claude can now provision Databricks infrastructure using Terraform"
info "via shell commands."

# Check for Terraform
if ! command -v terraform &>/dev/null; then
  warn ""
  warn "Terraform is not installed. Install it with: brew install terraform"
fi

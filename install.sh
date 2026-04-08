#!/usr/bin/env bash
set -euo pipefail

# Databricks Platform Kit v2 installer
# Installs skills and optionally the MCP server for Claude Code

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills"
MCP_SERVER_DIR="$SCRIPT_DIR/mcp-server"
CORE_DIR="$SCRIPT_DIR/core"

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
  --skills-only    Install skills only (no MCP server). Claude writes
                   Terraform from scratch using skill knowledge + shell.
  --global         Install to global Claude Code settings (~/.claude/)
                   instead of project-level (.claude/ in current directory).
  --force          Overwrite existing installation without prompting.
  -h, --help       Show this help message.

Examples:
  ./install.sh                    # Full install (skills + MCP server)
  ./install.sh --skills-only      # Lightweight install
  ./install.sh --global           # Install globally for all projects
EOF
  exit 0
}

SKILLS_ONLY=false
GLOBAL=false
FORCE=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --skills-only) SKILLS_ONLY=true; shift ;;
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
CLAUDE_SETTINGS="$CLAUDE_DIR/settings.json"

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

# --- MCP Server Installation ---

if ! $SKILLS_ONLY; then
  info "Installing MCP server..."

  # Check Python
  PYTHON=""
  for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
      PYTHON="$cmd"
      break
    fi
  done
  [[ -z "$PYTHON" ]] && error "Python 3 is required. Install it and try again."

  # Install core library
  info "  Installing core library..."
  (cd "$CORE_DIR" && $PYTHON -m pip install -e ".[all]" --quiet 2>&1 | tail -1)

  # Install MCP server
  info "  Installing MCP server..."
  (cd "$MCP_SERVER_DIR" && $PYTHON -m pip install -e . --quiet 2>&1 | tail -1)

  # Register MCP server in Claude Code settings
  info "  Registering MCP server in Claude Code settings..."
  mkdir -p "$CLAUDE_DIR"

  if [[ -f "$CLAUDE_SETTINGS" ]]; then
    $PYTHON -c "
import json, sys
settings_path = '$CLAUDE_SETTINGS'
with open(settings_path) as f:
    settings = json.load(f)
mcp = settings.setdefault('mcpServers', {})
mcp['databricks-platform'] = {
    'command': '$PYTHON',
    'args': ['-m', 'databricks_platform_mcp'],
    'env': {}
}
with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)
"
  else
    cat > "$CLAUDE_SETTINGS" <<SETTINGS
{
  "mcpServers": {
    "databricks-platform": {
      "command": "$PYTHON",
      "args": ["-m", "databricks_platform_mcp"],
      "env": {}
    }
  }
}
SETTINGS
  fi

  info "  MCP server registered."
fi

# --- Verify ---

info ""
info "Installation complete!"
info ""
if $SKILLS_ONLY; then
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
  info "via shell commands. No MCP server needed."
else
  info "Skills installed to: $CLAUDE_SKILLS_DIR"
  info "MCP server registered in: $CLAUDE_SETTINGS"
  info ""
  info "Restart Claude Code to activate the MCP server."
fi

# Check for Terraform
if ! command -v terraform &>/dev/null; then
  warn ""
  warn "Terraform is not installed. Install it with: brew install terraform"
fi

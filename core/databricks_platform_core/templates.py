"""
Terraform template discovery and management.

Locates bundled Terraform templates in the databricks-platform-kit repo's
terraform-templates/ directory.
"""

import json
from pathlib import Path


def get_templates_dir() -> Path:
    """
    Get the path to the bundled terraform-templates/ directory.

    The templates are at the repo root: <repo>/terraform-templates/
    This module is at: <repo>/core/databricks_platform_core/templates.py
    So we navigate 2 levels up to the repo root.

    Returns:
        Path to the terraform-templates directory

    Raises:
        FileNotFoundError: If the templates directory is not found
    """
    # Navigate from this file to the repo root
    # This file: <repo>/core/databricks_platform_core/templates.py
    # Repo root: 2 levels up
    module_dir = Path(__file__).resolve().parent
    repo_root = module_dir.parent.parent

    templates_dir = repo_root / "terraform-templates"
    if not templates_dir.is_dir():
        # Also check common install location
        alt_dir = Path.home() / ".ai-dev-kit" / "repo" / "terraform-templates"
        if alt_dir.is_dir():
            return alt_dir
        raise FileNotFoundError(
            f"Terraform templates directory not found at {templates_dir} or {alt_dir}. "
            f"Ensure the databricks-platform-kit repo is intact."
        )
    return templates_dir


def list_templates() -> list[dict]:
    """
    List all available Terraform templates.

    Reads template.json from each subdirectory of terraform-templates/.

    Returns:
        List of template metadata dicts with keys:
        name, cloud, description, required_vars, optional_vars, outputs
    """
    templates_dir = get_templates_dir()
    templates = []

    for child in sorted(templates_dir.iterdir()):
        if not child.is_dir():
            continue
        metadata_file = child / "template.json"
        if not metadata_file.exists():
            continue
        try:
            with open(metadata_file) as f:
                metadata = json.load(f)
            templates.append(metadata)
        except (json.JSONDecodeError, OSError):
            continue

    return templates


def get_template_path(template_name: str) -> Path:
    """
    Get the full path to a named template directory.

    Args:
        template_name: Name of the template (e.g. "azure-workspace-basic")

    Returns:
        Path to the template directory

    Raises:
        ValueError: If the template is not found
    """
    templates_dir = get_templates_dir()
    template_path = templates_dir / template_name

    if not template_path.is_dir():
        available = [t["name"] for t in list_templates()]
        raise ValueError(
            f"Template '{template_name}' not found. "
            f"Available templates: {', '.join(available)}"
        )

    return template_path

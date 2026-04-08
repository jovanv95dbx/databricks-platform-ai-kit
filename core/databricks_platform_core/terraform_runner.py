"""
Terraform runner for workspace provisioning.

Manages Terraform init/plan/apply/destroy lifecycle with structured
output capture, run tracking, and secret masking.
"""

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TerraformError(Exception):
    """Raised when a Terraform operation fails."""

    def __init__(self, message: str, log: str = ""):
        self.log = log
        super().__init__(message)


# Fields that contain secrets and must be masked in metadata
_SECRET_FIELDS = {
    "client_secret", "token", "databricks_account_token",
    "secret", "password", "access_key", "secret_key",
}

_RUNS_DIR = Path.home() / ".ai-dev-kit" / "terraform-runs"


def _ensure_terraform() -> str:
    """Check that terraform binary is available. Returns the path."""
    tf_path = shutil.which("terraform")
    if not tf_path:
        raise TerraformError(
            "Terraform binary not found on PATH. "
            "Install it with: brew install terraform (macOS) or "
            "see https://developer.hashicorp.com/terraform/install"
        )
    return tf_path


def _mask_secrets(variables: dict) -> dict:
    """Return a copy of variables with secret values replaced by '***'."""
    masked = {}
    for key, value in variables.items():
        if key.lower() in _SECRET_FIELDS or "secret" in key.lower() or "token" in key.lower():
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


def _generate_run_id(workspace_name: str) -> str:
    """Generate a run ID from timestamp + workspace name slug."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9-]", "-", workspace_name.lower())[:30]
    return f"{timestamp}-{slug}"


def _write_metadata(run_dir: Path, run_id: str, template: str,
                    variables: dict, status: str, outputs: dict | None = None) -> None:
    """Write run metadata to run_metadata.json."""
    metadata = {
        "run_id": run_id,
        "template": template,
        "variables": _mask_secrets(variables),
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "outputs": outputs or {},
    }
    with open(run_dir / "run_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)


def _write_tfvars(run_dir: Path, variables: dict) -> Path:
    """Write a terraform.tfvars file from a dict of variables."""
    tfvars_path = run_dir / "terraform.tfvars"
    lines = []
    for key, value in variables.items():
        if isinstance(value, dict):
            # HCL map syntax
            items = ", ".join(f'"{k}" = "{v}"' for k, v in value.items())
            lines.append(f'{key} = {{{items}}}')
        elif isinstance(value, bool):
            lines.append(f'{key} = {str(value).lower()}')
        elif isinstance(value, (int, float)):
            lines.append(f'{key} = {value}')
        elif isinstance(value, (list, tuple)):
            # HCL list syntax
            items = ", ".join(f'"{v}"' for v in value)
            lines.append(f'{key} = [{items}]')
        else:
            # Escape any quotes in string values
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')

    tfvars_path.write_text("\n".join(lines) + "\n")
    return tfvars_path


def _run_tf_command(cmd: list[str], cwd: Path, env: dict | None = None) -> tuple[int, str]:
    """Run a terraform command and capture output."""
    full_env = os.environ.copy()

    # Remove DATABRICKS_* env vars that conflict with Terraform provider auth.
    # When these are set in the shell (e.g. from a previous OAuth M2M session),
    # the Databricks Terraform provider sees both azure-cli and oauth credentials
    # and fails with "more than one authorization method configured".
    for key in list(full_env.keys()):
        if key.startswith("DATABRICKS_"):
            del full_env[key]

    if env:
        full_env.update(env)

    # Disable interactive prompts
    full_env["TF_INPUT"] = "0"

    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=full_env,
    )
    return result.returncode, result.stdout


def run_terraform(
    template_name: str,
    variables: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Run Terraform to provision infrastructure from a template.

    1. Copies the template into a working directory
    2. Writes variables to terraform.tfvars
    3. Runs terraform init
    4. Runs terraform plan (if dry_run) or terraform apply -auto-approve
    5. Captures and parses terraform output -json

    Args:
        template_name: Name of the template (e.g. "azure-workspace-basic")
        variables: Dict of Terraform variable values
        dry_run: If True, runs plan only without applying

    Returns:
        dict with keys: status, log, outputs, run_dir, run_id
    """
    from .templates import get_template_path

    tf_bin = _ensure_terraform()

    # Resolve template
    template_path = get_template_path(template_name)

    # Create run directory
    workspace_name = variables.get("workspace_name", "unnamed")
    run_id = _generate_run_id(workspace_name)
    run_dir = _RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Copy template files into run directory
    for item in template_path.iterdir():
        if item.is_file() and item.name != "template.json":
            shutil.copy2(item, run_dir / item.name)

    # Write tfvars
    _write_tfvars(run_dir, variables)

    # Write initial metadata
    _write_metadata(run_dir, run_id, template_name, variables, "running")

    full_log = []

    # terraform init
    returncode, output = _run_tf_command(
        [tf_bin, "init", "-no-color"],
        cwd=run_dir,
    )
    full_log.append("=== terraform init ===\n" + output)
    if returncode != 0:
        log_text = "\n".join(full_log)
        _write_metadata(run_dir, run_id, template_name, variables, "failed")
        last_lines = "\n".join(output.splitlines()[-50:])
        raise TerraformError(
            f"terraform init failed (exit code {returncode}):\n{last_lines}",
            log=log_text,
        )

    if dry_run:
        # terraform plan
        returncode, output = _run_tf_command(
            [tf_bin, "plan", "-no-color", "-var-file=terraform.tfvars"],
            cwd=run_dir,
        )
        full_log.append("=== terraform plan ===\n" + output)
        log_text = "\n".join(full_log)
        status = "plan_complete" if returncode == 0 else "plan_failed"
        _write_metadata(run_dir, run_id, template_name, variables, status)

        if returncode != 0:
            last_lines = "\n".join(output.splitlines()[-50:])
            raise TerraformError(
                f"terraform plan failed (exit code {returncode}):\n{last_lines}",
                log=log_text,
            )

        return {
            "status": status,
            "log": log_text,
            "outputs": {},
            "run_dir": str(run_dir),
            "run_id": run_id,
        }

    # terraform apply
    returncode, output = _run_tf_command(
        [tf_bin, "apply", "-auto-approve", "-no-color", "-var-file=terraform.tfvars"],
        cwd=run_dir,
    )
    full_log.append("=== terraform apply ===\n" + output)

    if returncode != 0:
        log_text = "\n".join(full_log)
        _write_metadata(run_dir, run_id, template_name, variables, "failed")
        last_lines = "\n".join(output.splitlines()[-50:])
        raise TerraformError(
            f"terraform apply failed (exit code {returncode}):\n{last_lines}",
            log=log_text,
        )

    # terraform output -json
    outputs = {}
    returncode, output = _run_tf_command(
        [tf_bin, "output", "-json", "-no-color"],
        cwd=run_dir,
    )
    if returncode == 0:
        try:
            raw_outputs = json.loads(output)
            outputs = {k: v.get("value") for k, v in raw_outputs.items()}
        except json.JSONDecodeError:
            pass

    log_text = "\n".join(full_log)
    _write_metadata(run_dir, run_id, template_name, variables, "success", outputs)

    return {
        "status": "success",
        "log": log_text,
        "outputs": outputs,
        "run_dir": str(run_dir),
        "run_id": run_id,
    }


def terraform_destroy(run_id: str) -> dict[str, Any]:
    """
    Destroy infrastructure from a previous Terraform run.

    Args:
        run_id: The run ID to destroy

    Returns:
        dict with status and log
    """
    tf_bin = _ensure_terraform()

    run_dir = _RUNS_DIR / run_id
    if not run_dir.is_dir():
        raise TerraformError(f"Run directory not found: {run_id}")

    # Check that terraform state exists
    state_file = run_dir / "terraform.tfstate"
    if not state_file.exists():
        raise TerraformError(
            f"No terraform state found for run '{run_id}'. "
            f"Nothing to destroy."
        )

    returncode, output = _run_tf_command(
        [tf_bin, "destroy", "-auto-approve", "-no-color", "-var-file=terraform.tfvars"],
        cwd=run_dir,
    )

    if returncode != 0:
        last_lines = "\n".join(output.splitlines()[-50:])
        raise TerraformError(
            f"terraform destroy failed (exit code {returncode}):\n{last_lines}",
            log=output,
        )

    # Update metadata
    metadata_file = run_dir / "run_metadata.json"
    if metadata_file.exists():
        with open(metadata_file) as f:
            metadata = json.load(f)
        metadata["status"] = "destroyed"
        metadata["destroyed_at"] = datetime.now(timezone.utc).isoformat()
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)

    return {
        "status": "destroyed",
        "run_id": run_id,
        "log": output,
    }


def list_runs() -> list[dict]:
    """
    List all Terraform runs with their status and metadata.

    Returns:
        List of dicts with run_id, template, status, timestamp, outputs
    """
    if not _RUNS_DIR.is_dir():
        return []

    runs = []
    for child in sorted(_RUNS_DIR.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        metadata_file = child / "run_metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file) as f:
                    metadata = json.load(f)
                runs.append(metadata)
            except (json.JSONDecodeError, OSError):
                runs.append({
                    "run_id": child.name,
                    "status": "unknown",
                    "error": "Failed to read metadata",
                })
        else:
            runs.append({
                "run_id": child.name,
                "status": "unknown",
            })

    return runs


def get_run_outputs(run_id: str) -> dict:
    """
    Get the outputs from a specific run.

    Args:
        run_id: The run ID

    Returns:
        dict with outputs from the run
    """
    run_dir = _RUNS_DIR / run_id
    metadata_file = run_dir / "run_metadata.json"

    if not metadata_file.exists():
        return {"error": f"Run '{run_id}' not found"}

    with open(metadata_file) as f:
        metadata = json.load(f)

    return {
        "run_id": run_id,
        "status": metadata.get("status"),
        "outputs": metadata.get("outputs", {}),
    }

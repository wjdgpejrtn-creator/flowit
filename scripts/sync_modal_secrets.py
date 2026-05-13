"""Sync local .env values to Modal Secrets.

Each entry in SECRET_MAPPINGS declares one Modal Secret. The script reads
the .env file, picks the entries that are non-empty, and runs
`modal secret create <name> KEY=VALUE --force` for each. Already-existing
secrets are overwritten (--force).

Usage:
    python scripts/sync_modal_secrets.py            # sync all
    python scripts/sync_modal_secrets.py --dry-run  # show what would happen
    python scripts/sync_modal_secrets.py huggingface-token  # only one secret

Prerequisites:
    - `modal token new` already executed (or MODAL_TOKEN_ID/SECRET in .env)
    - .env file exists at repo root (see .env.example)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"

# Maps Modal Secret name → list of (env_var_in_dotenv, key_inside_modal_secret).
# Modal lets a single Secret hold multiple env vars; we keep one var per
# Secret here for clarity. Add new entries as new sub-agents need them.
# Sub-agent Modal apps connect to Cloud SQL via IAM authentication
# (cloud-sql-python-connector). Each sub-agent gets two Modal Secrets:
#   1. agent-<name>-secret   — app-specific config (LLM/Embedding URL + DB target)
#   2. cloudsql-iam-sa       — shared GCP service-account JSON (one-time, by 조장)
#
# Adding a new sub-agent: append "agent-<name>-secret" with the same 5 keys.
# The GCP SA JSON is intentionally NOT routed through .env — it's a multiline
# secret that would smear the dotenv parser and leak via terminal history.
SECRET_MAPPINGS: dict[str, list[tuple[str, str]]] = {
    "huggingface-token": [("HF_TOKEN", "HF_TOKEN")],
    "agent-skills-builder-secret": [
        ("LLM_BASE_URL", "LLM_BASE_URL"),
        ("EMBEDDING_BASE_URL", "EMBEDDING_BASE_URL"),
        ("CLOUD_SQL_INSTANCE", "CLOUD_SQL_INSTANCE"),
        ("DB_IAM_USER", "DB_IAM_USER"),
        ("DB_NAME", "DB_NAME"),
    ],
    # Future sub-agents (uncomment + customize when their Modal app lands):
    # "agent-personalization-secret": [
    #     ("LLM_BASE_URL", "LLM_BASE_URL"),
    #     ("EMBEDDING_BASE_URL", "EMBEDDING_BASE_URL"),
    #     ("CLOUD_SQL_INSTANCE", "CLOUD_SQL_INSTANCE"),
    #     ("DB_IAM_USER", "DB_IAM_USER"),
    #     ("DB_NAME", "DB_NAME"),
    #     ("GCS_PERSONAL_BUCKET", "GCS_PERSONAL_BUCKET"),
    # ],
    # "langsmith-api-key": [("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY")],
}


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal .env parser — no python-dotenv dependency.

    Supports KEY=value, KEY="value", KEY='value'. Comments and blank lines
    are skipped. Anything before the first `=` is the key.
    """
    if not path.exists():
        sys.exit(
            f"ERROR: {path} not found. Copy .env.example to .env and fill values."
        )

    env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip matching surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        env[key] = value
    return env


def sync_secret(
    secret_name: str,
    mappings: list[tuple[str, str]],
    env: dict[str, str],
    dry_run: bool,
) -> bool:
    """Sync one Modal Secret. Returns True if synced, False if skipped."""
    kv_args: list[str] = []
    missing: list[str] = []
    for env_var, modal_key in mappings:
        value = env.get(env_var, "").strip()
        if not value or value.startswith(
            (
                "hf_xxx",
                "ak-xxx",
                "as-xxx",
                "ls__xxx",
                "https://your-",
                "<PROJECT_ID>",
                "<YOUR_EMAIL>",
            )
        ):
            missing.append(env_var)
            continue
        kv_args.append(f"{modal_key}={value}")

    if missing:
        print(f"[skip] {secret_name} — .env missing or placeholder: {missing}")
        return False

    cmd = ["modal", "secret", "create", secret_name, *kv_args, "--force"]
    # Mask values in the printed command — don't leak secrets to stdout
    masked = ["modal", "secret", "create", secret_name]
    for arg in kv_args:
        k, _, _ = arg.partition("=")
        masked.append(f"{k}=***")
    masked.append("--force")
    print(f"[{'dry-run' if dry_run else 'sync'}] {' '.join(masked)}")

    if dry_run:
        return True

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FAILED: {result.stderr.strip()}", file=sys.stderr)
        return False
    print(f"  OK")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "secret_names",
        nargs="*",
        help="Specific Modal Secret(s) to sync (default: all)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"Path to .env file (default: {DEFAULT_ENV_FILE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them",
    )
    args = parser.parse_args()

    env = parse_env_file(args.env_file)
    targets = args.secret_names or list(SECRET_MAPPINGS.keys())

    unknown = [name for name in targets if name not in SECRET_MAPPINGS]
    if unknown:
        sys.exit(
            f"ERROR: unknown secret name(s): {unknown}. "
            f"Known: {list(SECRET_MAPPINGS.keys())}"
        )

    synced = 0
    for name in targets:
        if sync_secret(name, SECRET_MAPPINGS[name], env, args.dry_run):
            synced += 1

    print(f"\nDone — {synced}/{len(targets)} secret(s) synced.")
    return 0 if synced == len(targets) else 1


if __name__ == "__main__":
    sys.exit(main())

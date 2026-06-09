"""Load shared Modal token from .env and persist it to ~/.modal.toml.

Team members share a single Modal workspace (flowit) so that sub-agents
can `modal.Cls.from_name(...)` each other across deployments. This script
reads MODAL_TOKEN_ID / MODAL_TOKEN_SECRET from the repo-root .env file and
runs `modal token set` so the Modal CLI/SDK picks them up for subsequent
`modal deploy` calls.

Usage:
    python scripts/setup_modal_token.py            # write to ~/.modal.toml
    python scripts/setup_modal_token.py --dry-run  # show command without running
    python scripts/setup_modal_token.py --profile workflow-automation
                                                   # write under a named profile

Prerequisites:
    - .env exists at repo root with MODAL_TOKEN_ID and MODAL_TOKEN_SECRET filled
    - `modal` CLI installed (pip install modal)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"

REQUIRED_KEYS = ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET")
PLACEHOLDER_PREFIXES = ("ak-xxx", "as-xxx")


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal .env parser — no python-dotenv dependency.

    Supports KEY=value, KEY="value", KEY='value'. Comments and blank lines
    are skipped.
    """
    if not path.exists():
        sys.exit(
            f"ERROR: {path} not found. Copy .env.example to .env and fill values."
        )

    env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        env[key] = value
    return env


def load_modal_token(env_file: Path) -> tuple[str, str]:
    """Read MODAL_TOKEN_ID / MODAL_TOKEN_SECRET from .env and export to os.environ.

    Exits with an error if either is missing or still set to the placeholder.
    Returns (token_id, token_secret).
    """
    env = parse_env_file(env_file)
    missing: list[str] = []
    values: dict[str, str] = {}
    for key in REQUIRED_KEYS:
        value = env.get(key, "").strip()
        if not value or value.startswith(PLACEHOLDER_PREFIXES):
            missing.append(key)
        else:
            values[key] = value

    if missing:
        sys.exit(
            f"ERROR: {env_file} is missing or has placeholder values for: {missing}. "
            "Get the shared token from the team lead and fill it in."
        )

    for key, value in values.items():
        os.environ[key] = value

    return values["MODAL_TOKEN_ID"], values["MODAL_TOKEN_SECRET"]


def persist_to_modal_toml(
    token_id: str, token_secret: str, profile: str | None, dry_run: bool
) -> int:
    """Run `modal token set` so the values land in ~/.modal.toml."""
    cmd = [
        "modal",
        "token",
        "set",
        "--token-id",
        token_id,
        "--token-secret",
        token_secret,
    ]
    if profile:
        cmd.extend(["--profile", profile])

    masked = cmd[:3] + ["--token-id", "***", "--token-secret", "***"]
    if profile:
        masked.extend(["--profile", profile])
    print(f"[{'dry-run' if dry_run else 'run'}] {' '.join(masked)}")

    if dry_run:
        return 0

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FAILED: {result.stderr.strip()}", file=sys.stderr)
        return result.returncode
    if result.stdout.strip():
        print(f"  {result.stdout.strip()}")
    print("  OK — token persisted to ~/.modal.toml")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"Path to .env file (default: {DEFAULT_ENV_FILE})",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Modal profile name (default: write to the default profile)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print command without executing",
    )
    args = parser.parse_args()

    token_id, token_secret = load_modal_token(args.env_file)
    return persist_to_modal_toml(token_id, token_secret, args.profile, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())

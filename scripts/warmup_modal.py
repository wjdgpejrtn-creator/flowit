"""Warm up Modal sub-agent apps before staging tests.

Pings `/v1/health` on each Modal app in parallel so the GPU/CPU containers
finish boot before real user requests arrive. Run this 30~60s before a
staging QA pass — by the time the script reports OK, the next user request
hits a warm worker and skips the cold-start window (llm-base alone is
~3 min on a cold boot).

URL resolution order per app:
    1. `--<app>-url` CLI flag (highest priority)
    2. matching env var (e.g. LLM_BASE_URL, COMPOSER_URL, ...)
    3. value parsed from `--env-file` (default: <repo root>/.env)
    4. hardcoded default for workspace `dhwang0803`

Usage:
    python scripts/warmup_modal.py
    python scripts/warmup_modal.py --apps llm-base,agent-composer
    python scripts/warmup_modal.py --timeout 240 --env-file path/to/.env
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"
DEFAULT_TIMEOUT = 180.0  # llm-base cold boot ≈ 3 min (Gemma mmap + BGE load)

# (env_var, default URL for workspace dhwang0803). Defaults are last-resort
# fallbacks — staging operator changes workspace? override via env var or
# --<app>-url flag.
APP_DEFAULTS: dict[str, tuple[str, str]] = {
    "orchestrator": (
        "ORCHESTRATOR_URL",
        "https://<WORKSPACE>--orchestrator.modal.run",
    ),
    "agent-composer": (
        "COMPOSER_URL",
        "https://dhwang0803--agent-composer-agentcomposer-fastapi.modal.run",
    ),
    "agent-skills-builder": (
        "SKILLS_BUILDER_URL",
        "https://dhwang0803--agent-skills-builder-agentskillsbuilder-fastapi.modal.run",
    ),
    "agent-personalization": (
        "PERSONALIZATION_URL",
        "https://dhwang0803--agent-personalization-agentpersonalization-fastapi.modal.run",
    ),
    "llm-base": (
        "LLM_BASE_URL",
        "https://<WORKSPACE>--llm-base.modal.run",
    ),
}


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal .env parser — reused pattern from setup_modal_token.py.

    Missing file is non-fatal (returns empty dict) so the script still
    works when env vars / CLI flags provide everything.
    """
    if not path.exists():
        return {}

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


def resolve_url(
    app: str,
    cli_override: str | None,
    env_file_values: dict[str, str],
) -> str:
    """Return the URL for `app`, applying the priority order documented above."""
    if cli_override:
        return cli_override.rstrip("/")

    env_var, default = APP_DEFAULTS[app]
    return (
        os.environ.get(env_var)
        or env_file_values.get(env_var)
        or default
    ).rstrip("/")


def ping_health(app: str, url: str, timeout: float) -> dict[str, object]:
    """Hit `<url>/v1/health` and return a structured result row."""
    target = f"{url}/v1/health"
    started = time.monotonic()
    ctx = ssl.create_default_context()
    req = urllib.request.Request(target, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            elapsed = time.monotonic() - started
            body_raw = resp.read()
            try:
                body = json.loads(body_raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                body = {"raw": body_raw[:200].decode("utf-8", errors="replace")}
            return {
                "app": app,
                "url": target,
                "status": resp.status,
                "elapsed_s": round(elapsed, 2),
                "body": body,
                "ok": 200 <= resp.status < 300,
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        elapsed = time.monotonic() - started
        return {
            "app": app,
            "url": target,
            "status": exc.code,
            "elapsed_s": round(elapsed, 2),
            "body": None,
            "ok": False,
            "error": f"HTTP {exc.code}: {exc.reason}",
        }
    except (urllib.error.URLError, TimeoutError) as exc:
        elapsed = time.monotonic() - started
        return {
            "app": app,
            "url": target,
            "status": None,
            "elapsed_s": round(elapsed, 2),
            "body": None,
            "ok": False,
            "error": str(exc),
        }


def print_row(result: dict[str, object]) -> None:
    flag = "OK   " if result["ok"] else "FAIL "
    elapsed = f"{result['elapsed_s']:>6.2f}s"
    line = f"  {flag} {result['app']:<22} {elapsed}  {result['url']}"
    print(line)
    if result["error"]:
        print(f"         └─ {result['error']}")
    elif result["body"] and isinstance(result["body"], dict):
        # Surface llm-base /v1/health components (llm / embed) when present.
        keys = {k: v for k, v in result["body"].items() if k != "status"}
        if keys:
            print(f"         └─ {keys}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apps",
        default=",".join(APP_DEFAULTS.keys()),
        help=f"Comma-separated subset to warm (default: all 5). Choices: {list(APP_DEFAULTS.keys())}",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"Path to .env for URL lookup (default: {DEFAULT_ENV_FILE})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Per-request timeout in seconds (default: {DEFAULT_TIMEOUT}). llm-base cold boot ≈ 3min.",
    )
    for app in APP_DEFAULTS:
        parser.add_argument(
            f"--{app}-url",
            default=None,
            help=f"Override URL for {app} (highest priority)",
        )
    args = parser.parse_args()

    requested = [a.strip() for a in args.apps.split(",") if a.strip()]
    unknown = [a for a in requested if a not in APP_DEFAULTS]
    if unknown:
        sys.exit(f"ERROR: unknown apps: {unknown}. Valid: {list(APP_DEFAULTS.keys())}")

    env_file_values = parse_env_file(args.env_file)

    targets: list[tuple[str, str]] = []
    for app in requested:
        cli_attr = f"{app.replace('-', '_')}_url"
        cli_override = getattr(args, cli_attr, None)
        url = resolve_url(app, cli_override, env_file_values)
        targets.append((app, url))

    print(f"Warming {len(targets)} Modal app(s) — timeout={args.timeout}s")
    print(f"  env-file: {args.env_file} ({'found' if env_file_values else 'not found, using defaults'})")
    print()

    results: list[dict[str, object]] = []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        futures = {
            pool.submit(ping_health, app, url, args.timeout): app
            for app, url in targets
        }
        for fut in as_completed(futures):
            result = fut.result()
            results.append(result)
            print_row(result)
    total_elapsed = time.monotonic() - started

    failed = [r for r in results if not r["ok"]]
    print()
    print(f"Done in {total_elapsed:.2f}s — {len(results) - len(failed)} OK, {len(failed)} FAIL")

    if failed:
        print()
        print("FAILED apps (likely still cold or unreachable):")
        for r in failed:
            print(f"  - {r['app']}: {r['error']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""GCP Secret Manager helper for Modal sub-agent boot.

Pulls secrets at app startup and injects values into ``os.environ``. Modal
apps mount the ``gcp-sa-key`` Modal Secret only (ADC root) — all other
secrets live in GCP Secret Manager and are read at runtime with the
deployer/runtime SA's IAM identity.

Typical usage in a Modal ``@modal.enter()`` hook::

    from services.common.gcp_secrets import load_secrets_to_env

    @modal.enter()
    def boot(self):
        # GOOGLE_APPLICATION_CREDENTIALS already pointing at SA key file
        load_secrets_to_env({
            "llm-base-url":       "LLM_BASE_URL",
            "embedding-base-url": "EMBEDDING_BASE_URL",
            "cloud-sql-instance": "CLOUD_SQL_INSTANCE",
            "db-iam-user":        "DB_IAM_USER",
            "db-name":            "DB_NAME",
        })
        # downstream code can now read os.environ["LLM_BASE_URL"] etc.

Project ID resolution order:
    1. ``project_id`` argument (if passed).
    2. ``GOOGLE_CLOUD_PROJECT`` environment variable.
    3. ADC default project (from the SA key payload).
"""
from __future__ import annotations

import os
from typing import Mapping

_PROJECT_ENV_VAR = "GOOGLE_CLOUD_PROJECT"


def load_secrets_to_env(
    secret_to_env: Mapping[str, str],
    project_id: str | None = None,
    version: str = "latest",
) -> None:
    """Pull GCP secrets and inject decoded values into ``os.environ``.

    Args:
        secret_to_env: Mapping of GCP secret ID → environment variable name.
            Example: ``{"llm-base-url": "LLM_BASE_URL"}``.
        project_id: GCP project that owns the secrets. Falls back to the
            ``GOOGLE_CLOUD_PROJECT`` env var, then to the ADC default project.
        version: Secret version alias or number. Defaults to ``"latest"``.

    Raises:
        RuntimeError: when ``project_id`` cannot be resolved.
        google.api_core.exceptions.PermissionDenied: when the caller lacks
            ``roles/secretmanager.secretAccessor`` on a referenced secret.
        google.api_core.exceptions.NotFound: when a secret or version is
            missing.
    """
    if not secret_to_env:
        return

    resolved_project = _resolve_project(project_id)
    if not resolved_project:
        raise RuntimeError(
            "GCP project_id could not be resolved. Pass it explicitly, "
            f"set ${_PROJECT_ENV_VAR}, or configure ADC with a default project."
        )

    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    for secret_id, env_var in secret_to_env.items():
        name = f"projects/{resolved_project}/secrets/{secret_id}/versions/{version}"
        response = client.access_secret_version(name=name)
        os.environ[env_var] = response.payload.data.decode("utf-8")


def _resolve_project(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    env_val = os.environ.get(_PROJECT_ENV_VAR)
    if env_val:
        return env_val
    from google.auth import default as adc_default

    _, adc_project = adc_default()
    return adc_project

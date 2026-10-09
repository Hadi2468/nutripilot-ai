"""Load API keys from AWS Secrets Manager into the environment (used on Lambda).

The secret is a JSON object whose keys are environment variable names, e.g.
{"GROQ_API_KEY": "...", "NUTRIPILOT_API_TOKEN": "..."}.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def load_secret_into_env(secret_arn: str, client: Any = None) -> list[str]:
    """Export the secret's keys as env vars without overriding ones already set.
    Returns the names that were exported."""
    if client is None:
        import boto3  # available in the Lambda runtime; not a project dependency

        client = boto3.client("secretsmanager")

    values = json.loads(client.get_secret_value(SecretId=secret_arn)["SecretString"])
    if not isinstance(values, dict):
        raise ValueError("The NutriPilot secret must be a JSON object")

    exported = []
    for name, value in values.items():
        if value and name not in os.environ:
            os.environ[name] = str(value)
            exported.append(name)
    logger.info("Loaded %d setting(s) from Secrets Manager", len(exported))
    return exported

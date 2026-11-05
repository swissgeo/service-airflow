import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Must be set before anything imports airflow, otherwise airflow writes its config to ~/airflow
os.environ["AIRFLOW_HOME"] = tempfile.mkdtemp(prefix="airflow-test-")
os.environ["COGNITO_REGION"] = "eu-central-1"
os.environ["COGNITO_USER_POOL_ID"] = "eu-central-1_test"
os.environ["COGNITO_CLIENT_ID"] = "test-client-id"

SECRET_DIR = "/mnt/secrets-store"
_original_read_text = Path.read_text


def _fake_read_text(self: Path, *args: object, **kwargs: object) -> str:
    # Only fake the mounted Cognito secret, airflow itself reads files during import
    if str(self).startswith(SECRET_DIR):
        return "test-client-secret\n"
    return _original_read_text(self, *args, **kwargs)  # ty: ignore[invalid-argument-type]


@pytest.fixture(scope="session")
def webserver_config():
    with mock.patch.object(Path, "read_text", _fake_read_text):
        import webserver_config  # noqa: PLC0415

    return webserver_config

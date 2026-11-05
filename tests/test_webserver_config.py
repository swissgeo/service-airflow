from types import ModuleType, SimpleNamespace
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def security_manager(webserver_config: ModuleType, monkeypatch: pytest.MonkeyPatch):
    # Skip __init__, it needs a full Flask AppBuilder; get_oauth_user_info does not use self
    manager = webserver_config.CognitoSecurityManager.__new__(
        webserver_config.CognitoSecurityManager
    )
    # Return our test public key instead of fetching the JWKS from Cognito
    monkeypatch.setattr(
        webserver_config._jwks_client,  # noqa: SLF001
        "get_signing_key_from_jwt",
        lambda _token: SimpleNamespace(key=PRIVATE_KEY.public_key()),
    )
    return manager


def make_id_token(webserver_config: ModuleType, **claims: Any) -> str:  # noqa: ANN401
    payload = {
        "sub": "1234-abcd",
        "aud": webserver_config.CLIENT_ID,
        "iss": webserver_config.ISSUER,
        **claims,
    }
    return jwt.encode(payload, PRIVATE_KEY, algorithm="RS256")


def test_config_values(webserver_config: ModuleType):
    assert webserver_config.CLIENT_SECRET == "test-client-secret"
    assert (
        webserver_config.ISSUER
        == "https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_test"
    )
    assert webserver_config.SECURITY_MANAGER_CLASS is webserver_config.CognitoSecurityManager


def test_user_in_mapped_group(webserver_config: ModuleType, security_manager: Any):  # noqa: ANN401
    token = make_id_token(
        webserver_config,
        email="jane.doe@example.com",
        given_name="Jane",
        family_name="Doe",
        **{"cognito:groups": ["airflow-admins", "some-other-group"]},
    )

    user_info = security_manager.get_oauth_user_info("cognito", {"id_token": token})

    assert user_info == {
        "username": "jane.doe@example.com",
        "email": "jane.doe@example.com",
        "first_name": "Jane",
        "last_name": "Doe",
        "role_keys": ["airflow-admins", "some-other-group"],
    }


def test_user_without_mapped_group_is_denied(
    webserver_config: ModuleType,
    security_manager: Any,  # noqa: ANN401
):
    token = make_id_token(webserver_config, **{"cognito:groups": ["some-other-group"]})

    with pytest.raises(PermissionError):
        security_manager.get_oauth_user_info("cognito", {"id_token": token})


def test_user_without_groups_is_denied(webserver_config: ModuleType, security_manager: Any):  # noqa: ANN401
    token = make_id_token(webserver_config)

    with pytest.raises(PermissionError):
        security_manager.get_oauth_user_info("cognito", {"id_token": token})


def test_token_for_other_client_is_rejected(
    webserver_config: ModuleType,
    security_manager: Any,  # noqa: ANN401
):
    token = make_id_token(
        webserver_config, aud="other-client-id", **{"cognito:groups": ["airflow-admins"]}
    )

    with pytest.raises(jwt.InvalidAudienceError):
        security_manager.get_oauth_user_info("cognito", {"id_token": token})

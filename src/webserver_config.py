import logging
import os
from pathlib import Path
from typing import Any

import jwt
from airflow.providers.fab.auth_manager.security_manager.override import (
    FabAirflowSecurityManagerOverride,
)
from flask_appbuilder.security.manager import AUTH_OAUTH

log = logging.getLogger(__name__)

REGION = os.environ["COGNITO_REGION"]
POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
CLIENT_ID = os.environ["COGNITO_CLIENT_ID"]
CLIENT_SECRET = (
    Path("/mnt/secrets-store/aws-secrets-airflow/cognito-client-secret").read_text().strip()
)
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"

_jwks_client = jwt.PyJWKClient(f"{ISSUER}/.well-known/jwks.json")

AUTH_TYPE = AUTH_OAUTH
AUTH_USER_REGISTRATION = True  # auto-create users on first login
# AUTH_USER_REGISTRATION_ROLE role for users not in any mapped group, we
# explicitly deny users that are not in any known groups, but it is still
# good explicitly to set this as it is the default anyway.
AUTH_USER_REGISTRATION_ROLE = "Public"
AUTH_ROLES_SYNC_AT_LOGIN = True  # re-sync roles from Cognito groups each login
PERMANENT_SESSION_LIFETIME = 43200  # 12h

AUTH_ROLES_MAPPING = {
    "airflow-admins": ["Admin"],
    "airflow-ops": ["Op"],
    "airflow-users": ["User"],
    "airflow-viewers": ["Viewer"],
}

OAUTH_PROVIDERS = [
    {
        "name": "cognito",
        "icon": "fa-amazon",
        "token_key": "access_token",
        "remote_app": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "server_metadata_url": f"{ISSUER}/.well-known/openid-configuration",
            "client_kwargs": {"scope": "openid email profile"},
        },
    }
]


class CognitoSecurityManager(FabAirflowSecurityManagerOverride):
    """FabAirflowSecurityManagerOverride does not know 'cognito' as a provider by default.
    So we need to implement the get_oauth_user_info to properly parse the user information
    from cognito.
    We also explicitly deny access if the user is not in one of the known groups. The default
    behaviour is to add the user to the 'Public' role, which has no permissions. But if we ever add
    permissions to the Public role in the future it might have unintended side-effect."""

    def get_oauth_user_info(self, provider: str, resp: dict[str, Any]) -> dict[str, Any]:
        if provider != "cognito":
            return super().get_oauth_user_info(provider, resp)

        id_token = resp["id_token"]
        signing_key = _jwks_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=ISSUER,
        )
        log.debug("Cognito claims: %s", claims)
        groups = claims.get("cognito:groups", [])
        if not any(g in AUTH_ROLES_MAPPING for g in groups):
            log.warning(
                "Denying Airflow login for %s: no mapped Cognito group (groups=%s)",
                claims.get("email") or claims["sub"],
                groups,
            )
            msg = "User is not in any Airflow group"
            raise PermissionError(msg)

        return {
            "username": claims.get("email") or claims["sub"],
            "email": claims.get("email", ""),
            "first_name": claims.get("given_name", ""),
            "last_name": claims.get("family_name", ""),
            "role_keys": groups,
        }


SECURITY_MANAGER_CLASS = CognitoSecurityManager

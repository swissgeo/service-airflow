"""Airflow auth manager that lets in-cluster workloads authenticate with their service account.

A pod mounts a projected service account token with the audience below and exchanges it for an
Airflow API token:

    POST /auth/token
    Authorization: Bearer <projected service account token>

The token is verified offline against the cluster's OIDC issuer JWKS (signature, issuer,
audience, expiry), then its subject is mapped to an Airflow machine user.
"""

import json
import logging
import os
import urllib.request
from typing import Any

import jwt
from airflow.providers.fab.auth_manager.fab_auth_manager import FabAuthManager

log = logging.getLogger(__name__)

# Service account token issuer of the cluster, e.g. for EKS
# https://oidc.eks.eu-central-1.amazonaws.com/id/<CLUSTER_OIDC_ID>
ISSUER = os.environ.get("K8S_SA_ISSUER", "").rstrip("/")
# Optional, discovered from {ISSUER}/.well-known/openid-configuration when not set
JWKS_URL = os.environ.get("K8S_SA_JWKS_URL", "")
# Audience the projected token must be issued for. Never accept the default API server
# audience, otherwise any token of the service account (also ones meant for other services)
# could be replayed against Airflow.
AUDIENCE = os.environ.get("K8S_SA_AUDIENCE", "airflow")
ALGORITHMS = ["RS256", "ES256"]
HTTP_TIMEOUT = 5

# Kubernetes service account subject -> Airflow username. The users (and their roles) must be
# created in Airflow beforehand, tokens of service accounts without an existing user are rejected.
MACHINE_USERS: dict[str, str] = {
    "system:serviceaccount:service-processes:service-processes": "service-processes",
}

_jwks_client: jwt.PyJWKClient | None = None


def _discover_jwks_url() -> str:
    if JWKS_URL:
        return JWKS_URL
    url = f"{ISSUER}/.well-known/openid-configuration"
    if not url.startswith("https://"):
        msg = f"K8S_SA_ISSUER must be an https URL, got {ISSUER!r}"
        raise ValueError(msg)
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310
        return json.load(resp)["jwks_uri"]


def _jwks() -> jwt.PyJWKClient:
    global _jwks_client  # noqa: PLW0603
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(_discover_jwks_url(), timeout=HTTP_TIMEOUT)
    return _jwks_client


def _verify(token: str) -> dict[str, Any] | None:
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS,
            issuer=ISSUER,
            audience=AUDIENCE,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except (jwt.PyJWTError, OSError, ValueError, KeyError) as e:
        log.warning("Rejected service account token: %s", e)
        return None


class K8sFabAuthManager(FabAuthManager):
    def create_token(self, headers: dict[str, str], body: dict[str, Any]) -> Any:  # noqa: ANN401
        auth = next((v for k, v in headers.items() if k.lower() == "authorization"), "")
        if not auth.lower().startswith("bearer "):
            # No bearer token: keep default behaviour (username/password body)
            return super().create_token(headers=headers, body=body)

        claims = _verify(auth.split(" ", 1)[1].strip())
        if claims is None:
            return None

        username = MACHINE_USERS.get(claims["sub"])
        if username is None:
            log.warning("Unknown service account %s", claims["sub"])
            return None

        user = self.security_manager.find_user(username=username)
        if user is None:
            log.warning("Airflow user %s for %s does not exist", username, claims["sub"])
            return None
        if not user.is_active:
            log.warning("Airflow user %s is inactive", username)
            return None
        return user

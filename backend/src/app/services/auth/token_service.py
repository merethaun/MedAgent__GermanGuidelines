from dataclasses import dataclass
from typing import Any

import requests

from app.constants.auth_config import KEYCLOAK_CLIENT_ID, OIDC_ISSUER
from app.models.auth.token import TokenResponse


@dataclass(frozen=True)
class TokenService:
    """
    Service layer: obtain access tokens from Keycloak via password grant.
    Dev/testing helper. Do NOT log passwords.
    """
    
    def create_token(self, username: str, password: str, timeout_s: int = 10) -> TokenResponse:
        if not OIDC_ISSUER:
            raise ValueError("OIDC_ISSUER is not set")
        
        # OIDC_ISSUER is expected to be like: http://keycloak:8080/realms/<realm>
        token_url = f"{OIDC_ISSUER.rstrip('/')}/protocol/openid-connect/token"
        
        data = {
            "client_id": KEYCLOAK_CLIENT_ID,
            "grant_type": "password",
            "username": username,
            "password": password,
            # optional, harmless
            "scope": "openid",
        }
        
        resp = requests.post(
            token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=timeout_s,
        )
        
        payload: dict[str, Any]
        try:
            payload = resp.json()
        except Exception:
            payload = {"raw": resp.text}
        
        if resp.status_code != 200:
            err = payload.get("error", "token_request_failed")
            desc = payload.get("error_description", payload.get("raw", ""))
            raise ValueError(f"Keycloak token request failed: {err} ({desc})")
        
        access_token = payload.get("access_token")
        if not access_token:
            raise ValueError(f"Keycloak response missing access_token: {payload}")
        
        return TokenResponse(
            access_token=access_token,
            token_type=payload.get("token_type", "Bearer"),
            expires_in=payload.get("expires_in"),
            refresh_token=payload.get("refresh_token"),
            scope=payload.get("scope"),
        )

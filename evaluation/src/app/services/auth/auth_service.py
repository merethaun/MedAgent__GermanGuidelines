import json
from typing import List, Optional, Set

import jwt
import requests
from jwt.algorithms import RSAAlgorithm

from app.constants import auth_config
from app.models.auth.user import CurrentUser


class AuthService:
    def __init__(self):
        self._jwks_cache: Optional[dict] = None

    @staticmethod
    def _allowed_issuers() -> List[str]:
        raw = auth_config.OIDC_ALLOWED_ISSUERS
        issuers = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]

        fallback = (auth_config.OIDC_ISSUER or "").strip().rstrip("/")
        if not issuers and fallback:
            issuers = [fallback]

        return issuers

    @staticmethod
    def _jwks_url() -> str:
        if auth_config.OIDC_JWKS_URL:
            return auth_config.OIDC_JWKS_URL

        issuer = (auth_config.OIDC_ISSUER or "").rstrip("/")
        if not issuer:
            raise RuntimeError("OIDC_JWKS_URL / OIDC_ISSUER not configured")

        return f"{issuer}/protocol/openid-connect/certs"

    def _get_jwks(self, force_refresh: bool = False) -> dict:
        jwks_url = self._jwks_url()
        if force_refresh or self._jwks_cache is None:
            response = requests.get(jwks_url, timeout=5)
            response.raise_for_status()
            self._jwks_cache = response.json()
        return self._jwks_cache

    @staticmethod
    def _extract_roles(payload: dict) -> Set[str]:
        return set(payload.get("realm_access", {}).get("roles", []) or [])

    @staticmethod
    def _find_jwk_for_kid(jwks: dict, kid: str) -> Optional[dict]:
        for key in jwks.get("keys", []) or []:
            if key.get("kid") == kid:
                return key
        return None

    def decode_and_validate(self, token: str) -> CurrentUser:
        verify_aud = bool(auth_config.OIDC_VERIFY_AUDIENCE)
        audience = auth_config.OIDC_AUDIENCE

        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            raise jwt.InvalidTokenError("Missing 'kid' in JWT header")

        jwks = self._get_jwks(force_refresh=False)
        jwk = self._find_jwk_for_kid(jwks, kid)
        if jwk is None:
            jwks = self._get_jwks(force_refresh=True)
            jwk = self._find_jwk_for_kid(jwks, kid)
        if jwk is None:
            raise jwt.InvalidTokenError(f"No matching JWK for kid='{kid}'")

        public_key = RSAAlgorithm.from_jwk(json.dumps(jwk))
        options = {
            "require": ["exp", "iss", "sub"],
            "verify_iss": False,
            "verify_aud": False,
        }
        decode_kwargs = {
            "key": public_key,
            "algorithms": ["RS256"],
            "options": options,
            "leeway": 10,
        }
        if verify_aud:
            if not audience:
                raise RuntimeError("OIDC_VERIFY_AUDIENCE=true but OIDC_AUDIENCE is empty")
            decode_kwargs["audience"] = audience
            decode_kwargs["options"]["verify_aud"] = True

        payload = jwt.decode(token, **decode_kwargs)
        issuer = (payload.get("iss") or "").rstrip("/")
        allowed = self._allowed_issuers()
        if allowed and issuer not in allowed:
            raise jwt.InvalidIssuerError(f"Issuer '{issuer}' not in allowed issuers: {allowed}")

        return CurrentUser(
            sub=payload["sub"],
            username=payload.get("preferred_username") or payload.get("email"),
            roles=self._extract_roles(payload),
        )

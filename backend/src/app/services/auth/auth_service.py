from typing import Optional, Set

import jwt
import requests
from jwt.algorithms import RSAAlgorithm

from app.constants.auth_config import (
    OIDC_ISSUER, OIDC_AUDIENCE, OIDC_JWKS_URL, OIDC_VERIFY_AUDIENCE,
)
from app.models.auth import CurrentUser
from app.utils.logging import setup_logger

logger = setup_logger(__name__)


class AuthService:
    def __init__(self):
        self._jwks_cache: Optional[dict] = None
    
    def _get_jwks(self) -> dict:
        if not OIDC_JWKS_URL:
            raise RuntimeError("OIDC_JWKS_URL / OIDC_ISSUER not configured")
        if self._jwks_cache is None:
            r = requests.get(OIDC_JWKS_URL, timeout=5)
            r.raise_for_status()
            self._jwks_cache = r.json()
        return self._jwks_cache
    
    @staticmethod
    def _extract_roles(payload: dict) -> Set[str]:
        roles = set(payload.get("realm_access", {}).get("roles", []))
        return roles
    
    def decode_and_validate(self, token: str) -> CurrentUser:
        jwks = self._get_jwks()
        
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            key = next(k for k in jwks["keys"] if k["kid"] == kid)
            
            decode_kwargs = dict(
                key=RSAAlgorithm.from_jwk(key),
                algorithms=["RS256"],
                issuer=OIDC_ISSUER,
                options={"require": ["exp", "iss"]},
            )
            
            if OIDC_VERIFY_AUDIENCE:
                decode_kwargs["audience"] = OIDC_AUDIENCE
            
            payload = jwt.decode(token, **decode_kwargs)
        except Exception as e:
            logger.warning(f"Token validation failed: {e}")
            raise
        
        roles = self._extract_roles(payload)
        
        return CurrentUser(
            sub=payload["sub"],
            username=payload.get("preferred_username"),
            roles=roles,
        )

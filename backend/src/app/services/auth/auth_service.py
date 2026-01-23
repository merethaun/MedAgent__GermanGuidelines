from typing import Optional, Set

import jwt
import requests
from jwt.algorithms import RSAAlgorithm

from app.constants import auth_config
from app.models.auth import CurrentUser
from app.utils.logging import setup_logger

logger = setup_logger(__name__)


class AuthService:
    def __init__(self):
        self._jwks_cache: Optional[dict] = None
    
    def _get_jwks(self) -> dict:
        jwks_url = auth_config.OIDC_JWKS_URL
        if not jwks_url:
            raise RuntimeError("OIDC_JWKS_URL / OIDC_ISSUER not configured")
        
        if self._jwks_cache is None:
            r = requests.get(jwks_url, timeout=5)
            r.raise_for_status()
            self._jwks_cache = r.json()
        return self._jwks_cache
    
    @staticmethod
    def _extract_roles(payload: dict) -> Set[str]:
        return set(payload.get("realm_access", {}).get("roles", []))
    
    def decode_and_validate(self, token: str) -> CurrentUser:
        jwks = self._get_jwks()
        
        issuer = auth_config.OIDC_ISSUER
        verify_aud = auth_config.OIDC_VERIFY_AUDIENCE
        audience = auth_config.OIDC_AUDIENCE
        
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            key = next(k for k in jwks["keys"] if k["kid"] == kid)
            
            options = {
                "require": ["exp", "iss"],
                "verify_aud": False,  # <-- default: do NOT verify aud
            }
            
            decode_kwargs = dict(
                key=RSAAlgorithm.from_jwk(key),
                algorithms=["RS256"],
                issuer=issuer,
                options=options,
            )
            
            if verify_aud:
                if not audience:
                    raise RuntimeError("OIDC_VERIFY_AUDIENCE=true but OIDC_AUDIENCE is empty")
                decode_kwargs["audience"] = audience
                decode_kwargs["options"]["verify_aud"] = True  # <-- explicitly enable
            
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

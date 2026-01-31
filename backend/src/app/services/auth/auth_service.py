import json
from typing import List, Optional, Set

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
    
    @staticmethod
    def _allowed_issuers() -> List[str]:
        """
        Allow-list of acceptable issuer strings. This is the key to handling
        localhost vs docker DNS issuer mismatches safely.
        """
        raw = auth_config.OIDC_ALLOWED_ISSUERS
        issuers = [s.strip().rstrip("/") for s in raw.split(",") if s.strip()]
        
        # Backward-compatible fallback: if not set, allow the single configured issuer (if any)
        fallback = (auth_config.OIDC_ISSUER or "").strip().rstrip("/")
        if not issuers and fallback:
            issuers = [fallback]
        
        return issuers
    
    @staticmethod
    def _jwks_url() -> str:
        """
        Prefer explicit JWKS URL. If not provided, derive it from OIDC_ISSUER.
        """
        if auth_config.OIDC_JWKS_URL:
            return auth_config.OIDC_JWKS_URL
        
        issuer = (auth_config.OIDC_ISSUER or "").rstrip("/")
        if not issuer:
            raise RuntimeError("OIDC_JWKS_URL / OIDC_ISSUER not configured")
        
        return f"{issuer}/protocol/openid-connect/certs"
    
    def _get_jwks(self, force_refresh: bool = False) -> dict:
        jwks_url = self._jwks_url()
        
        if force_refresh or self._jwks_cache is None:
            r = requests.get(jwks_url, timeout=5)
            r.raise_for_status()
            self._jwks_cache = r.json()
        
        return self._jwks_cache
    
    @staticmethod
    def _extract_roles(payload: dict) -> Set[str]:
        return set(payload.get("realm_access", {}).get("roles", []) or [])
    
    @staticmethod
    def _find_jwk_for_kid(jwks: dict, kid: str) -> Optional[dict]:
        keys = jwks.get("keys", []) or []
        for k in keys:
            if k.get("kid") == kid:
                return k
        return None
    
    def decode_and_validate(self, token: str) -> CurrentUser:
        """
        Validates token signature (JWKS), expiration, optional audience,
        and issuer via allowlist (OIDC_ALLOWED_ISSUERS).
        """
        verify_aud = bool(auth_config.OIDC_VERIFY_AUDIENCE)
        audience = auth_config.OIDC_AUDIENCE
        
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not kid:
                raise jwt.InvalidTokenError("Missing 'kid' in JWT header")
            
            # Try cached JWKS first, refresh once if kid not found
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
                # We will validate issuer manually via allowlist, because issuer may differ
                # between browser URL and docker DNS.
                "verify_iss": False,
                # aud optional (enable only if configured)
                "verify_aud": False,
            }
            
            decode_kwargs = dict(
                key=public_key,
                algorithms=["RS256"],
                options=options,
                leeway=10,  # small clock skew tolerance (seconds)
            )
            
            if verify_aud:
                if not audience:
                    raise RuntimeError("OIDC_VERIFY_AUDIENCE=true but OIDC_AUDIENCE is empty")
                decode_kwargs["audience"] = audience
                decode_kwargs["options"]["verify_aud"] = True
            
            payload = jwt.decode(token, **decode_kwargs)
            
            # Manual issuer allowlist check
            iss = (payload.get("iss") or "").rstrip("/")
            allowed = self._allowed_issuers()
            if allowed and iss not in allowed:
                raise jwt.InvalidIssuerError(f"Issuer '{iss}' not in allowed issuers: {allowed}")
        
        except Exception as e:
            logger.warning(f"Token validation failed: {e}")
            raise
        
        roles = self._extract_roles(payload)
        
        return CurrentUser(
            sub=payload["sub"],
            username=payload.get("preferred_username") or payload.get("email"),
            roles=roles,
        )

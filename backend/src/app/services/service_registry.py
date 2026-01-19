from typing import Optional

from .auth import AuthService, TokenService

_auth_service: Optional[AuthService] = None
_token_service: Optional[TokenService] = TokenService()


def init_services() -> None:
    """
    Initialize all singleton services. Call once during app startup.
    """
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    
    global _token_service
    if _token_service is None:
        _token_service = TokenService()


def get_auth_service() -> AuthService:
    """
    Getter used by controllers via Depends(...).
    """
    if _auth_service is None:
        init_services()
    return _auth_service


def get_token_service() -> TokenService:
    if _token_service is None:
        init_services()
    return _token_service

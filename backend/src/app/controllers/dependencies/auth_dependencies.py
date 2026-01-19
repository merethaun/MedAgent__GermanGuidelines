from typing import Callable, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.constants.auth_config import ROLE_ADMIN
from app.models.auth.user import CurrentUser
from app.services.auth import AuthService
from app.services.service_registry import get_auth_service

bearer = HTTPBearer(auto_error=False)


def get_current_user(
        creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
        auth_service: AuthService = Depends(get_auth_service),
) -> CurrentUser:
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    
    try:
        return auth_service.decode_and_validate(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def require_roles(*allowed_roles: str) -> Callable:
    allowed = set(allowed_roles)
    
    def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        # Convenience: admin can do everything
        if ROLE_ADMIN in user.roles:
            return user
        if user.roles.isdisjoint(allowed):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user
    
    return _dep

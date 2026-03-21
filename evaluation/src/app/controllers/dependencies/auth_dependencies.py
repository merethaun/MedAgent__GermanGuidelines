from typing import Callable, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.constants.auth_config import ROLE_ADMIN
from app.models.auth.user import CurrentUser
from app.services.auth.auth_service import AuthService
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


def get_access_token(
        creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> str:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return creds.credentials


def require_authenticated_user(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return user


def require_roles(*allowed_roles: str) -> Callable:
    allowed = set(allowed_roles)

    def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if ROLE_ADMIN in user.roles:
            return user
        if user.roles.isdisjoint(allowed):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return _dep

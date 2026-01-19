from fastapi import APIRouter
from fastapi import Depends

from app.constants.auth_config import ROLE_ADMIN, ROLE_USER
from app.controllers.dependencies.auth_dependencies import require_roles
from app.utils.logging import setup_logger

logger = setup_logger(__name__)
test_router = APIRouter()


@test_router.get("/", dependencies=[Depends(require_roles(ROLE_ADMIN, ROLE_USER))])
def test():
    return "test"


@test_router.get("/admin", dependencies=[Depends(require_roles(ROLE_ADMIN))])
def secure_test():
    return "ONLY WITH ADMIN: test"

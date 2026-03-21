import os

OIDC_ISSUER = os.getenv("OIDC_ISSUER", "")
OIDC_ALLOWED_ISSUERS = os.getenv("OIDC_ALLOWED_ISSUERS", "")
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE", "")

OIDC_JWKS_URL = os.getenv(
    "OIDC_JWKS_URL",
    f"{OIDC_ISSUER}/protocol/openid-connect/certs" if OIDC_ISSUER else "",
)

OIDC_VERIFY_AUDIENCE = os.getenv("OIDC_VERIFY_AUDIENCE", "true").lower() == "true"

ROLE_ADMIN = str(os.getenv("MEDAGENT_ROLE_ADMIN", "admin"))
ROLE_USER = str(os.getenv("MEDAGENT_ROLE_USER", "study_user"))
ROLE_EVALUATOR = str(os.getenv("MEDAGENT_ROLE_EVALUATOR", "evaluator"))

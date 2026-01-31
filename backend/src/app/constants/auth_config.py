import os

OIDC_ISSUER = os.getenv("OIDC_ISSUER", "")
OIDC_ALLOWED_ISSUERS = os.getenv("OIDC_ALLOWED_ISSUERS", "")
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE", "")

OIDC_JWKS_URL = os.getenv(
    "OIDC_JWKS_URL",
    f"{OIDC_ISSUER}/protocol/openid-connect/certs" if OIDC_ISSUER else "",
)

# Optional: in dev you might temporarily disable audience checks; default is secure
OIDC_VERIFY_AUDIENCE = os.getenv("OIDC_VERIFY_AUDIENCE", "true").lower() == "true"
KEYCLOAK_REALM: str = os.getenv("KEYCLOAK_REALM", "medagent")
KEYCLOAK_CLIENT_ID: str = os.getenv("KEYCLOAK_CLIENT_ID", "medagent-frontend")

# Role names (centralized so you don’t hardcode them everywhere)
ROLE_ADMIN: str = str(os.getenv("MEDAGENT_ROLE_ADMIN", "admin"))
ROLE_USER: str = str(os.getenv("MEDAGENT_ROLE_USER", "study_user"))

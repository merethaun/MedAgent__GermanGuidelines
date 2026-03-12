import Keycloak from "keycloak-js";

// Important: for Browser + Backend use consistently "http://keycloak:8080"
const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL ?? "http://keycloak:8080",
  realm: import.meta.env.VITE_KEYCLOAK_REALM ?? "medagent",
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID ?? "medagent-frontend",
  adminRole: import.meta.env.VITE_KEYCLOAK_ADMIN_ROLE ?? "admin",
});

export default keycloak;

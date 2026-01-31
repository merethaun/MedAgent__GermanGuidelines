import Keycloak from "keycloak-js";

// WICHTIG: für Browser & Backend einheitlich "http://keycloak:8080"
const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL ?? "http://keycloak:8080",
  realm: import.meta.env.VITE_KEYCLOAK_REALM ?? "medagent",
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID ?? "medagent-frontend",
});

export default keycloak;

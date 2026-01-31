import {useAuth} from "../auth/AuthContext";

export default function LoginPage() {
  const auth = useAuth();

  if (!auth.initialized) return <div style={{padding: 16}}>Init…</div>;

  return (
    <div style={{padding: 16}}>
      <h2>Login</h2>
      {auth.authenticated ? (
        <>
          <p>Eingeloggt als: <b>{auth.username}</b></p>
          <button onClick={auth.logout}>Logout</button>
        </>
      ) : (
        <>
          <p>Nicht eingeloggt.</p>
          <button onClick={auth.login}>Login mit Keycloak</button>
        </>
      )}
    </div>
  );
}

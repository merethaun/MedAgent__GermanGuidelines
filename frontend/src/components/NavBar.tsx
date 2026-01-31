import {Link} from "react-router-dom";
import {useAuth} from "../auth/AuthContext";

export default function NavBar() {
  const auth = useAuth();

  return (
    <div style={{display: "flex", gap: 16, padding: 12, borderBottom: "1px solid #ddd"}}>
      <strong>MedAgent</strong>

      <Link to="/login">Login</Link>
      <Link to="/chats">Chats</Link>
      <Link to="/chat/placeholder">Chat Interaction</Link>

      <div style={{marginLeft: "auto", display: "flex", gap: 12, alignItems: "center"}}>
        {auth.initialized && auth.authenticated ? (
          <>
            <span>{auth.username ?? "user"}</span>
            <button onClick={auth.logout}>Logout</button>
          </>
        ) : (
          <button onClick={auth.login}>Login</button>
        )}
      </div>
    </div>
  );
}

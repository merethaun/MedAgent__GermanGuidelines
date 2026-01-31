import {BrowserRouter, Navigate, Route, Routes} from "react-router-dom";
import NavBar from "./components/NavBar";
import LoginPage from "./pages/Login";
import ChatsPage from "./pages/Chats";
import ChatInteractionPage from "./pages/ChatInteraction";
import {useAuth} from "./auth/AuthContext";

function Protected({children}: { children: JSX.Element }) {
  const auth = useAuth();
  if (!auth.initialized) return <div style={{padding: 16}}>Init…</div>;
  if (!auth.authenticated) return <Navigate to="/login" replace/>;
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <NavBar/>
      <Routes>
        <Route path="/login" element={<LoginPage/>}/>
        <Route path="/chats" element={<Protected><ChatsPage/></Protected>}/>
        <Route path="/chat/:chatId" element={<Protected><ChatInteractionPage/></Protected>}/>
        <Route path="*" element={<Navigate to="/chats" replace/>}/>
      </Routes>
    </BrowserRouter>
  );
}
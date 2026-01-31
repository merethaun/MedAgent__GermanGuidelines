import {BrowserRouter, Navigate, Route, Routes} from "react-router-dom";
import NavBar from "./components/NavBar";
import LoginPage from "./pages/Login";
import ChatsPage from "./pages/Chats";
import ChatInteractionPage from "./pages/ChatInteraction";
import {useAuth} from "./auth/AuthContext";

import {Box, CircularProgress, Container, CssBaseline} from "@mui/material";
import {ThemeProvider} from "@mui/material/styles";
import {theme} from "./theme";

function Protected({children}: { children: JSX.Element }) {
  const auth = useAuth();

  if (!auth.initialized) {
    return (
      <Box sx={{display: "flex", justifyContent: "center", py: 8}}>
        <CircularProgress/>
      </Box>
    );
  }

  if (!auth.authenticated) return <Navigate to="/login" replace/>;
  return children;
}

export default function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline/>
      <BrowserRouter>
        <NavBar/>
        <Container maxWidth="lg">
          <Box sx={{pt: 3, pb: 2}}>
            <Routes>
              <Route path="/login" element={<LoginPage/>}/>
              <Route path="/chats" element={<Protected><ChatsPage/></Protected>}/>
              <Route path="/chat/:chatId" element={<Protected><ChatInteractionPage/></Protected>}/>
              <Route path="*" element={<Navigate to="/chats" replace/>}/>
            </Routes>
          </Box>
        </Container>
      </BrowserRouter>
    </ThemeProvider>
  );
}

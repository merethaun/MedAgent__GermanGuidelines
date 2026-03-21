import {BrowserRouter, Navigate, Route, Routes} from "react-router-dom";
import NavBar from "./components/NavBar";
import LoginPage from "./pages/Login";
import ChatsPage from "./pages/Chats";
import ChatInteractionPage from "./pages/ChatInteraction";
import ReferenceManagementPage from "./pages/ReferenceManagement"
import ReferenceEditorPage from "./pages/ReferenceEditing";
import EvaluationAdminPage from "./pages/EvaluationAdmin";
import EvaluationTasksPage from "./pages/EvaluationTasks";
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

function RoleProtected({children, allowedRoles}: { children: JSX.Element; allowedRoles: string[] }) {
  const auth = useAuth();

  if (!auth.initialized) {
    return (
      <Box sx={{display: "flex", justifyContent: "center", py: 8}}>
        <CircularProgress/>
      </Box>
    );
  }

  if (!auth.authenticated) return <Navigate to="/login" replace/>;
  if (!allowedRoles.some((role) => auth.hasRole(role))) return <Navigate to="/chats" replace/>;
  return children;
}

export default function App() {
  const adminRole = import.meta.env.VITE_KEYCLOAK_ADMIN_ROLE ?? "admin";
  const evaluatorRole = import.meta.env.VITE_KEYCLOAK_EVALUATOR_ROLE ?? "evaluator";

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
              <Route path="/admin/references" element={<Protected><ReferenceManagementPage/></Protected>}/>
              <Route path="/admin/references/:groupId/:guidelineId" element={<Protected><ReferenceEditorPage/></Protected>}/>
              <Route path="/admin/evaluation" element={<RoleProtected allowedRoles={[adminRole]}><EvaluationAdminPage/></RoleProtected>}/>
              <Route path="/evaluation/tasks" element={<RoleProtected allowedRoles={[adminRole, evaluatorRole]}><EvaluationTasksPage/></RoleProtected>}/>
              <Route path="*" element={<Navigate to="/chats" replace/>}/>
            </Routes>
          </Box>
        </Container>
      </BrowserRouter>
    </ThemeProvider>
  );
}

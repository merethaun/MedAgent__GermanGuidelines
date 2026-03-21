import {Link as RouterLink, matchPath, useLocation} from "react-router-dom";
import {useAuth} from "../auth/AuthContext";

import {AppBar, Box, Button, Tab, Tabs, Toolbar, Typography} from "@mui/material";
import {alpha} from "@mui/material/styles";
import {UI} from "../theme";

const ADMIN_ROLE = import.meta.env.VITE_KEYCLOAK_ADMIN_ROLE ?? "admin";
const EVALUATOR_ROLE = import.meta.env.VITE_KEYCLOAK_EVALUATOR_ROLE ?? "evaluator";
const HEADER_LOGO_SRC = "/medagent-header-logo.png";

export default function NavBar() {
  const auth = useAuth();
  const location = useLocation();

  // Only “on a chat” when the current route matches /chat/:chatId
  const chatMatch = matchPath("/chat/:chatId", location.pathname);
  const chatId = chatMatch?.params?.chatId;

  const isAdmin = auth.initialized && auth.authenticated && auth.hasRole(ADMIN_ROLE);
  const isEvaluator = auth.initialized && auth.authenticated && (auth.hasRole(EVALUATOR_ROLE) || isAdmin);

  const currentTab =
    location.pathname === "/login"
      ? "/login"
      : chatMatch
        ? "/chat"
        : location.pathname === "/chats"
          ? "/chats"
          : location.pathname.startsWith("/admin/references")
            ? "/admin/references"
            : location.pathname.startsWith("/admin/evaluation")
              ? "/admin/evaluation"
              : location.pathname.startsWith("/evaluation/tasks")
                ? "/evaluation/tasks"
            : false;

  return (
    <AppBar
      position="sticky"
      elevation={2}
      color="transparent"
      sx={(theme) => ({
        borderBottom: "none",
        backgroundColor: alpha(theme.palette.primary.light, UI.navbarTintAlpha),
        backdropFilter: "saturate(160%) blur(16px)",
        boxShadow: "0 1px 6px rgba(0,0,0,0.15)",
      })}
    >
      <Toolbar
        sx={{
          gap: 1.5,
          minHeight: 64,
          py: 1,
        }}
      >
        <Box
          component={RouterLink}
          to="/chats"
          sx={{
            display: "inline-flex",
            alignItems: "center",
            gap: 1.25,
            mr: 1,
            textDecoration: "none",
            color: "text.primary",
            flexShrink: 0,
          }}
        >
          <Box
            component="img"
            src={HEADER_LOGO_SRC}
            alt=""
            sx={{
              display: "block",
              height: {xs: 34, sm: 40},
              width: "auto",
            }}
          />
          <Typography
            variant="h6"
            sx={{
              color: "inherit",
              fontWeight: 800,
              letterSpacing: 0.2,
            }}
          >
            MedAgent
          </Typography>
        </Box>

        <Tabs
          value={currentTab}
          textColor="inherit"
          sx={{
            minHeight: 44,
            "& .MuiTabs-flexContainer": {gap: 0.5},
          }}
        >
          {/* Order: Login, then Chats, then optional Chat interaction */}
          <Tab label="Login" value="/login" component={RouterLink} to="/login"/>
          <Tab label="Chats" value="/chats" component={RouterLink} to="/chats"/>
          {chatId ? (
            <Tab
              label="Chat interaction"
              value="/chat"
              component={RouterLink}
              to={`/chat/${chatId}`}
            />
          ) : null}
          {isAdmin ? (
            <Tab
              label="Reference management"
              value="/admin/references"
              component={RouterLink}
              to="/admin/references"
            />
          ) : null}
          {isAdmin ? (
            <Tab
              label="Evaluation admin"
              value="/admin/evaluation"
              component={RouterLink}
              to="/admin/evaluation"
            />
          ) : null}
          {isEvaluator ? (
            <Tab
              label="Evaluation tasks"
              value="/evaluation/tasks"
              component={RouterLink}
              to="/evaluation/tasks"
            />
          ) : null}
        </Tabs>

        <Box sx={{flexGrow: 1}}/>

        {auth.initialized && auth.authenticated ? (
          <Box sx={{display: "flex", alignItems: "center", gap: 3}}>
            <Typography>
              {auth.username ? (
                <>
                  User: <b>{auth.username}</b>
                </>
              ) : (
                "User"
              )}
            </Typography>
            <Button
              onClick={auth.logout}
              variant="outlined"
              size="small"
              sx={{textTransform: "none"}}
            >
              Logout
            </Button>
          </Box>
        ) : (
          <Button
            onClick={auth.login}
            variant="contained"
            size="small"
            sx={{textTransform: "none", boxShadow: "none"}}
          >
            Login
          </Button>
        )}
      </Toolbar>
    </AppBar>
  );
}

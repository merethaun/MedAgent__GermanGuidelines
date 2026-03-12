import {Link as RouterLink, matchPath, useLocation} from "react-router-dom";
import {useAuth} from "../auth/AuthContext";

import {AppBar, Box, Button, Tab, Tabs, Toolbar, Typography} from "@mui/material";
import {alpha} from "@mui/material/styles";
import {UI} from "../theme";

const ADMIN_ROLE = import.meta.env.VITE_KEYCLOAK_ADMIN_ROLE ?? "admin";

export default function NavBar() {
  const auth = useAuth();
  const location = useLocation();

  // Only “on a chat” when the current route matches /chat/:chatId
  const chatMatch = matchPath("/chat/:chatId", location.pathname);
  const chatId = chatMatch?.params?.chatId;

  const isAdmin = auth.initialized && auth.authenticated && auth.hasRole(ADMIN_ROLE);

  const currentTab =
    location.pathname === "/login"
      ? "/login"
      : chatMatch
        ? "/chat"
        : location.pathname === "/chats"
          ? "/chats"
          : location.pathname.startsWith("/admin/references")
            ? "/admin/references"
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
        <Typography
          variant="h6"
          component={RouterLink}
          to="/chats"
          sx={{
            textDecoration: "none",
            color: "text.primary",
            fontWeight: 800,
            letterSpacing: 0.2,
            mr: 1,
          }}
        >
          MedAgent
        </Typography>

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

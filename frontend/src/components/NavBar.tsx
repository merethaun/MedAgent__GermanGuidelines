import {Link as RouterLink, useLocation} from "react-router-dom";
import {useAuth} from "../auth/AuthContext";

import {AppBar, Box, Button, Tab, Tabs, Toolbar, Typography} from "@mui/material";
import {alpha} from "@mui/material/styles";
import {UI} from "../theme";

export default function NavBar() {
  const auth = useAuth();
  const location = useLocation();

  const currentTab =
    location.pathname === "/login"
      ? "/login"
      : location.pathname === "/chats" || location.pathname.startsWith("/chat/")
        ? "/chats"
        : false;

  return (
    <AppBar
      position="sticky"
      elevation={2}
      color="transparent"
      sx={(theme) => ({
        borderBottom: "none",
        backgroundColor: alpha(theme.palette.primary.main, UI.navbarTintAlpha),
        backdropFilter: "saturate(60%) blur(2px)",
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
          <Tab label="Chats" value="/chats" component={RouterLink} to="/chats"/>
          <Tab label="Login Page" value="/login" component={RouterLink} to="/login"/>
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
            sx={{textTransform: "none"}}
          >
            Login
          </Button>
        )}
      </Toolbar>
    </AppBar>
  );
}

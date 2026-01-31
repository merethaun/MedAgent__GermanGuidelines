import {useAuth} from "../auth/AuthContext";
import {Alert, Box, Button, CircularProgress, Paper, Stack, Typography} from "@mui/material";

export default function LoginPage() {
  const auth = useAuth();

  if (!auth.initialized) {
    return (
      <Box sx={{display: "flex", justifyContent: "center", py: 8}}>
        <CircularProgress/>
      </Box>
    );
  }

  return (
    <Paper variant="outlined" sx={{p: {xs: 2.5, sm: 4}}}>
      <Stack spacing={2.5}>
        <Box>
          <Typography variant="h4" sx={{fontWeight: 800}}>
            Login
          </Typography>
          <Typography color="text.secondary">
            Authenticate required to access chats and interact with the system.
          </Typography>
        </Box>

        <Alert severity="warning">
          This frontend is optimized for <strong>desktop</strong> and <strong>tablet</strong> screens. Very small
          displays (e.g., smartphones) are currently not supported, since core interactions (e.g., PDF viewing and
          reference handling) are not designed for narrow layouts.<br/>
          If any problems occur, consider to change the device.
        </Alert>

        {auth.authenticated ? (
          <Alert severity="success">
            Eingeloggt als: <strong>{auth.username}</strong>
          </Alert>
        ) : (
          <Alert severity="info">Nicht eingeloggt.</Alert>
        )}

        {auth.authenticated ? (
          <Button
            variant="outlined"
            onClick={auth.logout}
            sx={{textTransform: "none", alignSelf: "flex-start"}}
          >
            Logout
          </Button>
        ) : (
          <Button
            variant="contained"
            onClick={auth.login}
            sx={{textTransform: "none", alignSelf: "flex-start"}}
          >
            Login mit Keycloak
          </Button>
        )}

        <Typography variant="body2" color="text.secondary">
          Tipp: If the login window does not open, check popup blockers or third-party cookie settings.
        </Typography>
      </Stack>
    </Paper>
  );
}

// src/theme.ts
import {alpha, createTheme} from "@mui/material/styles";

export const UI = {
  navbarTintAlpha: 0.04,   // navbar background tint strength
  tabSelectedAlpha: 0.14,  // selected tab pill strength
};

export const theme = createTheme({
  typography: {
    fontFamily: ["Inter", "system-ui", "Segoe UI", "Roboto", "Arial"].join(","),
  },
  shape: {borderRadius: 12},

  components: {
    // Hide the default indicator line (we use a pill background instead)
    MuiTabs: {
      styleOverrides: {
        indicator: {height: 0},
      },
    },

    // Global tab styling (nice for nav tabs; tweak if you use tabs elsewhere)
    MuiTab: {
      styleOverrides: {
        root: ({theme}) => ({
          textTransform: "none",
          fontWeight: 600,
          minHeight: 44,
          borderRadius: 999,
          paddingLeft: theme.spacing(1.5),
          paddingRight: theme.spacing(1.5),
          marginRight: theme.spacing(0.5),
          transition: theme.transitions.create(["background-color", "color"], {
            duration: theme.transitions.duration.shortest,
          }),

          "&:hover": {
            backgroundColor: alpha(theme.palette.primary.main, UI.tabSelectedAlpha * 0.55),
          },

          "&.Mui-selected": {
            backgroundColor: alpha(theme.palette.primary.main, UI.tabSelectedAlpha),
            color: theme.palette.primary.main,
          },
        }),
      },
    },
  },
});

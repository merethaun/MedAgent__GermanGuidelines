import {alpha, createTheme} from "@mui/material/styles";

export const UI = {
  navbarTintAlpha: 0.04,
  tabSelectedAlpha: 0.14,
};

export const theme = createTheme({
  typography: {
    fontFamily: ["Inter", "system-ui", "Segoe UI", "Roboto", "Arial"].join(","),
  },
  shape: {borderRadius: 12},

  palette: {
    mode: "light",

    // Teal primary
    primary: {
      main: "#008489",        // teal 600
      light: "#32babf",       // teal 300
      dark: "#045b5e",        // teal 800
      contrastText: "#FFFFFF",
    },

    // Some other accent color
    secondary: {
      main: "#5C6BC0",        // indigo 400
      light: "#9FA8DA",       // indigo 200
      dark: "#3949AB",        // indigo 600
      contrastText: "#FFFFFF",
    },

    // Orange
    warning: {
      main: "#FF7300FF",
    },

    // Green (used via color="success")
    success: {
      main: "#2E7D32",
      contrastText: "#FFFFFF",
    },

    // Optional: nicer default surfaces
    background: {
      default: "#FAFAFA",
      paper: "#FFFFFF",
    },
  },

  components: {
    MuiTabs: {
      styleOverrides: {
        indicator: {height: 0},
      },
    },
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
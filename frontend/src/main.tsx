import {StrictMode} from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import {AuthProvider} from "./auth/AuthContext";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider>
      <App/>
    </AuthProvider>
  </StrictMode>
);
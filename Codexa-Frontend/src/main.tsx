import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css"; // main.tsx or App.tsx

import { AuthProvider } from "./context/AuthContext.tsx";
import { AppDataProvider } from "./context/useAppData.tsx";

createRoot(document.getElementById("root")!).render(
  <AuthProvider>
    <AppDataProvider>
      <App />
    </AppDataProvider>
  </AuthProvider>
);

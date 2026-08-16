import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { db } from "./db/schema";

// Test hook for Playwright to inspect IndexedDB state directly. Harness-only,
// not meant to survive into the real Phase 4 UI.
declare global {
  interface Window {
    __db: typeof db;
  }
}
window.__db = db;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

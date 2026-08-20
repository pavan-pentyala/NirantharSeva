import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { db } from "./db/schema";
import { applyPulledEvents, createReferral, transitionReferral } from "./sync/engine";
import "./styles/tokens.css";

// Test hooks for Playwright to inspect IndexedDB state and drive the sync
// engine directly, without a screen to click through. Harness-only, not
// meant to survive into the real Phase 4 UI.
declare global {
  interface Window {
    __db: typeof db;
    __engine: {
      createReferral: typeof createReferral;
      transitionReferral: typeof transitionReferral;
      applyPulledEvents: typeof applyPulledEvents;
    };
  }
}
window.__db = db;
window.__engine = { createReferral, transitionReferral, applyPulledEvents };

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);

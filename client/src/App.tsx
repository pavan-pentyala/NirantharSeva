import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./auth/RequireAuth";
import CreateReferralPage from "./pages/CreateReferralPage";
import IncomingReferralsPage from "./pages/IncomingReferralsPage";
import LoginPage from "./pages/LoginPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import ReferralDetailPage from "./pages/ReferralDetailPage";
import ReferralListPage from "./pages/ReferralListPage";
import ToyPage from "./pages/ToyPage";

type HealthResponse = {
  status: string;
  clock_mode: string;
  server_time: string;
  run_id: string | null;
};

/** The sync-engine harness (plan §5.5) — unchanged since Phase 1. Stays
 * mounted at "/" through P4.2 on purpose: client/tests/offline-sync.spec.ts
 * and client-kill-resume.spec.ts (E4's evidence) still drive it via
 * page.goto("/"), and porting them onto the real referral screens is P4.3's
 * job, not this one's (docs/PHASE4_PLAN.md). Do not repurpose "/" for a
 * real screen before that port happens. */
function ToyHarness() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((res) => {
        if (!res.ok) throw new Error(`status ${res.status}`);
        return res.json();
      })
      .then(setHealth)
      .catch((err) => setError(String(err)));
  }, []);

  return (
    <main style={{ fontFamily: "sans-serif", padding: "2rem" }}>
      <h1>NirantharSeva</h1>
      {error && <p style={{ color: "crimson" }}>API error: {error}</p>}
      {!error && !health && <p>Checking API…</p>}
      {health && (
        <ul>
          <li>status: {health.status}</li>
          <li>clock mode: {health.clock_mode}</li>
          <li>server time: {health.server_time}</li>
        </ul>
      )}
      <ToyPage />
    </main>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ToyHarness />} />
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route path="/referrals" element={<ReferralListPage />} />
        <Route path="/referrals/new" element={<CreateReferralPage />} />
        <Route path="/referrals/:id" element={<ReferralDetailPage />} />
        <Route path="/mo/incoming" element={<IncomingReferralsPage />} />
        <Route
          path="/supervisor"
          element={<PlaceholderPage title="Supervisor dashboard" comingIn="Phase 5" />}
        />
        <Route
          path="/identity-review"
          element={<PlaceholderPage title="Identity review" comingIn="Phase 6" />}
        />
      </Route>

      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

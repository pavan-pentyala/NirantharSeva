import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./auth/RequireAuth";
import { getSession, isAuthenticated } from "./auth/session";
import CreateReferralPage from "./pages/CreateReferralPage";
import IncomingReferralsPage from "./pages/IncomingReferralsPage";
import LoginPage from "./pages/LoginPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import ReferralDetailPage from "./pages/ReferralDetailPage";
import ReferralListPage from "./pages/ReferralListPage";
import { homeRouteFor } from "./routes";

/** Phase 4.3 (D1/D7): the toy sync-engine harness that used to live here
 * (Phase 1 scaffold) is dropped along with the rest of the toy model —
 * migration 0006, docs/PHASE4_PLAN.md's P4.3. "/" now redirects to
 * wherever a fresh visit should land: home if already logged in (the
 * stored JWT is still valid), the login screen otherwise. */
function Root() {
  if (isAuthenticated()) {
    const session = getSession();
    return <Navigate to={homeRouteFor(session?.role ?? "")} replace />;
  }
  return <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Root />} />
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

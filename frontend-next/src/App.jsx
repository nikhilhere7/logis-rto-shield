import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import AuthModal from "./components/AuthModal";
import { FeaturePage } from "./components/FeatureAvailability";
import DemoDashboard from "./demo/DemoDashboard";
import DemoLayout from "./demo/DemoLayout";
import { AuthProvider, RequireAuth } from "./lib/auth";
import ComingSoon from "./pages/ComingSoon";
import Dashboard from "./pages/Dashboard";
import Landing from "./pages/Landing";
import Uploads from "./pages/Uploads";

// [path, title, feature]: each page shows its placeholder when available, its FeatureAvailability panel when not.
const LATER = [["risk", "Order risk checker", "risk"], ["customers", "Customers", "customers"], ["couriers", "Couriers", "couriers"], ["rto", "RTO analytics", "rto"], ["audit", "Billing audit", "audit"], ["reports", "Reports", "reports"]];

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* The landing page stays mounted; /login and /signup only add the pop-up on top of it. */}
          <Route element={<Landing />}>
            <Route path="/" element={null} />
            <Route path="/login" element={<AuthModal mode="login" />} />
            <Route path="/signup" element={<AuthModal mode="signup" />} />
          </Route>
          {/* Public, read-only sample workspace: no login, no API calls, no merchant data. */}
          <Route path="/demo" element={<DemoLayout><DemoDashboard /></DemoLayout>} />
          <Route path="/app" element={<RequireAuth><AppShell /></RequireAuth>}>
            <Route index element={<Dashboard />} />
            <Route path="uploads" element={<Uploads />} />
            {LATER.map(([path, title, feature]) => (
              <Route key={path} path={path} element={<FeaturePage feature={feature} title={title}><ComingSoon /></FeaturePage>} />
            ))}
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

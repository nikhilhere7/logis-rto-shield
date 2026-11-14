import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import AuthModal from "./components/AuthModal";
import { FeaturePage } from "./components/FeatureAvailability";
import DemoDashboard from "./demo/DemoDashboard";
import DemoLayout from "./demo/DemoLayout";
import { AuthProvider, RequireAuth } from "./lib/auth";
import Audit from "./pages/Audit";
import Couriers from "./pages/Couriers";
import Customers from "./pages/Customers";
import Dashboard from "./pages/Dashboard";
import Landing from "./pages/Landing";
import Reports from "./pages/Reports";
import Risk from "./pages/Risk";
import Rto from "./pages/Rto";
import Uploads from "./pages/Uploads";

// [path, title, feature, page]: each page shows itself when its feature is available, and its FeatureAvailability panel when not.
const PAGES = [
  ["risk", "Order risk checker", "risk", <Risk />],
  ["customers", "Customers", "customers", <Customers />],
  ["couriers", "Couriers", "couriers", <Couriers />],
  ["rto", "RTO analytics", "rto", <Rto />],
  ["audit", "Billing audit", "audit", <Audit />],
  ["reports", "Reports", "reports", <Reports />],
];

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
            {PAGES.map(([path, title, feature, page]) => (
              <Route key={path} path={path} element={<FeaturePage feature={feature} title={title}>{page}</FeaturePage>} />
            ))}
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

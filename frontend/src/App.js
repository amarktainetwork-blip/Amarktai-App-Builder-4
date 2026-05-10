import { useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider, useAuth } from "@/lib/auth-context";
import LandingPage from "@/pages/Landing";
import LoginPage from "@/pages/Login";
import ContactPage from "@/pages/Contact";
import PrivacyPage from "@/pages/Privacy";
import TermsPage from "@/pages/Terms";
import ProjectListPage from "@/pages/ProjectList";
import WorkspacePage from "@/pages/Workspace";
import SystemHealthPage from "@/pages/SystemHealth";
import AdminUsersPage from "@/pages/AdminUsers";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center bg-amk-base text-amk-fg3 font-mono text-xs">
        [ initialising ]
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function App() {
  useEffect(() => { document.documentElement.classList.add("dark"); }, []);

  return (
    <div className="App min-h-screen bg-amk-base text-amk-fg">
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/contact" element={<ContactPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/terms" element={<TermsPage />} />
            <Route path="/app" element={<Protected><ProjectListPage /></Protected>} />
            <Route path="/system" element={<Protected><SystemHealthPage /></Protected>} />
            <Route path="/admin/users" element={<Protected><AdminUsersPage /></Protected>} />
            <Route path="/workspace/:projectId" element={<Protected><WorkspacePage /></Protected>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
      <Toaster theme="dark" position="bottom-right" />
    </div>
  );
}

export default App;

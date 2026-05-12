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
import FeaturesPage from "@/pages/Features";
import PipelinePage from "@/pages/Pipeline";
import AccessPage from "@/pages/Access";
import ProjectListPage from "@/pages/ProjectList";
import WorkspacePage from "@/pages/Workspace";
import SystemHealthPage from "@/pages/SystemHealth";
import AdminUsersPage from "@/pages/AdminUsers";

// Dashboard layout + focused pages
import DashboardLayout from "@/components/DashboardLayout";
import DashboardHome from "@/pages/dashboard/DashboardHome";
import NewBuild from "@/pages/dashboard/NewBuild";
import ProjectsPage from "@/pages/dashboard/Projects";
import RepoWorkbench from "@/pages/dashboard/RepoWorkbench";
import MediaLibraryPage from "@/pages/dashboard/MediaLibraryPage";
import SettingsPage from "@/pages/dashboard/SettingsPage";

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
            {/* Public routes */}
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/contact" element={<ContactPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/terms" element={<TermsPage />} />
            <Route path="/features" element={<FeaturesPage />} />
            <Route path="/pipeline" element={<PipelinePage />} />
            <Route path="/access" element={<AccessPage />} />

            {/* /app → redirect to /dashboard for backward compatibility */}
            <Route path="/app" element={<Protected><Navigate to="/dashboard" replace /></Protected>} />

            {/* Dashboard — nested routes with sidebar layout */}
            <Route path="/dashboard" element={<Protected><DashboardLayout /></Protected>}>
              <Route index element={<DashboardHome />} />
              <Route path="new" element={<NewBuild />} />
              <Route path="projects" element={<ProjectsPage />} />
              <Route path="repo" element={<RepoWorkbench />} />
              <Route path="media" element={<MediaLibraryPage />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>

            {/* Workspace */}
            <Route path="/workspace/:projectId" element={<Protected><WorkspacePage /></Protected>} />

            {/* Protected system/admin */}
            <Route path="/system" element={<Protected><SystemHealthPage /></Protected>} />
            <Route path="/admin/users" element={<Protected><AdminUsersPage /></Protected>} />

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
      <Toaster theme="dark" position="bottom-right" />
    </div>
  );
}

export default App;

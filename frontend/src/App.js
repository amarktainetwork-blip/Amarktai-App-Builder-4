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
import WorkspacePage from "@/pages/Workspace";
import SystemHealthPage from "@/pages/SystemHealth";
import AdminUsersPage from "@/pages/AdminUsers";
import DashboardShell from "@/components/dashboard/DashboardShell";
import DashboardHome from "@/pages/dashboard/DashboardHome";
import NewBuildPage from "@/pages/dashboard/NewBuildPage";
import ProjectsPage from "@/pages/dashboard/ProjectsPage";
import RepoWorkbenchPage from "@/pages/dashboard/RepoWorkbenchPage";
import MediaPage from "@/pages/dashboard/MediaPage";
import SettingsPage from "@/pages/dashboard/SettingsPage";
import BuildStoragePage from "@/pages/dashboard/BuildStoragePage";

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
            <Route path="/features" element={<FeaturesPage />} />
            <Route path="/pipeline" element={<PipelinePage />} />
            <Route path="/access" element={<AccessPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/contact" element={<ContactPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/terms" element={<TermsPage />} />
            <Route path="/dashboard" element={<Protected><DashboardShell /></Protected>}>
              <Route index element={<DashboardHome />} />
              <Route path="new" element={<NewBuildPage />} />
              <Route path="projects" element={<ProjectsPage />} />
              <Route path="repo" element={<RepoWorkbenchPage />} />
              <Route path="builds" element={<BuildStoragePage />} />
              <Route path="media" element={<MediaPage />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>
            <Route path="/app" element={<Navigate to="/dashboard" replace />} />
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

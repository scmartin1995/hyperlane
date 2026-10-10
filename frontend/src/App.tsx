import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { useHealth, useMe } from "@/api/queries";
import { Spinner } from "@/components/ui";

const WelcomePage = lazy(() => import("@/features/welcome/WelcomePage"));
const ProfilePage = lazy(() => import("@/features/profile/ProfilePage"));
const HomePage = lazy(() => import("@/features/home/HomePage"));
const BoardPage = lazy(() => import("@/features/board/BoardPage"));
const BacklogPage = lazy(() => import("@/features/backlog/BacklogPage"));
const ItemPage = lazy(() => import("@/features/items/ItemPage"));
const SprintsPage = lazy(() => import("@/features/sprints/SprintsPage"));
const ReportsPage = lazy(() => import("@/features/reports/ReportsPage"));
const IntakePage = lazy(() => import("@/features/intake/IntakePage"));
const ActionItemsPage = lazy(() => import("@/features/action-items/ActionItemsPage"));
const PeoplePage = lazy(() => import("@/features/people/PeoplePage"));
const SettingsPage = lazy(() => import("@/features/settings/SettingsPage"));
const ChatPage = lazy(() => import("@/features/chat/ChatPage"));

function Gate({ children }: { children: React.ReactNode }) {
  const health = useHealth();
  const me = useMe();
  const loc = useLocation();
  if (health.isLoading || me.isLoading) return <div className="h-screen flex items-center justify-center"><Spinner size={28} /></div>;
  if (health.data && !health.data.onboarded && loc.pathname !== "/welcome") return <Navigate to="/welcome" replace />;
  if (health.data?.onboarded && !me.data && loc.pathname !== "/profile" && loc.pathname !== "/welcome") return <Navigate to="/profile" replace />;
  return <>{children}</>;
}

const Fallback = <div className="p-10 flex justify-center"><Spinner size={24} /></div>;

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={Fallback}>
        <Gate>
          <Routes>
            <Route path="/welcome" element={<WelcomePage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route element={<AppShell />}>
              <Route index element={<HomePage />} />
              <Route path="board" element={<BoardPage />} />
              <Route path="backlog" element={<BacklogPage />} />
              <Route path="items/:id" element={<ItemPage />} />
              <Route path="sprints" element={<SprintsPage />} />
              <Route path="sprints/:id" element={<SprintsPage />} />
              <Route path="sprints/:id/:tab" element={<SprintsPage />} />
              <Route path="reports" element={<ReportsPage />} />
              <Route path="reports/:tab" element={<ReportsPage />} />
              <Route path="intake" element={<IntakePage />} />
              <Route path="intake/:id" element={<IntakePage />} />
              <Route path="action-items" element={<ActionItemsPage />} />
              <Route path="people" element={<PeoplePage />} />
              <Route path="people/:id" element={<PeoplePage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="settings/:tab" element={<SettingsPage />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="chat/:id" element={<ChatPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </Gate>
      </Suspense>
    </BrowserRouter>
  );
}

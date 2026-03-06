import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MainLayout } from "./components/layout/MainLayout";
import { ChatPage } from "./pages/ChatPage";
import { SearchPage } from "./pages/SearchPage";
import { PrescriptionPage } from "./pages/PrescriptionPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { VerifyEmailPage } from "./pages/VerifyEmailPage";
import { useAuthStore } from "./stores/authStore";
import { ToastContainer } from "./components/ui/ToastContainer";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
    },
  },
});

/** Wrapper that redirects to /login when unauthenticated */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

/** Wrapper that redirects to / when already authenticated */
function GuestOnly({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* ── Public auth routes ─────────────────────────── */}
          <Route
            path="/login"
            element={
              <GuestOnly>
                <LoginPage />
              </GuestOnly>
            }
          />
          <Route
            path="/register"
            element={
              <GuestOnly>
                <RegisterPage />
              </GuestOnly>
            }
          />
          <Route path="/verify-email" element={<VerifyEmailPage />} />

          {/* ── Protected app routes ──────────────────────── */}
          <Route
            path="/"
            element={
              <RequireAuth>
                <MainLayout />
              </RequireAuth>
            }
          >
            <Route index element={<ChatPage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="prescription" element={<PrescriptionPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
        <ToastContainer />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;

import { useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { Loader2 } from "lucide-react";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import Home from "./pages/Home";
import Room from "./pages/Room";
import Login from "./pages/Login";

const Protected = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#050505] text-zinc-500">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
};

const LoginRoute = () => {
  const { user, loading } = useAuth();
  if (loading) return <div className="h-screen bg-[#050505]" />;
  if (user) return <Navigate to="/" replace />;
  return <Login />;
};

function App() {
  useEffect(() => {
    document.documentElement.classList.add("dark");
  }, []);

  return (
    <div className="App min-h-screen bg-[#050505] text-white">
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginRoute />} />
            <Route path="/" element={<Protected><Home /></Protected>} />
            <Route path="/session/:id" element={<Protected><Room /></Protected>} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
      <Toaster theme="dark" position="top-center" richColors />
    </div>
  );
}

export default App;

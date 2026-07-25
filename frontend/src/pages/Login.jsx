import { useState } from "react";
import { motion } from "framer-motion";
import { useAuth } from "../contexts/AuthContext";
import { loginPassword, registerAccount } from "../lib/api";
import { toast } from "sonner";
import {
  Users, Sparkles, Mic, Gavel, Mail, Lock, User as UserIcon,
  Loader2, AlertTriangle,
} from "lucide-react";

export default function Login() {
  const { login, authError, setAuthError, signInWithUser } = useAuth();

  const [mode, setMode] = useState("signin"); // "signin" | "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!email.trim() || !password) return toast.error("Enter your email and a password");
    if (mode === "register" && password.length < 8) {
      return toast.error("Password must be at least 8 characters");
    }
    setBusy(true);
    setAuthError(null);
    try {
      const body = mode === "register"
        ? { email: email.trim(), password, name: name.trim() || undefined }
        : { email: email.trim(), password };
      const u = mode === "register" ? await registerAccount(body) : await loginPassword(body);
      toast.success(mode === "register" ? `Welcome, ${u.name || u.email}` : `Signed in as ${u.email}`);
      signInWithUser(u);
      // A hard nav gives us a clean state and lets the router pick up the new auth
      window.location.href = "/";
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || "Sign-in failed";
      toast.error(detail);
      setAuthError(detail);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grain relative min-h-screen flex items-center justify-center overflow-hidden">
      <div
        className="absolute inset-0 opacity-30"
        style={{
          background:
            "radial-gradient(circle at 30% 20%, #10B98133, transparent 45%), radial-gradient(circle at 75% 70%, #8B5CF633, transparent 45%)",
        }}
      />
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="relative z-10 w-full max-w-md px-8"
      >
        <div className="flex items-center gap-3 mb-10">
          <div className="h-10 w-10 rounded-lg bg-white flex items-center justify-center">
            <Users className="h-5 w-5 text-black" />
          </div>
          <span className="font-mono text-sm tracking-[0.25em] uppercase text-zinc-400">The Council</span>
        </div>

        <h1 className="font-heading text-4xl sm:text-5xl font-light tracking-tighter leading-[1.05]">
          Convene the
          <br />
          <span className="text-zinc-500">frontier minds.</span>
        </h1>
        <p className="mt-5 text-base leading-relaxed text-zinc-400">
          A live, spoken roundtable where GPT, Claude, Gemini, DeepSeek and Kimi debate your ideas — and you hold the chair.
        </p>

        {authError && (
          <div
            data-testid="auth-error"
            className="mt-6 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200"
          >
            <AlertTriangle className="h-4 w-4 mt-0.5 flex-none" />
            <span>{authError}</span>
          </div>
        )}

        <button
          data-testid="google-login-btn"
          onClick={login}
          className="group mt-9 flex w-full items-center justify-center gap-3 rounded-full bg-white px-6 h-13 py-3.5 text-base font-medium text-black hover:bg-zinc-200 transition-colors duration-200"
        >
          <svg className="h-5 w-5" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Sign in with Google
        </button>

        <div className="my-5 flex items-center gap-3 text-[11px] font-mono uppercase tracking-widest text-zinc-600">
          <div className="h-px flex-1 bg-white/10" /> or <div className="h-px flex-1 bg-white/10" />
        </div>

        {/* Mode tabs */}
        <div className="flex gap-1 rounded-full border border-white/10 bg-black/40 p-1 mb-4 text-sm">
          <button
            data-testid="mode-signin-tab"
            type="button"
            onClick={() => setMode("signin")}
            className={
              "flex-1 rounded-full px-3 h-9 transition-colors " +
              (mode === "signin" ? "bg-white text-black" : "text-zinc-400 hover:text-white")
            }
          >
            Sign in
          </button>
          <button
            data-testid="mode-register-tab"
            type="button"
            onClick={() => setMode("register")}
            className={
              "flex-1 rounded-full px-3 h-9 transition-colors " +
              (mode === "register" ? "bg-white text-black" : "text-zinc-400 hover:text-white")
            }
          >
            Create account
          </button>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-2.5">
          {mode === "register" && (
            <div className="relative">
              <UserIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
              <input
                data-testid="name-input"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name (optional)"
                className="w-full rounded-full bg-black/40 border border-white/10 pl-9 pr-4 h-12 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30 transition-colors duration-200"
              />
            </div>
          )}
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
            <input
              data-testid="email-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@email.com"
              autoComplete="email"
              className="w-full rounded-full bg-black/40 border border-white/10 pl-9 pr-4 h-12 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30 transition-colors duration-200"
            />
          </div>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
            <input
              data-testid="password-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === "register" ? "Choose a password (min 8 chars)" : "Password"}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              minLength={8}
              className="w-full rounded-full bg-black/40 border border-white/10 pl-9 pr-4 h-12 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30 transition-colors duration-200"
            />
          </div>
          <button
            data-testid={mode === "register" ? "register-submit-btn" : "signin-submit-btn"}
            type="submit"
            disabled={busy}
            className="mt-1 flex items-center justify-center gap-2 rounded-full bg-white text-black h-12 text-sm font-medium hover:bg-zinc-200 disabled:opacity-60 transition-colors duration-200"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {mode === "register" ? "Create account" : "Sign in"}
          </button>
        </form>

        <div className="mt-10 flex items-center gap-6 text-xs font-mono text-zinc-600">
          <span className="flex items-center gap-1.5"><Mic className="h-3.5 w-3.5" /> real voices</span>
          <span className="flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5" /> synthesis</span>
          <span className="flex items-center gap-1.5"><Gavel className="h-3.5 w-3.5" /> verdicts</span>
        </div>
      </motion.div>
    </div>
  );
}

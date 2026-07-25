import { motion } from "framer-motion";
import { useAuth } from "../contexts/AuthContext";
import { Users, Sparkles, Mic, Gavel } from "lucide-react";

export default function Login() {
  const { login } = useAuth();

  return (
    <div className="grain relative min-h-screen flex items-center justify-center overflow-hidden">
      <div className="absolute inset-0 opacity-30"
        style={{ background: "radial-gradient(circle at 30% 20%, #10B98133, transparent 45%), radial-gradient(circle at 75% 70%, #8B5CF633, transparent 45%)" }} />
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}
        className="relative z-10 w-full max-w-md px-8">
        <div className="flex items-center gap-3 mb-10">
          <div className="h-10 w-10 rounded-lg bg-white flex items-center justify-center">
            <Users className="h-5 w-5 text-black" />
          </div>
          <span className="font-mono text-sm tracking-[0.25em] uppercase text-zinc-400">The Council</span>
        </div>

        <h1 className="font-heading text-4xl sm:text-5xl font-light tracking-tighter leading-[1.05]">
          Convene the<br /><span className="text-zinc-500">frontier minds.</span>
        </h1>
        <p className="mt-5 text-base leading-relaxed text-zinc-400">
          A live, spoken roundtable where GPT, Claude, Gemini, DeepSeek and Kimi debate your ideas — and you hold the chair.
        </p>

        <button data-testid="google-login-btn" onClick={login}
          className="group mt-9 flex w-full items-center justify-center gap-3 rounded-full bg-white px-6 h-13 py-3.5 text-base font-medium text-black hover:bg-zinc-200 transition-colors duration-200">
          <svg className="h-5 w-5" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
          Sign in with Google
        </button>

        <div className="mt-10 flex items-center gap-6 text-xs font-mono text-zinc-600">
          <span className="flex items-center gap-1.5"><Mic className="h-3.5 w-3.5" /> real voices</span>
          <span className="flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5" /> synthesis</span>
          <span className="flex items-center gap-1.5"><Gavel className="h-3.5 w-3.5" /> verdicts</span>
        </div>
      </motion.div>
    </div>
  );
}

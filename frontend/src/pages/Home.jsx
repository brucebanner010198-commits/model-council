import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { getCouncil, listSessions, createSession, deleteSession } from "../lib/api";
import { SettingsDialog } from "../components/SettingsDialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../components/ui/dialog";
import { toast } from "sonner";
import { Settings, Plus, Users, Trash2, ArrowUpRight, AlertTriangle, CheckCircle2 } from "lucide-react";

export default function Home() {
  const nav = useNavigate();
  const [council, setCouncil] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [setupOpen, setSetupOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [selected, setSelected] = useState([]);

  const load = () => {
    getCouncil().then(setCouncil);
    listSessions().then(setSessions);
  };
  useEffect(() => { load(); }, []);

  const openSetup = () => {
    if (council) setSelected(council.members.map((m) => m.id));
    setTitle("");
    setSetupOpen(true);
  };

  const toggle = (id) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const start = async () => {
    if (!title.trim()) return toast.error("Give the session a topic");
    if (selected.length === 0) return toast.error("Pick at least one member");
    const s = await createSession({ title: title.trim(), participant_ids: selected });
    nav(`/session/${s.id}`);
  };

  const remove = async (e, id) => {
    e.stopPropagation();
    await deleteSession(id);
    setSessions((s) => s.filter((x) => x.id !== id));
    toast.success("Session deleted");
  };

  return (
    <div className="grain relative min-h-screen">
      <div className="relative z-10 mx-auto max-w-6xl px-6 py-10">
        {/* Header */}
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-white flex items-center justify-center">
              <Users className="h-5 w-5 text-black" />
            </div>
            <span className="font-mono text-sm tracking-[0.25em] uppercase text-zinc-400">The Council</span>
          </div>
          <Button data-testid="open-settings-btn" variant="ghost" onClick={() => setSettingsOpen(true)}
            className="text-zinc-400 hover:text-white hover:bg-white/5">
            <Settings className="h-4 w-4 mr-2" /> Configure
          </Button>
        </header>

        {/* Hero */}
        <section className="mt-16 max-w-3xl">
          <h1 className="font-heading text-4xl sm:text-5xl lg:text-6xl font-light tracking-tighter leading-[1.05]">
            A roundtable of the world's<br />
            <span className="text-zinc-500">frontier minds.</span> And you.
          </h1>
          <p className="mt-6 text-base leading-relaxed text-zinc-400 max-w-xl">
            Convene GPT, Claude, Gemini, DeepSeek and Kimi in a live spoken council. Debate an idea,
            challenge each other, and have one of them draft the final verdict. You hold the chair.
          </p>

          <div className="mt-8 flex items-center gap-4">
            <Button data-testid="new-session-btn" onClick={openSetup}
              className="rounded-full bg-white text-black hover:bg-zinc-200 px-6 h-12 text-base">
              <Plus className="h-4 w-4 mr-2" /> Convene a council
            </Button>
            {council && (
              <div className="flex items-center gap-2 text-xs font-mono">
                {council.openrouter_configured ? (
                  <span className="flex items-center gap-1.5 text-emerald-400"><CheckCircle2 className="h-3.5 w-3.5" /> OpenRouter linked</span>
                ) : (
                  <button onClick={() => setSettingsOpen(true)} className="flex items-center gap-1.5 text-amber-400">
                    <AlertTriangle className="h-3.5 w-3.5" /> Add OpenRouter key
                  </button>
                )}
              </div>
            )}
          </div>
        </section>

        {/* Council roster */}
        {council && (
          <section className="mt-16">
            <div className="text-xs font-mono uppercase tracking-[0.2em] text-zinc-500 mb-4">The Standing Council</div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
              {council.members.map((m, i) => (
                <motion.div key={m.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.06 }}
                  className="rounded-xl bg-[#0a0a0c] p-4 border border-white/8"
                  style={{ borderTop: `2px solid ${m.color}` }}>
                  <div className="font-mono text-sm font-semibold" style={{ color: m.color }}>{m.name}</div>
                  <div className="text-[11px] text-zinc-500 mt-0.5">{m.org} · {m.country}</div>
                  <div className="text-xs text-zinc-400 mt-3">{m.specialty}</div>
                  <div className="mt-2 inline-block rounded-full px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider"
                    style={{ backgroundColor: `${m.color}22`, color: m.color }}>
                    {m.open ? "open weight" : "frontier"}
                  </div>
                </motion.div>
              ))}
            </div>
          </section>
        )}

        {/* Sessions */}
        <section className="mt-16">
          <div className="text-xs font-mono uppercase tracking-[0.2em] text-zinc-500 mb-4">Session Archive</div>
          {sessions.length === 0 ? (
            <div className="rounded-xl border border-dashed border-white/10 p-10 text-center text-zinc-500 text-sm">
              No sessions yet. Convene your first council above.
            </div>
          ) : (
            <div className="grid gap-3">
              {sessions.map((s) => (
                <div key={s.id} data-testid={`session-${s.id}`} onClick={() => nav(`/session/${s.id}`)}
                  className="group flex items-center justify-between rounded-xl bg-[#0a0a0c] border border-white/8 p-5 cursor-pointer hover:border-white/20 transition-colors duration-300">
                  <div>
                    <div className="text-base text-white">{s.title}</div>
                    <div className="text-xs font-mono text-zinc-500 mt-1">
                      {s.turn_count} turns · {s.participant_ids.length} members ·{" "}
                      <span className={s.status === "concluded" ? "text-emerald-400" : "text-amber-400"}>{s.status}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button data-testid={`delete-session-${s.id}`} onClick={(e) => remove(e, s.id)}
                      className="p-2 rounded-full text-zinc-600 hover:text-red-400 hover:bg-white/5 transition-colors duration-200">
                      <Trash2 className="h-4 w-4" />
                    </button>
                    <ArrowUpRight className="h-5 w-5 text-zinc-600 group-hover:text-white transition-colors duration-200" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} onSaved={load} />

      {/* Setup dialog */}
      <Dialog open={setupOpen} onOpenChange={setSetupOpen}>
        <DialogContent className="bg-[#0a0a0c] border-white/10 text-white">
          <DialogHeader>
            <DialogTitle className="font-mono">Convene the Council</DialogTitle>
          </DialogHeader>
          <div className="space-y-5 py-2">
            <div>
              <label className="text-xs uppercase tracking-widest text-zinc-500">Topic / question</label>
              <Input data-testid="session-title-input" value={title} onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Should we bet the company on agents?"
                className="mt-2 bg-black/40 border-white/10" />
            </div>
            <div>
              <label className="text-xs uppercase tracking-widest text-zinc-500">Seat the members</label>
              <div className="mt-2 flex flex-wrap gap-2">
                {council?.members.map((m) => {
                  const on = selected.includes(m.id);
                  return (
                    <button key={m.id} data-testid={`pick-${m.id}`} onClick={() => toggle(m.id)}
                      className="rounded-full px-3 py-1.5 text-xs font-mono transition-colors duration-200 border"
                      style={{
                        borderColor: on ? m.color : "rgba(255,255,255,0.12)",
                        backgroundColor: on ? `${m.color}22` : "transparent",
                        color: on ? m.color : "#a1a1aa",
                      }}>
                      {m.name}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
          <Button data-testid="start-session-btn" onClick={start}
            className="w-full rounded-full bg-white text-black hover:bg-zinc-200">
            Enter the chamber
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

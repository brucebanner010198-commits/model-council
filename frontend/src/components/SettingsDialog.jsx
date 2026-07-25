import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { getCouncil, getSettings, saveSettings } from "../lib/api";
import { toast } from "sonner";
import { KeyRound, Check } from "lucide-react";

export const SettingsDialog = ({ open, onOpenChange, onSaved }) => {
  const [key, setKey] = useState("");
  const [configured, setConfigured] = useState(false);
  const [members, setMembers] = useState([]);
  const [models, setModels] = useState({});
  const [personas, setPersonas] = useState({});
  const [ntModel, setNtModel] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    Promise.all([getCouncil(), getSettings()]).then(([c, s]) => {
      setMembers(c.members);
      setConfigured(s.openrouter_configured);
      const m = {};
      const p = {};
      c.members.forEach((mem) => {
        m[mem.id] = s.models?.[mem.id] || mem.model;
        p[mem.id] = s.personas?.[mem.id] || "";
      });
      setModels(m);
      setPersonas(p);
      setNtModel(s.notetaker_model || c.notetaker.model);
    });
  }, [open]);

  const save = async () => {
    setSaving(true);
    try {
      const body = { models, personas, notetaker_model: ntModel };
      if (key.trim()) body.openrouter_key = key.trim();
      const res = await saveSettings(body);
      setConfigured(res.openrouter_configured);
      setKey("");
      toast.success("Settings saved");
      onSaved?.();
      onOpenChange(false);
    } catch (e) {
      toast.error("Could not save settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl bg-[#0a0a0c] border-white/10 text-white max-h-[85vh] overflow-y-auto thin-scroll">
        <DialogHeader>
          <DialogTitle className="font-mono flex items-center gap-2">
            <KeyRound className="h-4 w-4" /> Council Configuration
          </DialogTitle>
          <DialogDescription className="text-zinc-500">
            Your OpenRouter key powers DeepSeek & Kimi (and any model overrides). Voices & note-taker run on the built-in key.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-2">
          <div>
            <Label className="text-xs uppercase tracking-widest text-zinc-500">OpenRouter API Key</Label>
            <div className="mt-2 flex gap-2">
              <Input
                data-testid="openrouter-key-input"
                type="password"
                placeholder={configured ? "•••••••••• (saved) — paste to replace" : "sk-or-..."}
                value={key}
                onChange={(e) => setKey(e.target.value)}
                className="bg-black/40 border-white/10 font-mono text-sm"
              />
              {configured && <span className="flex items-center gap-1 text-xs text-emerald-400 whitespace-nowrap"><Check className="h-3.5 w-3.5" /> active</span>}
            </div>
          </div>

          <div className="space-y-3">
            <Label className="text-xs uppercase tracking-widest text-zinc-500">Model IDs & Personas</Label>
            {members.map((m) => (
              <div key={m.id} className="rounded-lg border border-white/8 p-3" style={{ borderLeft: `3px solid ${m.color}` }}>
                <div className="flex items-center justify-between">
                  <span className="font-mono text-sm" style={{ color: m.color }}>{m.name}</span>
                  <span className="text-[10px] uppercase tracking-wider text-zinc-500">{m.specialty}</span>
                </div>
                <Input
                  data-testid={`model-id-${m.id}`}
                  value={models[m.id] || ""}
                  onChange={(e) => setModels({ ...models, [m.id]: e.target.value })}
                  className="mt-2 bg-black/40 border-white/10 font-mono text-xs"
                />
                <Input
                  data-testid={`persona-${m.id}`}
                  placeholder="Optional persona (leave blank for natural personality)"
                  value={personas[m.id] || ""}
                  onChange={(e) => setPersonas({ ...personas, [m.id]: e.target.value })}
                  className="mt-2 bg-black/40 border-white/10 text-xs"
                />
              </div>
            ))}
            <div>
              <Label className="text-[10px] uppercase tracking-wider text-zinc-500">Scribe (note-taker) model</Label>
              <Input
                data-testid="notetaker-model"
                value={ntModel}
                onChange={(e) => setNtModel(e.target.value)}
                className="mt-1 bg-black/40 border-white/10 font-mono text-xs"
              />
            </div>
          </div>
        </div>

        <Button data-testid="save-settings-btn" onClick={save} disabled={saving}
          className="w-full rounded-full bg-white text-black hover:bg-zinc-200">
          {saving ? "Saving…" : "Save configuration"}
        </Button>
      </DialogContent>
    </Dialog>
  );
};

import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Textarea } from "./ui/textarea";
import { getCouncil, getSettings, saveSettings } from "../lib/api";
import { toast } from "sonner";
import { KeyRound, Check, CreditCard, GitBranch, Sparkles, Info, X } from "lucide-react";

const ROUTES = [
  { v: "auto", label: "Auto" },
  { v: "subscription", label: "Subscription" },
  { v: "direct", label: "API key" },
  { v: "openrouter", label: "OpenRouter" },
];

const SUB_HELP = {
  anthropic:
    "Install Claude Code and run `claude setup-token` on your machine, then paste the sk-ant-oat01-... token shown.",
  openai:
    "Install OpenAI Codex CLI and run `codex login` on your machine, then paste the ENTIRE contents of ~/.codex/auth.json here.",
};

export const SettingsDialog = ({ open, onOpenChange, onSaved }) => {
  const [orKey, setOrKey] = useState("");
  const [orConfigured, setOrConfigured] = useState(false);
  const [providers, setProviders] = useState([]);
  const [provConfigured, setProvConfigured] = useState({});
  const [provKeys, setProvKeys] = useState({});
  const [subsConfigured, setSubsConfigured] = useState({});
  const [subInputs, setSubInputs] = useState({}); // {openai: string, anthropic: string}
  const [members, setMembers] = useState([]);
  const [models, setModels] = useState({});
  const [nativeModels, setNativeModels] = useState({});
  const [routing, setRouting] = useState({});
  const [personas, setPersonas] = useState({});
  const [ntModel, setNtModel] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    Promise.all([getCouncil(), getSettings()]).then(([c, s]) => {
      setMembers(c.members);
      setProviders(c.providers);
      setOrConfigured(s.openrouter_configured);
      setProvConfigured(s.providers_configured || {});
      setSubsConfigured(s.subscriptions_configured || {});
      const m = {}, nm = {}, rt = {}, p = {};
      c.members.forEach((mem) => {
        m[mem.id] = s.models?.[mem.id] || mem.model;
        nm[mem.id] = s.native_models?.[mem.id] || mem.native_model;
        rt[mem.id] = s.routing?.[mem.id] || "auto";
        p[mem.id] = s.personas?.[mem.id] || "";
      });
      setModels(m); setNativeModels(nm); setRouting(rt); setPersonas(p);
      setProvKeys({});
      setSubInputs({});
      setNtModel(s.notetaker_model || c.notetaker.native_model);
    });
  }, [open]);

  const providerLabel = (pid) => providers.find((x) => x.id === pid)?.label || pid;

  // Try to normalise subscription input:
  //  - Anthropic: expect a bare "sk-ant-oat01-..." token.
  //  - OpenAI: expect either the JSON contents of ~/.codex/auth.json, or a JSON object.
  const buildSubscriptionPayload = () => {
    const payload = {};
    const openai = (subInputs.openai || "").trim();
    if (openai) {
      try {
        payload.openai = JSON.parse(openai);
      } catch {
        // If they pasted just a raw access token, wrap it. Refresh won't work.
        payload.openai = { access_token: openai };
      }
    }
    const anthropic = (subInputs.anthropic || "").trim();
    if (anthropic) {
      payload.anthropic = { access_token: anthropic };
    }
    return Object.keys(payload).length ? payload : null;
  };

  const clearSubscription = (pid) => {
    // Send empty object to explicitly delete server-side
    saveSettings({ subscription_tokens: { [pid]: {} } })
      .then((res) => {
        setSubsConfigured(res.subscriptions_configured || subsConfigured);
        toast.success(`${pid === "openai" ? "ChatGPT" : "Claude"} subscription disconnected`);
      })
      .catch(() => toast.error("Could not disconnect"));
  };

  const save = async () => {
    setSaving(true);
    try {
      const body = { models, native_models: nativeModels, routing, personas, notetaker_model: ntModel };
      if (orKey.trim()) body.openrouter_key = orKey.trim();
      const pk = {};
      Object.entries(provKeys).forEach(([k, v]) => { if (v && v.trim()) pk[k] = v.trim(); });
      if (Object.keys(pk).length) body.provider_keys = pk;
      const subPayload = buildSubscriptionPayload();
      if (subPayload) body.subscription_tokens = subPayload;
      const res = await saveSettings(body);
      setOrConfigured(res.openrouter_configured);
      setProvConfigured(res.providers_configured || provConfigured);
      setSubsConfigured(res.subscriptions_configured || subsConfigured);
      setOrKey(""); setProvKeys({}); setSubInputs({});
      toast.success("Settings saved");
      onSaved?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl bg-[#0a0a0c] border-white/10 text-white max-h-[86vh] overflow-y-auto thin-scroll">
        <DialogHeader>
          <DialogTitle className="font-mono flex items-center gap-2">
            <KeyRound className="h-4 w-4" /> Council Configuration
          </DialogTitle>
          <DialogDescription className="text-zinc-500">
            Reuse your existing ChatGPT / Claude subscriptions, add native API keys, or fall back to OpenRouter for everything else. Nothing is ever returned to the browser once saved.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-7 py-2">
          {/* --- Subscription auth (personal use) --- */}
          <div className="space-y-3 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3">
            <div className="flex items-start justify-between gap-3">
              <Label className="text-xs uppercase tracking-widest text-amber-400 flex items-center gap-2">
                <Sparkles className="h-3.5 w-3.5" /> Subscription sign-in (personal use)
              </Label>
              <span className="text-[10px] text-amber-500/80 font-mono">EXPERIMENTAL</span>
            </div>
            <div className="text-[11px] text-zinc-500 leading-relaxed flex gap-1.5">
              <Info className="h-3.5 w-3.5 mt-0.5 flex-none text-amber-500/70" />
              <span>
                Uses your ChatGPT Plus / Pro and Claude Pro / Max quotas instead of paid API tokens. Personal-use only.
                sharing subscription tokens with other users violates provider ToS.
              </span>
            </div>

            {/* Anthropic subscription */}
            <div className="grid gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-300 flex items-center gap-1.5">
                  Claude Pro / Max
                  {subsConfigured.anthropic && (
                    <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                      <Check className="h-3 w-3" /> connected
                    </span>
                  )}
                </span>
                {subsConfigured.anthropic && (
                  <button
                    data-testid="disconnect-anthropic-sub"
                    type="button"
                    onClick={() => clearSubscription("anthropic")}
                    className="text-[10px] text-zinc-500 hover:text-red-400 flex items-center gap-1"
                  >
                    <X className="h-3 w-3" /> disconnect
                  </button>
                )}
              </div>
              <Input
                data-testid="sub-anthropic-input"
                type="password"
                placeholder={
                  subsConfigured.anthropic
                    ? "•••• saved. Paste again to replace"
                    : "sk-ant-oat01-..."
                }
                value={subInputs.anthropic || ""}
                onChange={(e) => setSubInputs({ ...subInputs, anthropic: e.target.value })}
                className="bg-black/40 border-white/10 font-mono text-xs"
              />
              <p className="text-[10px] text-zinc-500 leading-relaxed">{SUB_HELP.anthropic}</p>
            </div>

            {/* OpenAI Codex subscription */}
            <div className="grid gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-300 flex items-center gap-1.5">
                  ChatGPT Plus / Pro
                  {subsConfigured.openai && (
                    <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                      <Check className="h-3 w-3" /> connected
                    </span>
                  )}
                </span>
                {subsConfigured.openai && (
                  <button
                    data-testid="disconnect-openai-sub"
                    type="button"
                    onClick={() => clearSubscription("openai")}
                    className="text-[10px] text-zinc-500 hover:text-red-400 flex items-center gap-1"
                  >
                    <X className="h-3 w-3" /> disconnect
                  </button>
                )}
              </div>
              <Textarea
                data-testid="sub-openai-input"
                placeholder={
                  subsConfigured.openai
                    ? "•••• saved. Paste the ~/.codex/auth.json contents again to replace"
                    : '{ "tokens": { "access_token": "...", "refresh_token": "...", "account_id": "..." }, "last_refresh": "..." }'
                }
                value={subInputs.openai || ""}
                onChange={(e) => setSubInputs({ ...subInputs, openai: e.target.value })}
                className="min-h-[76px] bg-black/40 border-white/10 font-mono text-[11px] leading-snug thin-scroll"
              />
              <p className="text-[10px] text-zinc-500 leading-relaxed">{SUB_HELP.openai}</p>
            </div>
          </div>

          {/* --- Native API keys --- */}
          <div className="space-y-3">
            <Label className="text-xs uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <CreditCard className="h-3.5 w-3.5" /> Provider API keys (billed per token)
            </Label>
            <div className="grid sm:grid-cols-2 gap-2">
              {providers.map((p) => (
                <div key={p.id}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-zinc-300">{p.label}</span>
                    {provConfigured[p.id] && (
                      <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                        <Check className="h-3 w-3" /> active
                      </span>
                    )}
                  </div>
                  <Input
                    data-testid={`provider-key-${p.id}`}
                    type="password"
                    placeholder={provConfigured[p.id] ? "•••• saved. Paste to replace" : `${p.label} API key`}
                    value={provKeys[p.id] || ""}
                    onChange={(e) => setProvKeys({ ...provKeys, [p.id]: e.target.value })}
                    className="bg-black/40 border-white/10 font-mono text-xs"
                  />
                </div>
              ))}
            </div>
          </div>

          {/* --- OpenRouter fallback --- */}
          <div>
            <Label className="text-xs uppercase tracking-widest text-zinc-500 flex items-center gap-2">
              <GitBranch className="h-3.5 w-3.5" /> OpenRouter (universal fallback)
            </Label>
            <div className="mt-2 flex gap-2 items-center">
              <Input
                data-testid="openrouter-key-input"
                type="password"
                placeholder={orConfigured ? "•••• saved. Paste to replace" : "sk-or-..."}
                value={orKey}
                onChange={(e) => setOrKey(e.target.value)}
                className="bg-black/40 border-white/10 font-mono text-sm"
              />
              {orConfigured && (
                <span className="flex items-center gap-1 text-xs text-emerald-400 whitespace-nowrap">
                  <Check className="h-3.5 w-3.5" /> active
                </span>
              )}
            </div>
          </div>

          {/* --- Per-member routing + model ids --- */}
          <div className="space-y-3">
            <Label className="text-xs uppercase tracking-widest text-zinc-500">
              Per-model routing, IDs & personas
            </Label>
            {members.map((m) => {
              const supportsSub = m.provider === "openai" || m.provider === "anthropic";
              return (
                <div key={m.id} className="rounded-lg border border-white/8 p-3" style={{ borderLeft: `3px solid ${m.color}` }}>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-sm" style={{ color: m.color }}>{m.name}</span>
                    <span className="text-[10px] uppercase tracking-wider text-zinc-500">{providerLabel(m.provider)}</span>
                  </div>
                  <div className="mt-2 grid grid-cols-1 gap-2">
                    <div className="flex flex-wrap gap-1">
                      {ROUTES.filter((r) => r.v !== "subscription" || supportsSub).map((r) => (
                        <button
                          key={r.v}
                          data-testid={`route-${m.id}-${r.v}`}
                          onClick={() => setRouting({ ...routing, [m.id]: r.v })}
                          className="rounded-full px-2.5 py-1 text-[10px] font-mono border transition-colors duration-200"
                          style={{
                            borderColor: routing[m.id] === r.v ? m.color : "rgba(255,255,255,0.12)",
                            backgroundColor: routing[m.id] === r.v ? `${m.color}22` : "transparent",
                            color: routing[m.id] === r.v ? m.color : "#a1a1aa",
                          }}
                        >
                          {r.label}
                        </button>
                      ))}
                    </div>
                    <div className="grid sm:grid-cols-2 gap-2">
                      <div>
                        <span className="text-[10px] text-zinc-500">Native model id</span>
                        <Input
                          data-testid={`native-model-${m.id}`}
                          value={nativeModels[m.id] || ""}
                          onChange={(e) => setNativeModels({ ...nativeModels, [m.id]: e.target.value })}
                          className="mt-0.5 bg-black/40 border-white/10 font-mono text-xs"
                        />
                      </div>
                      <div>
                        <span className="text-[10px] text-zinc-500">OpenRouter model</span>
                        <Input
                          data-testid={`model-id-${m.id}`}
                          value={models[m.id] || ""}
                          onChange={(e) => setModels({ ...models, [m.id]: e.target.value })}
                          className="mt-0.5 bg-black/40 border-white/10 font-mono text-xs"
                        />
                      </div>
                    </div>
                    <Input
                      data-testid={`persona-${m.id}`}
                      placeholder="Optional persona (blank = natural personality)"
                      value={personas[m.id] || ""}
                      onChange={(e) => setPersonas({ ...personas, [m.id]: e.target.value })}
                      className="bg-black/40 border-white/10 text-xs"
                    />
                  </div>
                </div>
              );
            })}
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

        <Button
          data-testid="save-settings-btn"
          onClick={save}
          disabled={saving}
          className="w-full rounded-full bg-white text-black hover:bg-zinc-200"
        >
          {saving ? "Saving…" : "Save configuration"}
        </Button>
      </DialogContent>
    </Dialog>
  );
};

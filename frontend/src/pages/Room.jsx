import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  getSession, getCouncil, sendMessage, respond, refreshNotes, concludeSession, transcribe,
  reviewSession, synthesize, ttsSpeak, exportUrl,
} from "../lib/api";
import { VideoTile } from "../components/VideoTile";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../components/ui/dialog";
import { toast } from "sonner";
import {
  Mic, Square, Send, Users2, PhoneOff, NotebookPen, Gavel, Play, Loader2, FileText,
  Swords, Trophy, Download, Sparkles, Volume2, StopCircle, Medal,
} from "lucide-react";

export default function Room() {
  const { id } = useParams();
  const nav = useNavigate();
  const [session, setSession] = useState(null);
  const [members, setMembers] = useState([]);
  const [input, setInput] = useState("");
  const [active, setActive] = useState(null);
  const [thinking, setThinking] = useState(null);
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [concludeOpen, setConcludeOpen] = useState(false);
  const [muted, setMuted] = useState(false);
  const [debating, setDebating] = useState(false);
  const [rounds, setRounds] = useState(2);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [synthOpen, setSynthOpen] = useState(false);
  const [playingId, setPlayingId] = useState(null);

  const transcriptRef = useRef(null);
  const mediaRef = useRef(null);
  const chunksRef = useRef([]);
  const audioRef = useRef(null);
  const stopRef = useRef(false);

  const participants = session
    ? session.participant_ids.map((pid) => members.find((m) => m.id === pid)).filter(Boolean)
    : [];

  const load = useCallback(async () => {
    const [s, c] = await Promise.all([getSession(id), getCouncil()]);
    setSession(s);
    setMembers(c.members);
  }, [id]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (transcriptRef.current) transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
  }, [session?.turns?.length]);

  const playAudio = (b64, speakerId) =>
    new Promise((resolve) => {
      if (!b64 || muted) { setTimeout(resolve, 400); return; }
      const audio = new Audio(`data:audio/mp3;base64,${b64}`);
      audioRef.current = audio;
      setActive(speakerId);
      audio.onended = () => { setActive(null); resolve(); };
      audio.onerror = () => { setActive(null); resolve(); };
      audio.play().catch(() => { setActive(null); resolve(); });
    });

  const pushTurn = (turn) =>
    setSession((s) => ({ ...s, turns: [...s.turns, turn] }));

  const makeRespond = async (modelId, directive) => {
    setThinking(modelId);
    try {
      const res = await respond(id, modelId, directive);
      setThinking(null);
      pushTurn(res.turn);
      await playAudio(res.audio_base64, modelId);
    } catch (e) {
      setThinking(null);
      toast.error(e?.response?.data?.detail || "A member failed to respond");
      throw e;
    }
  };

  const doNotes = async () => {
    try {
      const res = await refreshNotes(id);
      setSession((s) => ({ ...s, notes: res.notes }));
    } catch (e) {
      console.debug("Scribe notes refresh failed (non-fatal):", e);
    }
  };

  const sendHuman = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    const turn = await sendMessage(id, text);
    pushTurn(turn);
  };

  const roundTable = async (directive) => {
    if (busy) return;
    setBusy(true);
    try {
      if (input.trim()) await sendHuman();
      for (const p of participants) {
        await makeRespond(p.id, directive);
      }
      await doNotes();
    } catch (e) {
      console.debug("Round-table interrupted:", e);
    } finally { setBusy(false); }
  };

  const openFloor = async () => {
    const dir = `Open the council discussion on the topic: "${session.title}". Share your opening position candidly.`;
    await roundTable(dir);
  };

  const tileRespond = async (member) => {
    if (busy || member.id === "human") return;
    setBusy(true);
    try {
      if (input.trim()) await sendHuman();
      await makeRespond(member.id, `The chair turns to you, ${member.name}. Respond to the discussion.`);
      await doNotes();
    } catch (e) {
      console.debug("Tile respond failed:", e);
    } finally { setBusy(false); }
  };

  const startRec = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => chunksRef.current.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setTranscribing(true);
        try {
          const res = await transcribe(blob);
          setInput((prev) => (prev ? prev + " " : "") + (res.text || ""));
        } catch (e) {
          console.warn("STT transcription failed:", e);
          toast.error("Could not transcribe audio");
        }
        finally { setTranscribing(false); }
      };
      mr.start();
      mediaRef.current = mr;
      setRecording(true);
    } catch (e) {
      console.warn("Microphone unavailable:", e);
      toast.error("Microphone access denied");
    }
  };

  const stopRec = () => {
    mediaRef.current?.stop();
    setRecording(false);
  };

  const draft = async (drafterId) => {
    setConcludeOpen(false);
    setBusy(true);
    setThinking(drafterId);
    try {
      const c = await concludeSession(id, drafterId);
      setSession((s) => ({ ...s, conclusion: c, status: "concluded" }));
      toast.success(`${c.drafter_name} drafted the conclusion`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not draft conclusion");
    } finally { setThinking(null); setBusy(false); }
  };

  const autoDebate = async () => {
    if (busy) return;
    stopRef.current = false;
    setBusy(true);
    setDebating(true);
    const dir =
      "This is a live council debate. Critically engage with what others have just said — challenge weak points " +
      "by name, defend or sharpen your own view, and drive toward the strongest possible answer. Be candid and concise.";
    try {
      if (input.trim()) await sendHuman();
      outer: for (let r = 0; r < rounds; r++) {
        for (const p of participants) {
          if (stopRef.current) break outer;
          await makeRespond(p.id, dir);
        }
      }
      await doNotes();
    } catch (e) {
      console.debug("Auto-debate interrupted:", e);
    } finally { setDebating(false); setBusy(false); }
  };

  const stopDebate = () => { stopRef.current = true; };

  const runReview = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const rv = await reviewSession(id);
      setSession((s) => ({ ...s, review: rv }));
      setReviewOpen(true);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Peer review failed");
    } finally { setBusy(false); }
  };

  const runSynthesize = async (chairmanId) => {
    setSynthOpen(false);
    setBusy(true);
    setThinking(chairmanId);
    const q = input.trim() || session.title;
    setInput("");
    try {
      const res = await synthesize(id, chairmanId, input.trim() || null);
      setSession((s) => ({
        ...s,
        turns: [...s.turns, ...res.answers],
        review: res.review || s.review,
        synthesis: res.synthesis,
      }));
      toast.success(`${res.synthesis.chairman_name} synthesised the council's answer`);
      if (!muted) await playBlob(res.synthesis.text, chairmanId);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Synthesis failed");
    } finally { setThinking(null); setBusy(false); }
  };

  const playBlob = async (text, memberId) => {
    try {
      setPlayingId(memberId);
      const res = await ttsSpeak(text, memberId);
      await new Promise((resolve) => {
        const a = new Audio(`data:audio/mp3;base64,${res.audio_base64}`);
        audioRef.current = a;
        setActive(memberId);
        a.onended = () => { setActive(null); resolve(); };
        a.onerror = () => { setActive(null); resolve(); };
        a.play().catch(() => { setActive(null); resolve(); });
      });
    } catch (e) {
      console.debug("TTS playback failed (non-fatal):", e);
    } finally { setPlayingId(null); }
  };

  const doExport = () => {
    window.open(exportUrl(id), "_blank");
  };

  if (!session) {
    return <div className="flex h-screen items-center justify-center text-zinc-500 font-mono text-sm">Entering the chamber…</div>;
  }

  return (
    <div className="grain relative h-screen w-full overflow-hidden">
      <div className="relative z-10 grid h-full grid-cols-1 lg:grid-cols-12">
        {/* Main stage */}
        <div className="lg:col-span-8 flex flex-col h-full overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/8">
            <div>
              <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">Council in session</div>
              <h1 className="font-heading text-xl font-medium tracking-tight">{session.title}</h1>
            </div>
            <Button data-testid="leave-btn" variant="ghost" onClick={() => nav("/")}
              className="text-zinc-400 hover:text-red-400 hover:bg-white/5">
              <PhoneOff className="h-4 w-4 mr-2" /> Leave
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto thin-scroll p-6">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {participants.map((m) => (
                <VideoTile key={m.id} member={m} speaking={active === m.id} thinking={thinking === m.id}
                  drafter={session.conclusion?.drafter_id === m.id}
                  onClick={() => tileRespond(m)} />
              ))}
              <VideoTile member={{ id: "human", name: "You", color: "#ffffff" }} isHuman muted={muted} />
            </div>
          </div>

          {/* Control dock */}
          <div className="px-6 pb-6 pt-2">
            <div className="rounded-2xl bg-black/60 backdrop-blur-xl border border-white/10 p-3 flex items-center gap-2 shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
              <button data-testid="mic-btn" onClick={recording ? stopRec : startRec}
                className={`flex h-11 w-11 items-center justify-center rounded-full transition-colors duration-200 ${recording ? "bg-red-500 text-white" : "bg-white/8 text-zinc-300 hover:bg-white/15"}`}>
                {recording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
              <input
                data-testid="message-input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") roundTable(); }}
                placeholder={transcribing ? "Transcribing your voice…" : recording ? "Listening…" : "Speak your mind to the council…"}
                className="flex-1 bg-transparent px-3 text-sm text-white placeholder:text-zinc-600 focus:outline-none"
              />
              {transcribing && <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />}
              <button data-testid="send-btn" onClick={() => roundTable()} disabled={busy}
                className="flex h-11 items-center gap-2 rounded-full bg-white px-4 text-sm text-black hover:bg-zinc-200 disabled:opacity-40 transition-colors duration-200">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                <span className="hidden sm:inline">Address council</span>
              </button>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button data-testid="synthesize-btn" onClick={() => setSynthOpen(true)} disabled={busy}
                className="rounded-full bg-white text-black hover:bg-zinc-200 text-xs h-9 font-medium">
                <Sparkles className="h-3.5 w-3.5 mr-1.5" /> Synthesize answer
              </Button>
              {debating ? (
                <Button data-testid="stop-debate-btn" onClick={stopDebate}
                  className="rounded-full bg-red-500/90 text-white hover:bg-red-500 text-xs h-9">
                  <StopCircle className="h-3.5 w-3.5 mr-1.5" /> Stop debate
                </Button>
              ) : (
                <div className="flex items-center rounded-full border border-white/12 h-9 overflow-hidden">
                  <button data-testid="auto-debate-btn" onClick={autoDebate} disabled={busy}
                    className="flex items-center gap-1.5 px-3 text-xs text-zinc-300 hover:bg-white/5 h-full transition-colors duration-200">
                    <Swords className="h-3.5 w-3.5" /> Auto-debate
                  </button>
                  <button data-testid="rounds-select" onClick={() => setRounds((r) => (r % 4) + 1)}
                    className="bg-black/40 text-zinc-400 text-xs h-full px-2.5 border-l border-white/12 hover:text-white transition-colors duration-200 font-mono">
                    {rounds}r
                  </button>
                </div>
              )}
              <Button data-testid="open-floor-btn" onClick={openFloor} disabled={busy}
                variant="outline" className="rounded-full border-white/12 bg-transparent text-zinc-300 hover:bg-white/5 hover:text-white text-xs h-9">
                <Play className="h-3.5 w-3.5 mr-1.5" /> Open floor
              </Button>
              <Button data-testid="round-table-btn" onClick={() => roundTable()} disabled={busy}
                variant="outline" className="rounded-full border-white/12 bg-transparent text-zinc-300 hover:bg-white/5 hover:text-white text-xs h-9">
                <Users2 className="h-3.5 w-3.5 mr-1.5" /> Round table
              </Button>
              <Button data-testid="review-btn" onClick={runReview} disabled={busy}
                variant="outline" className="rounded-full border-white/12 bg-transparent text-zinc-300 hover:bg-white/5 hover:text-white text-xs h-9">
                <Trophy className="h-3.5 w-3.5 mr-1.5" /> Peer review
              </Button>
              <Button data-testid="notes-btn" onClick={doNotes} disabled={busy}
                variant="outline" className="rounded-full border-white/12 bg-transparent text-zinc-300 hover:bg-white/5 hover:text-white text-xs h-9">
                <NotebookPen className="h-3.5 w-3.5 mr-1.5" /> Notes
              </Button>
              <Button data-testid="conclude-btn" onClick={() => setConcludeOpen(true)} disabled={busy}
                variant="outline" className="rounded-full border-white/12 bg-transparent text-zinc-300 hover:bg-white/5 hover:text-white text-xs h-9">
                <Gavel className="h-3.5 w-3.5 mr-1.5" /> Conclude
              </Button>
              <Button data-testid="export-btn" onClick={doExport}
                variant="outline" className="rounded-full border-white/12 bg-transparent text-zinc-300 hover:bg-white/5 hover:text-white text-xs h-9">
                <Download className="h-3.5 w-3.5 mr-1.5" /> Export PDF
              </Button>
              <button onClick={() => setMuted((m) => !m)} data-testid="mute-toggle"
                className="text-xs font-mono text-zinc-500 hover:text-white ml-auto">
                {muted ? "voices off" : "voices on"}
              </button>
            </div>
          </div>
        </div>

        {/* Sidebars */}
        <div className="lg:col-span-4 grid grid-rows-2 h-full border-l border-white/8 overflow-hidden">
          {/* Transcript */}
          <div className="row-span-1 flex flex-col border-b border-white/8 overflow-hidden">
            <div className="flex items-center gap-2 px-5 py-3 border-b border-white/8">
              <FileText className="h-3.5 w-3.5 text-zinc-500" />
              <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">Transcript</span>
            </div>
            <div ref={transcriptRef} className="flex-1 overflow-y-auto thin-scroll px-5 py-4 space-y-4">
              {session.turns.length === 0 && (
                <div className="text-xs text-zinc-600">The chamber is silent. Address the council or open the floor.</div>
              )}
              <AnimatePresence initial={false}>
                {session.turns.map((t) => (
                  <motion.div key={t.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                    data-testid={`turn-${t.speaker_id}`} className="group">
                    <div className="flex items-center gap-2">
                      <div className="font-mono text-[11px] font-semibold tracking-wide" style={{ color: t.color }}>
                        {t.speaker_name}
                      </div>
                      {t.speaker_id !== "human" && (
                        <button data-testid={`play-turn-${t.id}`} onClick={() => playBlob(t.text, t.speaker_id)}
                          className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-white transition-opacity duration-200">
                          {playingId === t.speaker_id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Volume2 className="h-3 w-3" />}
                        </button>
                      )}
                    </div>
                    <p className="mt-1 text-sm leading-relaxed text-zinc-300">{t.text}</p>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </div>

          {/* Notes */}
          <div className="row-span-1 flex flex-col overflow-hidden bg-[#08080a]">
            <div className="flex items-center gap-2 px-5 py-3 border-b border-white/8">
              <NotebookPen className="h-3.5 w-3.5 text-zinc-500" />
              <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">Scribe's Notes</span>
            </div>
            <div className="flex-1 overflow-y-auto thin-scroll px-5 py-4 space-y-3">
              {(!session.notes || session.notes.length === 0) ? (
                <div className="text-xs text-zinc-600">Scribe captures key points automatically after each round.</div>
              ) : (
                session.notes.map((n) => (
                  <div key={n.id} className="flex gap-2 text-sm text-zinc-300" data-testid="note-item">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-zinc-500" />
                    <span>{n.text}</span>
                  </div>
                ))
              )}
              {session.synthesis && (
                <div className="mt-5 rounded-lg border p-4" data-testid="synthesis-block"
                  style={{ borderColor: `${session.synthesis.chairman_color}44`, backgroundColor: `${session.synthesis.chairman_color}0f` }}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest"
                      style={{ color: session.synthesis.chairman_color }}>
                      <Sparkles className="h-3 w-3" /> Synthesised answer · by {session.synthesis.chairman_name}
                    </div>
                    <button data-testid="play-synthesis" onClick={() => playBlob(session.synthesis.text, session.synthesis.chairman_id)}
                      className="text-zinc-400 hover:text-white transition-colors duration-200">
                      <Volume2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-zinc-200 whitespace-pre-wrap">{session.synthesis.text}</p>
                </div>
              )}
              {session.conclusion && (
                <div className="mt-5 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4" data-testid="conclusion-block">
                  <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-emerald-400">
                    <Gavel className="h-3 w-3" /> Verdict · drafted by {session.conclusion.drafter_name}
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-zinc-200 whitespace-pre-wrap">{session.conclusion.text}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Conclusion drafter picker */}
      <Dialog open={concludeOpen} onOpenChange={setConcludeOpen}>
        <DialogContent className="bg-[#0a0a0c] border-white/10 text-white">
          <DialogHeader>
            <DialogTitle className="font-mono">Assign the conclusion drafter</DialogTitle>
            <DialogDescription className="text-zinc-500">The chosen member will synthesise the discussion into the final verdict.</DialogDescription>
          </DialogHeader>
          <p className="text-sm text-zinc-400">Which member should synthesise the discussion into the final verdict?</p>
          <div className="grid gap-2 mt-2">
            {participants.map((m) => (
              <button key={m.id} data-testid={`draft-with-${m.id}`} onClick={() => draft(m.id)}
                className="flex items-center justify-between rounded-lg border border-white/10 p-3 text-left hover:bg-white/5 transition-colors duration-200"
                style={{ borderLeft: `3px solid ${m.color}` }}>
                <div>
                  <div className="font-mono text-sm" style={{ color: m.color }}>{m.name}</div>
                  <div className="text-[11px] text-zinc-500">{m.specialty}</div>
                </div>
                <Gavel className="h-4 w-4 text-zinc-500" />
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* Chairman picker for synthesis (Perplexity-style, additive) */}
      <Dialog open={synthOpen} onOpenChange={setSynthOpen}>
        <DialogContent className="bg-[#0a0a0c] border-white/10 text-white">
          <DialogHeader>
            <DialogTitle className="font-mono flex items-center gap-2"><Sparkles className="h-4 w-4" /> Synthesize a single answer</DialogTitle>
            <DialogDescription className="text-zinc-500">
              Fans your question to all {participants.length} members in parallel, blind-reviews their answers, then the Chairman merges them into one authoritative answer.
            </DialogDescription>
          </DialogHeader>
          <p className="text-sm text-zinc-400 mt-1">
            Question: <span className="text-zinc-200">{input.trim() || session.title}</span>
          </p>
          <div className="text-[11px] uppercase tracking-widest text-zinc-500 mt-3 mb-1">Choose the Chairman</div>
          <div className="grid gap-2">
            {participants.map((m) => (
              <button key={m.id} data-testid={`chairman-${m.id}`} onClick={() => runSynthesize(m.id)}
                className="flex items-center justify-between rounded-lg border border-white/10 p-3 text-left hover:bg-white/5 transition-colors duration-200"
                style={{ borderLeft: `3px solid ${m.color}` }}>
                <div>
                  <div className="font-mono text-sm" style={{ color: m.color }}>{m.name}</div>
                  <div className="text-[11px] text-zinc-500">{m.specialty}</div>
                </div>
                <Sparkles className="h-4 w-4 text-zinc-500" />
              </button>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* Council standings from blind peer review */}
      <Dialog open={reviewOpen} onOpenChange={setReviewOpen}>
        <DialogContent className="bg-[#0a0a0c] border-white/10 text-white max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-mono flex items-center gap-2"><Trophy className="h-4 w-4" /> Council Standings</DialogTitle>
            <DialogDescription className="text-zinc-500">
              Each member blind-ranked the others' latest positions (identities hidden) on rigour & insight.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 mt-1">
            {session.review?.standings?.map((s, i) => (
              <div key={s.member_id} data-testid={`standing-${s.member_id}`} className="rounded-lg bg-black/40 p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-zinc-500">{i + 1}</span>
                    <span className="font-mono text-sm font-semibold" style={{ color: s.color }}>{s.name}</span>
                    {s.member_id === session.review.mvp_id && (
                      <span className="flex items-center gap-1 rounded-full bg-white/10 px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider text-amber-300">
                        <Medal className="h-3 w-3" /> most convincing
                      </span>
                    )}
                  </div>
                  <span className="font-mono text-xs text-zinc-400">{s.votes} vote{s.votes === 1 ? "" : "s"}</span>
                </div>
                <div className="mt-2 h-1.5 w-full rounded-full bg-white/8 overflow-hidden">
                  <motion.div className="h-full rounded-full" style={{ backgroundColor: s.color }}
                    initial={{ width: 0 }} animate={{ width: `${s.score}%` }} transition={{ duration: 0.6 }} />
                </div>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

import { motion } from "framer-motion";
import { Waveform } from "./Waveform";
import { Mic, MicOff, Loader2, PenLine } from "lucide-react";

const hexToRgba = (hex, a) => {
  const h = hex.replace("#", "");
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
};

export const VideoTile = ({ member, isHuman, speaking, thinking, muted, onClick, drafter }) => {
  const color = member.color || "#ffffff";
  const initials = isHuman
    ? "YOU"
    : member.name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();

  return (
    <motion.button
      type="button"
      onClick={onClick}
      data-testid={`tile-${member.id}`}
      className="relative flex flex-col items-center justify-center rounded-2xl bg-[#0a0a0c] p-5 text-left transition-colors duration-300 focus:outline-none focus:ring-2 focus:ring-zinc-600 min-h-[180px] overflow-hidden group"
      style={{
        border: `1px solid ${speaking ? color : "rgba(255,255,255,0.08)"}`,
        boxShadow: speaking ? `0 0 28px ${hexToRgba(color, 0.35)}` : "none",
      }}
      whileHover={{ scale: onClick ? 1.015 : 1 }}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <div
        className="absolute inset-0 opacity-[0.12] transition-opacity duration-500"
        style={{ background: `radial-gradient(circle at 50% 30%, ${color}, transparent 70%)`, opacity: speaking ? 0.22 : 0.06 }}
      />
      <div
        className="relative flex h-16 w-16 items-center justify-center rounded-full font-mono text-lg font-bold"
        style={{ backgroundColor: hexToRgba(color, 0.14), color, border: `1px solid ${hexToRgba(color, 0.4)}` }}
      >
        {initials}
      </div>
      <div className="relative mt-4 text-center">
        <div className="font-mono text-sm font-semibold text-white">{member.name}</div>
        <div className="text-[11px] uppercase tracking-[0.15em] text-zinc-500">
          {isHuman ? "Council Chair" : member.org}
        </div>
      </div>

      <div className="relative mt-3 h-8 flex items-center">
        {thinking ? (
          <span className="flex items-center gap-2 text-xs text-zinc-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> thinking…
          </span>
        ) : (
          <Waveform active={speaking} color={color} />
        )}
      </div>

      {!isHuman && (
        <div className="absolute left-3 top-3 rounded-full px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider"
          style={{ backgroundColor: hexToRgba(color, 0.12), color }}>
          {member.open ? "open" : "frontier"}
        </div>
      )}
      {drafter && (
        <div className="absolute right-3 top-3 flex items-center gap-1 rounded-full bg-white/10 px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider text-white">
          <PenLine className="h-3 w-3" /> drafter
        </div>
      )}
      {isHuman && (
        <div className="absolute right-3 top-3 text-zinc-400">
          {muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4 text-emerald-400" />}
        </div>
      )}
    </motion.button>
  );
};

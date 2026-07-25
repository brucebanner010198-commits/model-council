import { motion } from "framer-motion";

export const Waveform = ({ active, color = "#ffffff" }) => {
  const bars = [0, 1, 2, 3, 4, 5, 6];
  return (
    <div className="flex items-center justify-center gap-1" data-testid="waveform">
      {bars.map((i) => (
        <motion.div
          key={i}
          className="w-1 rounded-full"
          style={{ backgroundColor: color, height: 22, originY: 0.5 }}
          animate={
            active
              ? { scaleY: [0.3, 1, 0.4, 0.9, 0.3], opacity: [0.5, 1, 0.6, 1, 0.5] }
              : { scaleY: 0.25, opacity: 0.35 }
          }
          transition={
            active
              ? { duration: 0.9, repeat: Infinity, repeatType: "mirror", delay: i * 0.08, ease: "easeInOut" }
              : { duration: 0.3 }
          }
        />
      ))}
    </div>
  );
};

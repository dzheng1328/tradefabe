import { motion } from "framer-motion";
import { SPRING } from "../lib/motion";
import { playRangeChange } from "../lib/sound";

export default function RangeControl({
  options, value, onChange,
}: {
  options: string[];
  value: string;
  onChange: (window: string) => void;
}) {
  return (
    <div className="flex gap-1 text-xs font-mono">
      {options.map((w) => (
        <motion.button
          key={w}
          aria-pressed={w === value}
          onClick={() => {
            playRangeChange();
            onChange(w);
          }}
          whileTap={{ scale: 0.92 }}
          animate={{
            backgroundColor: w === value ? "#9fe870" : "rgba(0,0,0,0)",
            color: w === value ? "#0d0f0c" : "#7d8877",
          }}
          transition={SPRING}
          className="px-2 py-1 rounded"
        >
          {w}
        </motion.button>
      ))}
    </div>
  );
}

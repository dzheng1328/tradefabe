import { useEffect, useRef, useState } from "react";
import { isSoundEnabled, onSoundPlayed, setSoundEnabled } from "../lib/sound";
import BrandGlyph from "./BrandGlyph";

const PULSE_MS = 500;

export default function Nav() {
  const [soundOn, setSoundOn] = useState(isSoundEnabled());
  const [pulsing, setPulsing] = useState(false);
  const pulseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const unsubscribe = onSoundPlayed(() => {
      setPulsing(true);
      if (pulseTimer.current) clearTimeout(pulseTimer.current);
      pulseTimer.current = setTimeout(() => setPulsing(false), PULSE_MS);
    });
    return () => {
      unsubscribe();
      if (pulseTimer.current) clearTimeout(pulseTimer.current);
    };
  }, []);

  return (
    <nav className="w-fit whitespace-nowrap border-r border-white/5 p-5 text-sm text-ink-muted flex flex-col">
      <div className="text-ink font-bold mb-4 flex items-center gap-2">
        <BrandGlyph className="w-4 h-4 text-accent shrink-0" />
        tradefabe
      </div>
      <div className="mb-2 text-ink">Paper Books</div>
      <div>Research Lab</div>
      <button
        className={`mt-auto text-xs text-ink-muted text-left${pulsing ? " sound-toggle-pulse" : ""}`}
        onClick={() => {
          const next = !soundOn;
          setSoundEnabled(next);
          setSoundOn(next);
        }}
      >
        Sound: {soundOn ? "on" : "off"}
      </button>
    </nav>
  );
}

import { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { isSoundEnabled, onSoundPlayed, setSoundEnabled } from "../lib/sound";
import BrandGlyph from "./BrandGlyph";

const PULSE_MS = 500;

function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink to={to} className="relative text-ink no-underline">
      {({ isActive }) => (
        <>
          {label}
          {isActive && (
            <span className="family-underline absolute -bottom-1.5 left-0 right-0 h-px bg-accent origin-left animate-underline-draw" />
          )}
        </>
      )}
    </NavLink>
  );
}

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
    <nav className="flex items-center gap-6 px-4 h-12 border-b border-white/5 text-sm text-ink-muted shrink-0">
      <div className="text-ink font-bold flex items-center gap-2">
        <BrandGlyph className="w-4 h-4 text-accent shrink-0" />
        tradefabe
      </div>
      <NavItem to="/books" label="Paper Books" />
      <NavItem to="/research" label="Research Lab" />
      <button
        className={`ml-auto text-xs text-ink-muted${pulsing ? " sound-toggle-pulse" : ""}`}
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

import { useState } from "react";
import { isSoundEnabled, setSoundEnabled } from "../lib/sound";

export default function Nav() {
  const [soundOn, setSoundOn] = useState(isSoundEnabled());
  return (
    <nav className="w-fit whitespace-nowrap border-r border-white/5 p-5 text-sm text-ink-muted flex flex-col">
      <div className="text-ink font-bold mb-4">tradefabe</div>
      <div className="mb-2 text-ink">Paper Books</div>
      <div>Research Lab</div>
      <button
        className="mt-auto text-xs text-ink-muted text-left"
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

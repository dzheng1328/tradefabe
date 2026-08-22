import { useEffect, useRef } from "react";
import { playScrollTick } from "./sound";

// Attaches to any scrollable container via the returned ref, plays the granular
// scroll sound (sound.ts) on real content movement. Listens to the native `scroll`
// event and derives delta from scrollTop rather than raw `wheel` deltas, so it
// reflects actual scroll position change regardless of input device (trackpad,
// mouse wheel, scrollbar drag, keyboard paging).
export function useScrollSound<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let lastTop = el.scrollTop;
    function onScroll() {
      const top = el!.scrollTop;
      const delta = top - lastTop;
      lastTop = top;
      if (delta !== 0) playScrollTick(delta);
    }
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  return ref;
}

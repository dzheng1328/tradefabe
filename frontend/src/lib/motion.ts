// Shared spring transition for Framer Motion -- real weight/slight overshoot instead
// of a smooth eased fade, per the spec's "alive and breathing" visual-language
// amendment. One shared config so every tactile moment (row selection, detail-panel
// mount) feels consistent rather than each call site picking its own numbers.
export const SPRING = { type: "spring" as const, stiffness: 500, damping: 28 };

export function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

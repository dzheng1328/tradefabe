// tradefabe's small mark: a crossed-square, adapted from inspo1's glyph (idea #41,
// ops/ui_plan_data.json phase 1). Sits next to the wordmark in Nav today; reused as
// the particle-ring loader's shape in Phase 3.
export default function BrandGlyph({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      aria-hidden="true"
    >
      <rect x="3" y="3" width="18" height="18" />
      <line x1="3" y1="3" x2="21" y2="21" />
      <line x1="21" y1="3" x2="3" y2="21" />
    </svg>
  );
}

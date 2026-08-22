// tradefabe's mark: the twin-corsage bloom (ops/assets/generate-logo.mjs), same source
// as the app icon and favicon so the wordmark's glyph never drifts from the two.
export default function BrandGlyph({ className }: { className?: string }) {
  return (
    <img
      src="/favicon.svg"
      alt=""
      aria-hidden="true"
      className={`${className ?? ""} rounded-[3px] object-cover`}
    />
  );
}

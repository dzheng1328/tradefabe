import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      'plotly.js/dist/plotly': 'plotly.js/dist/plotly.js',
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    // react-plotly.js/plotly.js are externalized to native Node resolution by
    // default, which bypasses the resolve.alias above (needed because
    // react-plotly.js imports "plotly.js/dist/plotly" with no extension --
    // Node's ESM resolver, unlike CJS require, never appends one). Inlining
    // routes them through Vite's own transform instead, where the alias applies.
    server: {
      deps: {
        inline: ["react-plotly.js", "plotly.js"],
      },
    },
  },
});

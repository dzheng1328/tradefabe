import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    // react-plotly.js imports the bare specifier "plotly.js/dist/plotly" with no
    // extension -- Node's own ESM resolver (unlike CJS require) never appends one,
    // so Vite/Vitest's SSR transform fails to resolve it without this alias.
    alias: {
      'plotly.js/dist/plotly': 'plotly.js/dist/plotly.js',
    },
  },
})

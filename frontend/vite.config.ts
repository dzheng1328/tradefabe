import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Vite defaults to IPv6 loopback ([::1]) on this machine, which the desktop
    // app's webview and its serving-check both miss since they target the IPv4
    // 127.0.0.1 -- pin the dev server there explicitly.
    host: '127.0.0.1',
  },
  resolve: {
    // react-plotly.js imports the bare specifier "plotly.js/dist/plotly" with no
    // extension -- Node's own ESM resolver (unlike CJS require) never appends one,
    // so Vite/Vitest's SSR transform fails to resolve it without this alias.
    alias: {
      'plotly.js/dist/plotly': 'plotly.js/dist/plotly.js',
    },
  },
})

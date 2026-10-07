import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // Tolerate UTF-8 BOM on Windows-created .env.local keys
  const bypassRaw =
    env.VITE_DEV_BYPASS_AUTH ??
    env['\ufeffVITE_DEV_BYPASS_AUTH'] ??
    ''
  const bypassOn = ['true', '1', 'yes', 'on'].includes(bypassRaw.trim().toLowerCase())
  if (mode === 'production' && bypassOn) {
    throw new Error(
      'Refusing production build: VITE_DEV_BYPASS_AUTH is enabled. ' +
        'Unset it before deploying.',
    )
  }

  return {
  plugins: [react()],
  server: {
    // 5173 is commonly used by other local apps; portal owns 5175.
    port: 5175,
    strictPort: true,
    proxy: {
      // Forward portal /api/* calls to the Flask API during local development
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        // Keep Set-Cookie on the Vite origin so SSO sessions work in the SPA.
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            const cookies = proxyRes.headers['set-cookie']
            if (!cookies) return
            proxyRes.headers['set-cookie'] = cookies.map((cookie) =>
              cookie.replace(/;\s*Domain=[^;]+/i, ''),
            )
          })
        },
      },
    },
  },
}
})
